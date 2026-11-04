#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
export SUPPORT_ROOT="$ROOT"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This launcher is for macOS."
  exit 1
fi

MACHINE="$(uname -m)"

if [ "$MACHINE" = "arm64" ]; then
  APP="$ROOT/MainSupport-macos-arm64.app"
elif [ "$MACHINE" = "x86_64" ]; then
  APP="$ROOT/MainSupport-macos-x86_64.app"
else
  echo "Unsupported architecture: $MACHINE"
  exit 1
fi

if [ ! -d "$APP" ]; then
  echo "MainSupport app for $MACHINE was not found."
  read -r -p "Press Enter to close..."
  exit 1
fi

xattr -cr "$APP" 2>/dev/null || true
chmod +x "$APP/Contents/MacOS/MainSupport" 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null || true

"$APP/Contents/MacOS/MainSupport"
