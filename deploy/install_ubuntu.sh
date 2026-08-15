#!/usr/bin/env bash
# Bootstrap Persian TTS-API on Ubuntu: venv + systemd on port 5004 (no reverse proxy).
#
# Usage (as root or with sudo):
#   sudo bash deploy/install_ubuntu.sh
#   sudo bash deploy/install_ubuntu.sh /opt/tts-api tts
#
# Env overrides:
#   APP_DIR   install path (default: /opt/tts-api)
#   APP_USER  system user  (default: tts)
#   APP_PORT  listen port  (default: 5004)
#   APP_HOST  bind address (default: 0.0.0.0 — reachable from LAN/internet)

set -euo pipefail

APP_DIR="${1:-${APP_DIR:-/opt/tts-api}}"
APP_USER="${2:-${APP_USER:-tts}}"
APP_PORT="${APP_PORT:-5004}"
APP_HOST="${APP_HOST:-0.0.0.0}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install_ubuntu.sh"
  exit 1
fi

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip ffmpeg curl rsync

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  echo "==> Creating user $APP_USER"
  useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

echo "==> Syncing app to $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a \
  --exclude '.venv' \
  --exclude 'output' \
  --exclude '.git' \
  --exclude '__pycache__' \
  "$REPO_ROOT"/ "$APP_DIR"/

mkdir -p "$APP_DIR/output/audio" "$APP_DIR/output/jobs" "$APP_DIR/output/uploads" "$APP_DIR/models"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Python venv + core requirements"
sudo -u "$APP_USER" bash -lc "
  cd '$APP_DIR'
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip setuptools wheel
  .venv/bin/pip install -r requirements.txt
"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.sample" "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env — set GEMINI_API_KEY and/or GOOGLE_APPS_SCRIPT_URL."
fi

# Always align bind settings for direct :5004 access (no Caddy)
if grep -q '^APP_PORT=' "$APP_DIR/.env" 2>/dev/null; then
  sed -i "s/^APP_PORT=.*/APP_PORT=$APP_PORT/" "$APP_DIR/.env"
else
  echo "APP_PORT=$APP_PORT" >>"$APP_DIR/.env"
fi
if grep -q '^APP_HOST=' "$APP_DIR/.env" 2>/dev/null; then
  sed -i "s/^APP_HOST=.*/APP_HOST=$APP_HOST/" "$APP_DIR/.env"
else
  echo "APP_HOST=$APP_HOST" >>"$APP_DIR/.env"
fi
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"

echo "==> systemd unit (binds $APP_HOST:$APP_PORT)"
sed \
  -e "s|/opt/tts-api|$APP_DIR|g" \
  -e "s|User=tts|User=$APP_USER|g" \
  -e "s|Group=tts|Group=$APP_USER|g" \
  -e "s|--host 0.0.0.0|--host $APP_HOST|g" \
  -e "s|--port 5004|--port $APP_PORT|g" \
  "$APP_DIR/deploy/tts-api.service" >/etc/systemd/system/tts-api.service

systemctl daemon-reload
systemctl enable --now tts-api
systemctl restart tts-api

# Open firewall port if ufw is active (safe no-op otherwise)
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi 'Status: active'; then
  echo "==> Allowing TCP $APP_PORT in ufw"
  ufw allow "${APP_PORT}/tcp" comment 'Persian TTS-API' || true
fi

PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Done. API listens directly on port $APP_PORT (no reverse proxy)."
echo "  Local:   http://127.0.0.1:${APP_PORT}/health"
echo "  Remote:  http://${PUBLIC_IP:-YOUR_SERVER_IP}:${APP_PORT}/health"
echo "  Logs:    journalctl -u tts-api -f"
echo "  Secrets: $APP_DIR/.env  (GEMINI_API_KEY, GOOGLE_APPS_SCRIPT_URL)"
echo
echo "If Caddy was previously installed for this app and you don't need it,"
echo "  leave your other sites alone; just don't point :80 at this API."
echo "  Optional: sudo systemctl disable --now caddy   # ONLY if Caddy isn't used elsewhere"
