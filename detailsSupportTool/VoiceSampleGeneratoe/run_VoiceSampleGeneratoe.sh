#!/bin/bash
# Auto-generated launcher for VoiceSampleGeneratoe (macOS)
DIR="$(cd "$(dirname "$0")" && pwd)"

# Install requirements.txt if it exists next to this script.
if [ -f "$DIR/requirements.txt" ]; then
  PY="$(command -v python3 || command -v python || true)"
  if [ -n "$PY" ]; then
    echo "Installing requirements..."
    "$PY" -m pip install -q -r "$DIR/requirements.txt" \
      || echo "Warning: failed to install requirements"
  else
    echo "Warning: Python not found; skipping requirements install"
  fi
fi

# Run the binary inside the bundle directly so logs stay in this
# terminal and Ctrl+C / closing the terminal stops the server.
"$DIR/VoiceSampleGeneratoe.app/Contents/MacOS/VoiceSampleGeneratoe"
echo
echo "Exited with code $?."
read -r -p "Press Enter to close..."
