#!/usr/bin/env bash
# Install Asterisk Gemini TTS helper on this host (Issabel / FreePBX / vanilla Asterisk).
#
# Usage:
#   sudo bash deploy/asterisk/install_on_asterisk.sh
#   sudo GOOGLE_APPS_SCRIPT_URL='https://script.google.com/macros/s/XXX/exec' \
#        bash deploy/asterisk/install_on_asterisk.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_BIN="${INSTALL_BIN:-/usr/local/bin/gemini_tts.py}"
SOUNDS_DIR="${SOUNDS_DIR:-/var/lib/asterisk/sounds/custom}"
ENV_FILE="${ENV_FILE:-/etc/asterisk/gemini_tts.env}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/asterisk/install_on_asterisk.sh"
  exit 1
fi

echo "==> Installing gemini_tts.py → $INSTALL_BIN"
install -m 0755 "$SCRIPT_DIR/gemini_tts.py" "$INSTALL_BIN"

echo "==> Ensuring sounds dir $SOUNDS_DIR"
mkdir -p "$SOUNDS_DIR"
# Best-effort ownership for Asterisk
if id asterisk >/dev/null 2>&1; then
  chown -R asterisk:asterisk "$SOUNDS_DIR" || true
elif id asteriskuser >/dev/null 2>&1; then
  chown -R asteriskuser:asteriskuser "$SOUNDS_DIR" || true
fi

if ! python3 -c "import requests" 2>/dev/null; then
  echo "==> Installing python3-requests"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y python3-requests python3-pip || pip3 install requests
  else
    pip3 install requests
  fi
fi

URL="${GOOGLE_APPS_SCRIPT_URL:-}"
if [[ -n "$URL" ]]; then
  echo "==> Writing $ENV_FILE"
  cat >"$ENV_FILE" <<EOF
# Sourced by dialplan System() or crontab — keep private
GOOGLE_APPS_SCRIPT_URL=$URL
ASTERISK_TTS_OUT=$SOUNDS_DIR/gemini_tts.wav
EOF
  chmod 640 "$ENV_FILE"
  echo "Saved GOOGLE_APPS_SCRIPT_URL"
else
  echo "NOTE: GOOGLE_APPS_SCRIPT_URL not set. After deploying Code.gs, run:"
  echo "  echo 'GOOGLE_APPS_SCRIPT_URL=https://script.google.com/macros/s/XXX/exec' | sudo tee $ENV_FILE"
fi

echo
echo "Done."
echo "  1) Paste Code.gs from $SCRIPT_DIR/Code.gs into Apps Script and Deploy as Web app (Anyone)."
echo "  2) Set GOOGLE_APPS_SCRIPT_URL to the /exec URL."
echo "  3) Test:"
echo "       export GOOGLE_APPS_SCRIPT_URL='...'"
echo "       python3 $INSTALL_BIN --text 'سلام'"
echo "  4) Add dialplan from $SCRIPT_DIR/dialplan-snippet.conf"
echo "  Docs: $SCRIPT_DIR/README.md"
