#!/usr/bin/env bash
# Run Leiturgia Desktop from source on Raspberry Pi OS (64-bit) using the OS's GTK/WebKit.
# Usage: bash scripts/run-pi.sh [path-to-parent-repo]   (default ../Leiturgia)
# One-time system packages:
#   sudo apt install python3-venv python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export LEITURGIA_SERVER_DIR="$(cd "${1:-$HERE/../Leiturgia}" && pwd)"

if ! python3 -c 'import gi' 2>/dev/null; then
  echo "error: python3-gi missing - sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1" >&2
  exit 1
fi

cd "$HERE"
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q -r requirements-desktop.txt
exec .venv/bin/python desktop_entry.py
