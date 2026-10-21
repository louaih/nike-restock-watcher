#!/usr/bin/env python3
"""Poll Nike's stock API and email when sizes of a product come back in stock."""
import argparse
import json
import logging
import os
import random
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
NIKE_CHANNEL = "d9a5bc42-4b9c-4976-858a-f159cf99c647"  # Nike.com web channel
FAILURE_ALERT_THRESHOLD = 12  # consecutive failed checks before emailing a warning
# Product info saved with --save-product, used when Nike blocks the product feed (e.g. from VPS IPs).
PRODUCTS_FILE = Path(__file__).resolve().parent / "products.json"

log = logging.getLogger("watcher")


def env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Missing required env var {name}")
    return val


def get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.nike.com",
        "Referer": "https://www.nike.com/",
        "nike-api-caller-id": "com.nike.commerce.nikedotcom.web",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e} from {url.split('?')[0]}") from e


def fetch_product(style_color, marketplace, language):
    """Return title, price and {gtin: size} for the style color."""
    q = urllib.parse.urlencode(safe="(),", query=[
        ("filter", f"marketplace({marketplace})"),
        ("filter", f"language({language})"),
        ("filter", f"channelId({NIKE_CHANNEL})"),
        ("filter", f"productInfo.merchProduct.styleColor({style_color})"),
    ])
    data = get_json(f"https://api.nike.com/product_feed/threads/v3/?{q}")
    for obj in data.get("objects", []):
        for info in obj.get("productInfo", []):
            if info["merchProduct"]["styleColor"] != style_color:
                continue
            sizes = {}
            for sku in info.get("skus", []):
                specs = sku.get("countrySpecifications") or [{}]
                sizes[sku["gtin"]] = specs[0].get("localizedSize") or sku.get("nikeSize")
            price = info.get("merchPrice", {})
            return {
                "title": info["productContent"].get("fullTitle") or info["productContent"]["title"],
                "sizes": sizes,
                "price": price.get("currentPrice"),
                "currency": price.get("currency"),
            }
    raise RuntimeError(f"Style {style_color} not found in product feed")


def fetch_availability(style_color, marketplace):
    """Return {gtin: level} for every GTIN currently available."""
    q = urllib.parse.urlencode(safe="(),", query=[
        ("filter", f"styleColor({style_color})"),
        ("filter", f"merchGroup({marketplace})"),
    ])
    data = get_json(f"https://api.nike.com/deliver/available_gtins/v3?{q}")
    return {o["gtin"]: o.get("level") for o in data.get("objects", []) if o.get("available")}


def send_email(subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env("EMAIL_FROM") or env("SMTP_USER")
    msg["To"] = env("EMAIL_TO", required=True)
    msg.set_content(body)
    host = env("SMTP_HOST", required=True)
    port = int(env("SMTP_PORT", "587"))
    user, password = env("SMTP_USER"), env("SMTP_PASS")
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()
    with server:
        if user:
            server.login(user, password)
        server.send_message(msg)
    log.info("Email sent: %s", subject)


def load_saved_products():
    try:
        return json.loads(PRODUCTS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_product(cfg, state):
    """Fetch product info, falling back to the last good copy if the feed is blocked."""
    try:
        product = fetch_product(cfg.style, cfg.marketplace, cfg.language)
    except Exception as e:
        product = state.get("product") or load_saved_products().get(cfg.style)
        if not product:
            raise
        log.warning("Product feed failed (%s); using saved product info", e)
    state["product"] = product
    return product


def load_state(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"in_stock": []}


def check(cfg, state):
    product = get_product(cfg, state)
    title, sizes = product["title"], product["sizes"]
    available = fetch_availability(cfg.style, cfg.marketplace)
    in_stock = sorted(
        sizes.get(g, g) for g in available
        if not cfg.sizes or sizes.get(g, "").upper() in cfg.sizes
    )
    newly = [s for s in in_stock if s not in state["in_stock"]]
    log.info("%s: in stock %s", cfg.style, in_stock or "none")
    if newly:
        levels = {sizes.get(g, g): lvl for g, lvl in available.items()}
        lines = "\n".join(f"  - {s} ({levels.get(s, '?')} stock)" for s in newly)
        send_email(
            f"Back in stock: {title} ({', '.join(newly)})",
            f"{title} is back in stock on Nike.\n\nNewly available sizes:\n{lines}\n\n"
            f"All sizes in stock now: {', '.join(in_stock)}\nPrice: {product['price']} {product['currency']}\n\n{cfg.url}\n",
        )
    state["in_stock"] = in_stock
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="run one check and exit")
    p.add_argument("--test-email", action="store_true", help="send a test email and exit")
    p.add_argument("--save-product", action="store_true",
                   help="save product info to products.json (run where Nike isn't blocked, then commit)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    class cfg:
        style = env("STYLE_COLOR", "IO7254-133")
        marketplace = env("MARKETPLACE", "US")
        language = env("LANGUAGE", "en")
        url = env("PRODUCT_URL", f"https://www.nike.com/t/_/{style}")
        sizes = {s.strip().upper() for s in env("SIZES", "").split(",") if s.strip()}
        interval = int(env("INTERVAL_SECONDS", "300"))
        state_file = Path(env("STATE_FILE", "state.json"))

    if args.save_product:
        products = load_saved_products()
        products[cfg.style] = fetch_product(cfg.style, cfg.marketplace, cfg.language)
        PRODUCTS_FILE.write_text(json.dumps(products, indent=2) + "\n")
        log.info("Saved %s (%s) to %s", cfg.style, products[cfg.style]["title"], PRODUCTS_FILE)
        return

    if args.test_email:
        send_email("Nike restock watcher: test email", f"SMTP works. Watching {cfg.style}:\n{cfg.url}\n")
        return

    state = load_state(cfg.state_file)
    failures = 0
    while True:
        try:
            state = check(cfg, state)
            cfg.state_file.write_text(json.dumps(state))
            failures = 0
        except Exception as e:
            failures += 1
            log.error("Check failed (%d in a row): %s", failures, e)
            if failures == FAILURE_ALERT_THRESHOLD:
                try:
                    send_email("Nike restock watcher is failing",
                               f"{failures} consecutive checks failed. Last error:\n{e!r}\n")
                except Exception as mail_err:
                    log.error("Could not send failure alert: %s", mail_err)
        if args.once:
            return
        time.sleep(cfg.interval * random.uniform(0.8, 1.2))


if __name__ == "__main__":
    main()
