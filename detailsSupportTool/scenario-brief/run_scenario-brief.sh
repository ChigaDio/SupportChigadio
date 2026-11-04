#!/bin/bash

# Auto-generated launcher for scenario-brief.
set -u

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOL_NAME="scenario-brief"

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

APP="$TOOL_DIR/$TOOL_NAME.app"
APP_EXE="$APP/Contents/MacOS/$TOOL_NAME"

ZIP="$TOOL_DIR/macos-$ARCH/$TOOL_NAME-macos-$ARCH.zip"

if [ ! -f "$ZIP" ]; then
  echo "Application ZIP was not found:"
  echo "$ZIP"
  read -r -p "Press Enter to close..."
  exit 1
fi

# Check whether an existing app supports this Mac architecture.
if [ -d "$APP" ] && [ -x "$APP_EXE" ]; then
  EXISTING_ARCHS="$(lipo -archs "$APP_EXE" 2>/dev/null || true)"

  if ! echo "$EXISTING_ARCHS" | grep -qw "$ARCH"; then
    echo "Existing app does not support $ARCH."
    echo "Re-extracting the correct application..."
    rm -rf "$APP"
  fi
else
  rm -rf "$APP"
fi

# Extract the selected ZIP directly into the tool folder.
if [ ! -d "$APP" ]; then
  echo "Extracting $TOOL_NAME for $ARCH..."

  ditto -x -k "$ZIP" "$TOOL_DIR"

  if [ ! -d "$APP" ]; then
    echo "Failed to extract application:"
    echo "$APP"
    read -r -p "Press Enter to close..."
    exit 1
  fi
fi

if [ ! -x "$APP_EXE" ]; then
  echo "Application executable was not found:"
  echo "$APP_EXE"
  read -r -p "Press Enter to close..."
  exit 1
fi

# Remove macOS quarantine attributes from the extracted app.
xattr -cr "$APP" 2>/dev/null || true

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
"$APP_EXE"
CODE=$?

echo
echo "Exited with code $CODE."
read -r -p "Press Enter to close..."

exit "$CODE"
