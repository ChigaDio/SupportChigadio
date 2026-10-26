"""Scenario Editor (PySide6) の起動。  python main.py [--url http://127.0.0.1:5000] [--light]"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scenario Editor")
    ap.add_argument("--url", help="シナリオエディタ(Flask)サーバーのアドレス(設定を上書きして保存)")
    ap.add_argument("--light", action="store_true", help="ライトテーマで起動")
    ap.add_argument("--dir", help="設定・プリセットの保存先フォルダ")
    args = ap.parse_args(argv)

    from PySide6.QtWidgets import QApplication
    from scenario_editor.ui import theme
    from scenario_editor.ui.app_state import AppState
    from scenario_editor.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Scenario Editor")
    state = AppState(args.dir)
    if args.url:
        state.set_base_url(args.url)
    theme.apply_theme(app, "light" if args.light else state.settings.get("theme", "dark"))
    win = MainWindow(state)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
