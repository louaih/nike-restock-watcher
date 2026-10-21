# Nike restock watcher

Polls Nike's stock API every ~5 minutes and emails you when any size (or the sizes you pick)
of a product comes back in stock. Uses only the Python standard library (3.6+).

## Install on the VPS

```bash
git clone <repo-url> /opt/nike-restock-watcher
cd /opt/nike-restock-watcher
cp config.env.example config.env && nano config.env   # SMTP creds, sizes
set -a; . ./config.env; set +a
python3 watcher.py --test-email                       # confirm email works
python3 watcher.py --once                             # confirm Nike API reachable
./install.sh                                          # install + start systemd service
```

## Update

```bash
cd /opt/nike-restock-watcher && git pull && ./install.sh
```

Logs: `journalctl -u nike-restock-watcher -f`

## Behavior
- Emails once per size when it goes from out of stock to in stock (state kept in
  `/var/lib/nike-restock-watcher/state.json`), so it won't spam you. If a size sells out and
  restocks again, you'll get another email.
- If 12 checks in a row fail (e.g. Nike blocks the VPS IP with HTTP 403), you get a warning email.
  Setting `HTTPS_PROXY` in `config.env` routes requests through a proxy.
- If Nike blocks the product-info request, it uses the copy saved in `products.json`. Only the
  stock request has to get through.
- To watch a different product, change `STYLE_COLOR` (the `XX0000-000` code at the end of the URL),
  then run `python3 watcher.py --save-product` on a machine Nike doesn't block and commit `products.json`.
