#!/usr/bin/env bash
# Persian TTS-API interactive toolbox (Ubuntu / Linux counterpart to toolbox.cmd)
#
# Usage:
#   chmod +x toolbox.sh
#   ./toolbox.sh
#   ./toolbox.sh http://127.0.0.1:5004
#
# Requires the API to be running (./run_api.sh or systemd tts-api).

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

echo
echo "Starting Persian TTS-API Toolbox…"
echo "Python: $PY"
echo

exec "$PY" -m cli.toolbox "$@"
