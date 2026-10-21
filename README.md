# Nike restock watcher
[![Watch stock](https://github.com/louaih/nike-restock-watcher/actions/workflows/watch.yml/badge.svg)](https://github.com/louaih/nike-restock-watcher/actions/workflows/watch.yml)

Checks Nike's stock API every ~5 minutes on GitHub Actions and emails you when any size (or the
sizes you pick) of a product comes back in stock. Uses only the Python standard library.

## Setup

[`.github/workflows/watch.yml`](.github/workflows/watch.yml) runs on a schedule (GitHub delays
scheduled runs, so expect checks every 5-15 minutes). Store the email settings as repo secrets:

```bash
cp config.env.example config.env && nano config.env
gh secret set -f config.env                    # SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
gh variable set SIZES --body "M"               # optional size filter, comma-separated
gh workflow run watch.yml -f test_email=true   # send a test email
gh workflow run watch.yml                      # run a check now
```

Scheduled runs are free on public repos. GitHub pauses them after 60 days without commits;
re-enable from the Actions tab.

## Behavior
- Emails once per size when it goes from out of stock to in stock (state carried between runs in
  the Actions cache), so it won't spam you. If a size sells out and restocks again, you'll get
  another email.
- If 12 checks in a row fail, you get a warning email.
- If Nike blocks the product-info request, it uses the copy saved in `products.json`. Only the
  stock request has to get through.

## Watching a different product
Change `STYLE_COLOR` (the `XX0000-000` code at the end of the URL) and `PRODUCT_URL` in the
workflow, then save its product info and commit `products.json`:

```bash
STYLE_COLOR=XX0000-000 python3 watcher.py --save-product
```

## Running locally
`python3 watcher.py` checks in a loop (every `INTERVAL_SECONDS`, default 300) with the same
environment variables; `--once` runs a single check. Nike blocks many VPS/datacenter IPs (HTTP 403).
