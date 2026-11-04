```bash
#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"
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

# dataフォルダはSupportChigadioの一つ上に配置する
DATA_DIR="$PARENT/data"
APP_DATA_DIR="$APP/Contents/data"

# 以前の起動でContents/dataが実フォルダとして作られていた場合は移動する
if [ -d "$APP_DATA_DIR" ] && [ ! -L "$APP_DATA_DIR" ]; then
  if [ -e "$DATA_DIR" ]; then
    echo "Both app data and external data directories already exist."
    echo "Please merge them manually:"
    echo "  $APP_DATA_DIR"
    echo "  $DATA_DIR"
    read -r -p "Press Enter to close..."
    exit 1
  fi

  mv "$APP_DATA_DIR" "$DATA_DIR"
fi

# 親フォルダにdataを作成
mkdir -p "$DATA_DIR"

# .app内部のdataを親フォルダのdataへ接続
if [ ! -L "$APP_DATA_DIR" ]; then
  ln -s "$DATA_DIR" "$APP_DATA_DIR"
fi

xattr -cr "$APP" 2>/dev/null || true
chmod +x "$APP/Contents/MacOS/MainSupport" 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null || true

"$APP/Contents/MacOS/MainSupport"
```
