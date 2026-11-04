#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

ZIP="SupportChigadio-macos.zip"
DIR="SupportChigadio"

NEED_EXTRACT=0
if [ ! -d "$DIR" ]; then
  NEED_EXTRACT=1
elif [ -f VERSION ] && [ -f "$DIR/.version" ]; then
  if [ "$(cat VERSION)" != "$(cat "$DIR/.version")" ]; then
    NEED_EXTRACT=1
  fi
fi

if [ "$NEED_EXTRACT" = "1" ]; then
  if [ ! -f "$ZIP" ]; then
    echo "Error: $ZIP が見つかりません"
    read -r -p "Enterキーで終了..."
    exit 1
  fi
  echo "解凍中... ($ZIP)"
  rm -rf "$DIR"
  unzip -q -o "$ZIP"
  cp VERSION "$DIR/.version" 2>/dev/null || true
fi

if [ -x "$DIR/SupportChigadio.command" ]; then
  exec "$DIR/SupportChigadio.command"
fi
echo "Error: $DIR/SupportChigadio.command が見つかりません"
read -r -p "Enterキーで終了..."
exit 1
