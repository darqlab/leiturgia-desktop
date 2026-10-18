#!/usr/bin/env bash
# Stage the parent Leiturgia server tree for the PyInstaller build.
# Usage: bash scripts/build.sh [path-to-parent-repo]   (default ../Leiturgia)
set -euo pipefail

PARENT="${1:-../Leiturgia}"
STAGE="build/leiturgia_server"

if [ ! -d "$PARENT/.git" ]; then
  echo "error: $PARENT is not a git checkout" >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"

git -C "$PARENT" ls-files | rsync -av --files-from=- "$PARENT/" "$STAGE/"

git -C "$PARENT" describe --tags --always --dirty > "$STAGE/_server_version.txt"
echo "staged $STAGE from $PARENT ($(cat "$STAGE/_server_version.txt"))"
