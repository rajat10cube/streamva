#!/usr/bin/env bash
# Update Streamva in place (run INSIDE the container, or via `pct exec`).
# Re-fetches the app + rebuilds; your data, library config and password
# (in /opt/streamva-data) are preserved.
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8

RAW="https://raw.githubusercontent.com/rajat10cube/streamva/main"
REPO="https://github.com/rajat10cube/streamva"

curl -fsSL "$RAW/deploy/lxc/streamva-install.sh" -o /tmp/streamva-install.sh
STREAMVA_REPO="$REPO" bash /tmp/streamva-install.sh
rm -f /tmp/streamva-install.sh
echo "[streamva] update complete."
