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
  EXECUTABLE="$ROOT/MainSupport-macos-arm64"
elif [ "$MACHINE" = "x86_64" ]; then
  EXECUTABLE="$ROOT/MainSupport-macos-x86_64"
else
  echo "Unsupported architecture: $MACHINE"
  exit 1
fi
if [ ! -f "$EXECUTABLE" ]; then
  echo "MainSupport executable for $MACHINE was not found."
  read -r -p "Press Enter to close..."
  exit 1
fi
xattr -cr "$EXECUTABLE" 2>/dev/null || true
chmod +x "$EXECUTABLE" 2>/dev/null || true
codesign --force --sign - "$EXECUTABLE" 2>/dev/null || true
"$EXECUTABLE"
