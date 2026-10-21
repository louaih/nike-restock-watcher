#!/usr/bin/env bash
# Run as root from the repo cloned at /opt/nike-restock-watcher: sudo ./install.sh
# Safe to re-run after `git pull` to pick up changes.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f config.env ]; then
  echo "Create config.env first: cp config.env.example config.env && nano config.env" >&2
  exit 1
fi
chmod 600 config.env
cp nike-restock-watcher.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable nike-restock-watcher
systemctl restart nike-restock-watcher
systemctl status --no-pager nike-restock-watcher
