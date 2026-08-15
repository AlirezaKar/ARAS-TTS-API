#!/usr/bin/env bash
# Bootstrap Persian TTS-API on Ubuntu: venv, systemd auto-restart, Caddy on :80 → :5004
#
# Usage (as root or with sudo):
#   sudo bash deploy/install_ubuntu.sh
#   sudo bash deploy/install_ubuntu.sh /opt/tts-api tts
#
# Env overrides:
#   APP_DIR   install path (default: /opt/tts-api)
#   APP_USER  system user  (default: tts)
#   DOMAIN    if set, Caddy uses this hostname (HTTPS); else listens on :80

set -euo pipefail

APP_DIR="${1:-${APP_DIR:-/opt/tts-api}}"
APP_USER="${2:-${APP_USER:-tts}}"
DOMAIN="${DOMAIN:-}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install_ubuntu.sh"
  exit 1
fi

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip ffmpeg curl debian-keyring debian-archive-keyring apt-transport-https rsync gnupg

if ! command -v caddy >/dev/null 2>&1; then
  echo "==> Installing Caddy"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -y
  apt-get install -y caddy
fi

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
  sed -i 's/^APP_PORT=.*/APP_PORT=5004/' "$APP_DIR/.env"
  sed -i 's/^APP_HOST=.*/APP_HOST=127.0.0.1/' "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env — set GEMINI_API_KEY and/or GOOGLE_APPS_SCRIPT_URL."
fi

echo "==> systemd unit"
sed \
  -e "s|/opt/tts-api|$APP_DIR|g" \
  -e "s|User=tts|User=$APP_USER|g" \
  -e "s|Group=tts|Group=$APP_USER|g" \
  "$APP_DIR/deploy/tts-api.service" >/etc/systemd/system/tts-api.service

systemctl daemon-reload
systemctl enable --now tts-api

echo "==> Caddy"
mkdir -p /var/log/caddy
if [[ -n "$DOMAIN" ]]; then
  cat >/etc/caddy/Caddyfile <<EOF
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:5004 {
		transport http {
			read_timeout 10m
			write_timeout 10m
		}
	}
	log {
		output file /var/log/caddy/tts-api.log
	}
}
EOF
else
  cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
fi
systemctl enable --now caddy
systemctl reload caddy || systemctl restart caddy

echo
echo "Done."
echo "  API (local):  http://127.0.0.1:5004/health"
echo "  Via Caddy:    http://\$(hostname -I | awk '{print \$1}')/health"
echo "  Logs:         journalctl -u tts-api -f"
echo "  Edit secrets: $APP_DIR/.env  (GEMINI_API_KEY, GOOGLE_APPS_SCRIPT_URL)"
echo "  Asterisk TTS: $APP_DIR/deploy/asterisk/README.md"
