#!/bin/bash
# Auto-generated launcher for scenario-brief (macOS x86_64)
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/scenario-brief.app"
ZIP="$DIR/scenario-brief-macos-x86_64.zip"
# Unzip next to this script if the app has not been extracted yet.
if [ ! -d "$APP" ] && [ -f "$ZIP" ]; then
  ditto -x -k "$ZIP" "$DIR"
fi
xattr -cr "$APP" 2>/dev/null || true
# Install requirements.txt (tool folder) if it exists.
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
# Run the binary inside the bundle directly so logs stay in this
# terminal and Ctrl+C / closing the terminal stops the server.
"$APP/Contents/MacOS/scenario-brief"
code=$?
echo
echo "Exited with code $code."
read -r -p "Press Enter to close..."
