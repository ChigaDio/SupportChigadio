"""PySide6 の代用品 (スモークテスト専用)。

実機の Qt は動かせない環境で、Qt 層の Python コード(ロジック・呼び出しの食い違い)を実行して
AttributeError / TypeError などを見つけるためのもの。描画やイベントは再現しない。
・存在しない属性は「何でも受けるメソッド」になり、connect/emit も持つ(シグナル兼用)
・setXxx/xxx()/isXxx() は値を覚えて返す。レイアウトと QComboBox は本物らしく動く
・QThreadPool は同期実行、QTimer は flush_timers() で手動実行
"""
from __future__ import annotations

import sys
import types

TIMERS = []
NUMERIC = {"width", "height", "x", "y", "value", "count", "length", "minimum", "maximum", "horizontalAdvance", "blockNumber",
           "position", "blockCount", "currentRow", "currentIndex", "lineWidth", "lineCount", "positionInBlock", "top", "bottom",
           "left", "right", "indexOf", "row", "column", "selectionStart", "selectionEnd", "tabStopDistance", "pageStep",
           "singleStep", "verticalOffset", "advance", "ascent", "descent", "lineSpacing", "manhattanLength"}
TRUE_DEFAULT = {"isVisible", "isEnabled", "isActiveWindow", "isOpen", "hasFocus"}


class Any:
    """どんな操作も受ける値。"""

    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return Any()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Any()

    def __bool__(self):
        return True

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __int__(self):
        return 0

    __index__ = __int__

    def __float__(self):
        return 0.0

    def __str__(self):
        return ""

    def __format__(self, spec):
        return ""

    def _op(self, *a):
        return Any()

    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __floordiv__ = __or__ = __ror__ = __and__ = _op
    __neg__ = __invert__ = _op

    def __eq__(self, o):
        return self is o

    __hash__ = object.__hash__

    def __lt__(self, o):
        return False

    __gt__ = __le__ = __ge__ = __lt__

    def __contains__(self, x):
        return False


class Bound:
    """シグナル兼メソッド。"""

    def __init__(self, owner, name):
        self.owner, self.name, self.slots = owner, name, []

    def connect(self, fn, *a, **k):
        self.slots.append(fn)

    def disconnect(self, *a):
        self.slots = []

    def emit(self, *args):
        for s in list(self.slots):
            s(*args)

    def __call__(self, *args, **kw):
        return self.owner._call(self.name, args, kw)


class Signal:
    def __init__(self, *types_):
        self.n = None

    def __set_name__(self, owner, name):
        self.n = name

    def __get__(self, obj, cls=None):
        if obj is None:
            return self
        b = obj.__dict__.setdefault("_bound", {})
        if self.n not in b:
            b[self.n] = Bound(obj, self.n)
        return b[self.n]


class Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Any()

    def __or__(cls, o):
        return Any()


class Stub(metaclass=Meta):
    def __init__(self, *a, **k):
        self.__dict__["_st"] = {}
        self.__dict__["_bound"] = {}
        self.__dict__["_ctor"] = (a, k)
        for x in a:
            if isinstance(x, Stub) and hasattr(self, "_adopt"):
                pass

    # --- 汎用メソッド
    def __getattr__(self, name):
        if name.startswith("__") or name in ("_st", "_bound", "_ctor"):
            raise AttributeError(name)
        b = self.__dict__.setdefault("_bound", {})
        if name not in b:
            b[name] = Bound(self, name)
        return b[name]

    def _call(self, name, args, kw):
        st = self.__dict__["_st"]
        if name.startswith("set") and len(name) > 3 and len(args) > 1:
            return None
        if name.startswith("set") and len(name) > 3 and args:
            key = name[3].lower() + name[4:]
            st[key] = args[0] if len(args) == 1 else args
            if key in ("plainText", "text"):
                st["text"] = st["plainText"] = args[0]
            if key == "checked":
                st["checked"] = bool(args[0])
            if key in ("property",):
                pass
            return None
        if name == "property":
            return st.get("prop:" + str(args[0]))
        if name == "setProperty":
            st["prop:" + str(args[0])] = args[1]
            return True
        if name == "toPlainText":
            return st.get("plainText", "")
        if name in ("text", "currentText", "placeholderText"):
            return st.get(name, st.get("text", "") if name != "placeholderText" else "")
        if name.startswith("is") and name[2:3].isupper():
            key = name[2].lower() + name[3:]
            if key in st:
                return st[key]
            return name in TRUE_DEFAULT
        if name in st:
            return st[name]
        if name in NUMERIC:
            return 0
        if name in ("exec", "exec_"):
            return 0
        if name in ("isChecked",):
            return False
        if name == "parentWidget" or name == "parent" or name == "window":
            return st.get("parent") or Any()
        return Any()

    # 本物らしい挙動が要るもの
    def setParent(self, p, *a):
        self.__dict__["_st"]["parent"] = p


def _install_super_targets():
    """super().xxx() は __getattr__ を経由しないので、実際に使われる名前だけ明示メソッドとして用意する。"""
    def mk(n):
        def f(self, *a, **k):
            return self._call(n, a, k)
        f.__name__ = n
        return f
    for n in ("setText", "setGeometry", "reject", "accept", "resizeEvent", "closeEvent", "mousePressEvent",
              "mouseMoveEvent", "mouseReleaseEvent", "keyPressEvent", "focusOutEvent", "showEvent", "hideEvent"):
        if n not in Stub.__dict__:
            setattr(Stub, n, mk(n))
    Stub.eventFilter = lambda self, *a, **k: False


_install_super_targets()


class Layout(Stub):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.items = []

    def _add(self, it):
        self.items.append(it)

    def addWidget(self, w, *a, **k):
        self._add(("w", w))

    def addLayout(self, l, *a, **k):
        self._add(("l", l))

    def addItem(self, it, *a, **k):
        self._add(("i", it))

    def addSpacing(self, *a):
        self._add(("s", None))

    def addStretch(self, *a):
        self._add(("s", None))

    def insertWidget(self, i, w, *a, **k):
        self.items.insert(i, ("w", w))

    def insertLayout(self, i, l, *a, **k):
        self.items.insert(i, ("l", l))

    def count(self):
        return len(self.items)

    class _It:
        def __init__(self, kind, v):
            self.kind, self.v = kind, v

        def widget(self):
            return self.v if self.kind == "w" else None

        def layout(self):
            return self.v if self.kind == "l" else None

        def spacerItem(self):
            return None

    def itemAt(self, i):
        return Layout._It(*self.items[i]) if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return Layout._It(*self.items.pop(i)) if 0 <= i < len(self.items) else None

    def indexOf(self, w):
        for i, (k, v) in enumerate(self.items):
            if v is w:
                return i
        return -1

    def removeWidget(self, w):
        self.items = [(k, v) for k, v in self.items if v is not w]


class Combo(Stub):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.data = []
        self.idx = -1

    def addItem(self, *a):
        text = a[-2] if len(a) == 3 else a[0]
        d = a[-1] if len(a) >= 2 and not isinstance(a[-1], str) or len(a) == 3 else None
        if len(a) == 2 and isinstance(a[1], str):
            d = None
        self.data.append((text, d))
        if self.idx < 0:
            self.idx = 0

    def addItems(self, xs):
        for x in xs:
            self.addItem(x)

    def count(self):
        return len(self.data)

    def clear(self):
        self.data, self.idx = [], -1

    def currentIndex(self):
        return self.idx

    def setCurrentIndex(self, i):
        self.idx = i

    def currentText(self):
        return self.data[self.idx][0] if 0 <= self.idx < len(self.data) else ""

    def currentData(self, *a):
        return self.data[self.idx][1] if 0 <= self.idx < len(self.data) else None

    def itemData(self, i, *a):
        return self.data[i][1]

    def itemText(self, i):
        return self.data[i][0]

    def findData(self, d, *a):
        for i, (_t, v) in enumerate(self.data):
            if v == d:
                return i
        return -1

    def findText(self, t, *a):
        for i, (x, _v) in enumerate(self.data):
            if x == t:
                return i
        return -1

    def setCurrentText(self, t):
        i = self.findText(t)
        if i >= 0:
            self.idx = i


class Timer(Stub):
    singleShot_calls = []

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.active = False
        TIMERS.append(self)

    def start(self, *a):
        self.active = True

    def stop(self):
        self.active = False

    def isActive(self):
        return self.active

    @staticmethod
    def singleShot(ms, fn=None):
        if fn is not None:
            TIMERS.append(("once", fn))


class Pool(Stub):
    _inst = None

    @staticmethod
    def globalInstance():
        if Pool._inst is None:
            Pool._inst = Pool()
        return Pool._inst

    def start(self, task):
        task.run()


class Runnable(Stub):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)

    def setAutoDelete(self, *a):
        pass


class QObject(Stub):
    def __init__(self, parent=None, *a, **k):
        super().__init__()
        self.__dict__["_st"]["parent"] = parent


class App(Stub):
    _inst = None

    def __init__(self, *a, **k):
        super().__init__()
        App._inst = self

    @staticmethod
    def instance():
        if App._inst is None:
            App._inst = App()
        return App._inst


def flush_timers(max_rounds=5):
    """singleShot を実行し、アクティブな QTimer の timeout を1回ずつ発火する。"""
    for _ in range(max_rounds):
        items, TIMERS[:] = list(TIMERS), []
        ran = False
        for t in items:
            if isinstance(t, tuple):
                t[1]()
                ran = True
        if not ran:
            break


def fire_timer(timer):
    timer.active = False
    timer.timeout.emit()


SPECIAL = {"QObject": QObject, "QThreadPool": Pool, "QRunnable": Runnable, "QTimer": Timer, "QApplication": App,
           "QGuiApplication": App, "QCoreApplication": App}


def make_class(name):
    if name in SPECIAL:
        return SPECIAL[name]
    if name == "Signal":
        return Signal
    base = Stub
    if "Layout" in name:
        base = Layout
    elif name == "QComboBox" or name == "QFontComboBox":
        base = Combo
    elif name in ("QMainWindow", "QDialog", "QWidget", "QFrame") or name.startswith("Q"):
        base = Stub
    return type(name, (base,), {})


class StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = make_class(name)
        setattr(self, name, cls)
        return cls


def install():
    if "PySide6" in sys.modules and getattr(sys.modules["PySide6"], "_is_stub", False):
        return
    pkg = StubModule("PySide6")
    pkg._is_stub = True
    pkg.__path__ = []
    sys.modules["PySide6"] = pkg
    for sub in ("QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtSvg"):
        m = StubModule(f"PySide6.{sub}")
        sys.modules[f"PySide6.{sub}"] = m
        setattr(pkg, sub, m)
    # Qt 名前空間
    sys.modules["PySide6.QtCore"].Qt = type("Qt", (Stub,), {})
    sys.modules["PySide6.QtCore"].Slot = lambda *a, **k: (lambda f: f)
    sys.modules["PySide6.QtCore"].Property = lambda *a, **k: (lambda f: f)
