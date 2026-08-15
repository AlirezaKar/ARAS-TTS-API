#!/usr/bin/env bash
# Alias for run_api.sh (same as Windows run_api.cmd)
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_api.sh" "$@"
