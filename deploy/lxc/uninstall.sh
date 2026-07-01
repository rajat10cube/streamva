#!/usr/bin/env bash
# Remove Streamva (run INSIDE the container, or via `pct exec`).
# Keeps your data by default; pass --purge to also delete it.
#
#   bash uninstall.sh            # remove app, keep /opt/streamva-data
#   bash uninstall.sh --purge    # also delete data + service user
set -euo pipefail

systemctl disable --now streamva 2>/dev/null || true
rm -f /etc/systemd/system/streamva.service
systemctl daemon-reload 2>/dev/null || true
rm -rf /opt/streamva

if [ "${1:-}" = "--purge" ]; then
  rm -rf /opt/streamva-data
  id streamva >/dev/null 2>&1 && deluser streamva 2>/dev/null || true
  echo "[streamva] fully removed (including data)."
else
  echo "[streamva] removed. Data kept at /opt/streamva-data (re-run with --purge to delete)."
fi
echo "[streamva] To remove the whole container, on the host run: pct stop <CTID> && pct destroy <CTID>"
