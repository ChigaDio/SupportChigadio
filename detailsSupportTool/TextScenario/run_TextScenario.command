#!/bin/bash

# Auto-generated launcher for TextScenario.
set -u

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOL_NAME="TextScenario"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This launcher is for macOS."
  read -r -p "Press Enter to close..."
  exit 1
fi

MACHINE="$(uname -m)"

if [ "$MACHINE" = "arm64" ]; then
  ARCH="arm64"
elif [ "$MACHINE" = "x86_64" ]; then
  ARCH="x86_64"
else
  echo "Unsupported architecture: $MACHINE"
  read -r -p "Press Enter to close..."
  exit 1
fi

EXECUTABLE_NAME="$TOOL_NAME-macos-$ARCH"
EXECUTABLE="$TOOL_DIR/$EXECUTABLE_NAME"
ZIP="$TOOL_DIR/macos-$ARCH/$TOOL_NAME-macos-$ARCH.zip"

if [ ! -f "$ZIP" ]; then
  echo "Application ZIP was not found:"
  echo "$ZIP"
  read -r -p "Press Enter to close..."
  exit 1
fi

# Check whether an existing executable supports this Mac architecture.
if [ -f "$EXECUTABLE" ] && [ -x "$EXECUTABLE" ]; then
  EXISTING_ARCHS="$(lipo -archs "$EXECUTABLE" 2>/dev/null || true)"

  if ! echo "$EXISTING_ARCHS" | grep -qw "$ARCH"; then
    echo "Existing executable does not support $ARCH."
    echo "Re-extracting the correct executable..."
    rm -f "$EXECUTABLE"
  fi
else
  rm -f "$EXECUTABLE"
fi

# Extract the selected ZIP directly into the tool folder.
if [ ! -f "$EXECUTABLE" ]; then
  echo "Extracting $TOOL_NAME for $ARCH..."

  ditto -x -k "$ZIP" "$TOOL_DIR"

  if [ ! -f "$EXECUTABLE" ]; then
    echo "Failed to extract executable:"
    echo "$EXECUTABLE"
    read -r -p "Press Enter to close..."
    exit 1
  fi
fi

if [ ! -x "$EXECUTABLE" ]; then
  chmod +x "$EXECUTABLE"
fi

# Remove macOS quarantine attributes.
xattr -cr "$EXECUTABLE" 2>/dev/null || true

# Install requirements.txt if available.
REQ="$TOOL_DIR/requirements.txt"

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

# Run the application in this terminal.
"$EXECUTABLE"
CODE=$?

echo
echo "Exited with code $CODE."
read -r -p "Press Enter to close..."

exit "$CODE"
