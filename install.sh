#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/Radioactive"

if [[ ! -f "$SOURCE_DIR/index.theme" || ! -d "$SOURCE_DIR/cursors" ]]; then
  printf 'Radioactive theme files are missing beside this installer.\n' >&2
  exit 1
fi

if (( EUID == 0 )); then
  DEST_DIR="/usr/share/icons"
else
  DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
  DEST_DIR="$DATA_HOME/icons"
fi

THEME_DIR="$DEST_DIR/Radioactive"
# Replace any previous install so no stale files from older versions remain.
rm -rf -- "$THEME_DIR"
mkdir -p -- "$THEME_DIR"
cp -R -- "$SOURCE_DIR/." "$THEME_DIR/"

printf 'Installed Radioactive to %s\n' "$THEME_DIR"
