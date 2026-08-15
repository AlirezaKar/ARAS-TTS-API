#!/usr/bin/env bash
# Start Persian TTS-API (dev / foreground). Ubuntu / Linux counterpart to run_api.cmd
#
# Usage:
#   chmod +x run_api.sh
#   ./run_api.sh
#   ./run_api.sh --host 127.0.0.1 --port 5004
#
# Production on Ubuntu usually uses systemd (deploy/install_ubuntu.sh) instead.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "No Python found. Create a venv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-5004}"

# Allow: ./run_api.sh --host 127.0.0.1 --port 5004
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:?}"
      shift 2
      ;;
    --port)
      PORT="${2:?}"
      shift 2
      ;;
    --no-reload)
      NO_RELOAD=1
      shift
      ;;
    *)
      EXTRA+=("$1")
      shift
      ;;
  esac
done

echo "Starting Persian TTS-API on http://${HOST}:${PORT} …"
echo "Python: $PY"
echo "Tip: set GEMINI_API_KEY / GOOGLE_APPS_SCRIPT_URL in .env"

RELOAD_ARGS=(--reload)
if [[ "${NO_RELOAD:-0}" == "1" ]] || [[ "${APP_RELOAD:-1}" == "0" ]]; then
  RELOAD_ARGS=()
fi

exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT" "${RELOAD_ARGS[@]}" "${EXTRA[@]}"
