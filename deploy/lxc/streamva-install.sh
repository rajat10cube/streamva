#!/usr/bin/env bash
# Streamva in-container installer (Debian 12 LXC). Re-running it = an in-place
# update: it re-fetches the app and rebuilds, but preserves your data, library
# config, and password (kept in $DATA_DIR, outside the app dir).
#
#   STREAMVA_REPO=https://github.com/rajat10cube/streamva bash streamva-install.sh
#   # or, with source already unpacked at /opt/streamva:
#   bash streamva-install.sh
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive

APP_DIR="${APP_DIR:-/opt/streamva}"
DATA_DIR="${DATA_DIR:-/opt/streamva-data}"
SERVICE_USER="${SERVICE_USER:-streamva}"
PORT="${PORT:-8000}"
NODE_MAJOR="${NODE_MAJOR:-22}"
STREAMVA_REPO="${STREAMVA_REPO:-}"
STREAMVA_REF="${STREAMVA_REF:-main}"
AUTH_USER="${STREAMVA_AUTH_USER:-admin}"
AUTH_PASS="${STREAMVA_AUTH_PASS:-}"   # empty -> first-run signup creates the admin
ENV_FILE="$DATA_DIR/streamva.env"
CONFIG_FILE="$DATA_DIR/streamva.yaml"

msg() { echo -e "\e[1;34m[streamva]\e[0m $*"; }
die() { echo -e "\e[1;31m[streamva] $*\e[0m" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root"

msg "Installing base packages (python, ffmpeg, git)…"
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends \
  python3 python3-venv python3-pip ffmpeg git ca-certificates curl >/dev/null

# --- fetch source ---
if [ -n "$STREAMVA_REPO" ]; then
  msg "Fetching Streamva ($STREAMVA_REF)…"
  rm -rf "$APP_DIR"
  git clone --depth 1 --branch "$STREAMVA_REF" "$STREAMVA_REPO" "$APP_DIR" -q
elif [ -d "$APP_DIR/backend" ]; then
  msg "Using existing source at $APP_DIR"
else
  die "no STREAMVA_REPO set and no source found at $APP_DIR"
fi

# --- frontend: use prebuilt static if shipped, else build with Node ---
if [ -f "$APP_DIR/backend/app/static/index.html" ]; then
  msg "Prebuilt frontend found — skipping Node/build."
else
  msg "Installing Node.js ${NODE_MAJOR} and building frontend…"
  if ! command -v node >/dev/null 2>&1; then
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - >/dev/null 2>&1
    apt-get install -y -qq nodejs >/dev/null
  fi
  ( cd "$APP_DIR/frontend" && (npm ci --silent || npm install --silent) && npm run build )
fi

# --- python venv + deps ---
msg "Creating Python venv and installing dependencies…"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q

# --- service user + persistent data dir ---
id -u "$SERVICE_USER" >/dev/null 2>&1 || \
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
mkdir -p "$DATA_DIR"

# --- persistent config + env (written once; survives updates) ---
if [ ! -f "$CONFIG_FILE" ]; then
  msg "Writing initial config (add libraries from the web UI)…"
  cat > "$CONFIG_FILE" <<'YAML'
# Add course folders from the web UI (Libraries). You may also list them here —
# entries are imported into the database on first run only.
# group_depth defaults to "auto" (adapts to flat or provider-grouped layouts).
libraries: []
YAML
fi
if [ ! -f "$ENV_FILE" ]; then
  {
    echo "STREAMVA_CONFIG=$CONFIG_FILE"
    echo "STREAMVA_DATA_DIR=$DATA_DIR"
    echo "STREAMVA_AUTH=basic"
    echo "STREAMVA_AUTH_USER=$AUTH_USER"
    [ -n "$AUTH_PASS" ] && echo "STREAMVA_AUTH_PASS=$AUTH_PASS"
  } > "$ENV_FILE"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR" "$DATA_DIR"
chmod 600 "$ENV_FILE"

# --- systemd service (reads the persistent env file) ---
msg "Installing systemd service…"
cat > /etc/systemd/system/streamva.service <<EOF
[Unit]
Description=Streamva course player
After=network-online.target
Wants=network-online.target

[Service]
User=$SERVICE_USER
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips '*'
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable streamva >/dev/null 2>&1 || true
systemctl restart streamva

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
msg "Done ✔  Streamva → http://${IP:-<container-ip>}:$PORT"
if grep -q '^STREAMVA_AUTH_PASS=' "$ENV_FILE"; then
  msg "Login: $AUTH_USER / $(sed -n 's/^STREAMVA_AUTH_PASS=//p' "$ENV_FILE")"
else
  msg "Open the app and create your admin (master) account on first login."
fi
msg "Add your course folders in the web UI → Libraries."
