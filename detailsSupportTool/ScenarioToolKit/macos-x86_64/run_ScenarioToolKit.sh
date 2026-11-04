#!/bin/bash

DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/ScenarioToolKit.app"
ZIP="$DIR/ScenarioToolKit-macos-x86_64.zip"

if [ ! -d "$APP" ] && [ -f "$ZIP" ]; then
  ditto -x -k "$ZIP" "$DIR"
fi

xattr -cr "$APP" 2>/dev/null || true

REQ="$DIR/../requirements.txt"

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

"$APP/Contents/MacOS/ScenarioToolKit"

code=$?
echo
echo "Exited with code $code."
read -r -p "Press Enter to close..."
