#!/usr/bin/env bash
# Start ScamShield AI on macOS or Linux from a terminal:
#   ./launch.sh
# Create a clickable launcher on Linux with tools/create_shortcut.sh
set -euo pipefail
cd "$(dirname "$0")"
exec python3 launcher.py "$@"
