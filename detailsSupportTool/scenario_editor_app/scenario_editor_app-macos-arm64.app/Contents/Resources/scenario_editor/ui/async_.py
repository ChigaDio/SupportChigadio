"""重い処理(HTTP)をワーカースレッドで実行し、結果を UI スレッドへ返す。"""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn, signals):
        super().__init__()
        self.fn = fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.fn()
        except BaseException as e:  # noqa: BLE001 ワーカーの例外は UI へ渡す
            e.__traceback_text__ = traceback.format_exc()
            self.signals.failed.emit(e)
            return
        self.signals.done.emit(result)


_alive = set()


def run_async(fn, on_ok=None, on_err=None, parent=None):
    """fn() をワーカースレッドで実行。on_ok(result) / on_err(exception) は UI スレッドで呼ばれる。
    parent が破棄済みなら(画面遷移後など)コールバックは呼ばない。"""
    signals = _Signals(parent)
    _alive.add(signals)

    def _cleanup():
        _alive.discard(signals)

    def _ok(r):
        _cleanup()
        if on_ok is not None:
            on_ok(r)

    def _err(e):
        _cleanup()
        if on_err is not None:
            on_err(e)

    signals.done.connect(_ok)
    signals.failed.connect(_err)
    QThreadPool.globalInstance().start(_Task(fn, signals))
    return signals
