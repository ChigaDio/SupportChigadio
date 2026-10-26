#!/bin/bash
# Auto-generated launcher for scenario-brief (macOS)
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

open "$DIR/scenario-brief.app"
