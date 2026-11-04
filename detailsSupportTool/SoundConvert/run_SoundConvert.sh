#!/bin/bash

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This launcher is for macOS."
  read -r -p "Press Enter to close..."
  exit 1
fi

MACHINE="$(uname -m)"

if [ "$MACHINE" = "arm64" ]; then
  APP="$ROOT/SoundConvert-macos-arm64.app"
elif [ "$MACHINE" = "x86_64" ]; then
  APP="$ROOT/SoundConvert-macos-x86_64.app"
else
  echo "Unsupported architecture: $MACHINE"
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -d "$APP" ]; then
  echo "App for $MACHINE was not found:"
  echo "$APP"
  read -r -p "Press Enter to close..."
  exit 1
fi

# Remove downloaded-file quarantine attributes.
xattr -cr "$APP" 2>/dev/null || true

# Ensure the executable bit is set.
chmod +x "$APP/Contents/MacOS/SoundConvert" 2>/dev/null || true

# Re-sign locally after quarantine removal.
codesign --force --deep --sign - "$APP" 2>/dev/null || true

# Install requirements if present.
REQ="$ROOT/requirements.txt"

if [ -f "$REQ" ]; then
  PY="$(command -v python3 || command -v python || true)"

  if [ -n "$PY" ]; then
    echo "Installing requirements..."
    "$PY" -m pip install -q -r "$REQ" \
      || echo "Warning: failed to install requirements"
  else
    echo "Warning: Python not found; skipping requirements install"
  fi
fi

# Run the selected application.
"$APP/Contents/MacOS/SoundConvert"

code=$?

echo
echo "Exited with code $code."
read -r -p "Press Enter to close..."
