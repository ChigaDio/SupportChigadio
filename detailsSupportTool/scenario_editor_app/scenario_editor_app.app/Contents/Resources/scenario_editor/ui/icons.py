"""コードで描くアイコン (24x24 のベクタ → QIcon)。画像ファイルに依存しない。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme

_cache = {}


def _poly(p, pts, close=False):
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _draw(name, p: QPainter, col: QColor):
    pen = QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "plus":
        _poly(p, [(12, 5), (12, 19)]); _poly(p, [(5, 12), (19, 12)])
    elif name == "minus":
        _poly(p, [(5, 12), (19, 12)])
    elif name == "close":
        _poly(p, [(6, 6), (18, 18)]); _poly(p, [(18, 6), (6, 18)])
    elif name == "check":
        _poly(p, [(5, 12.5), (10, 17.5), (19, 7)])
    elif name == "trash":
        _poly(p, [(5, 7), (19, 7)]); _poly(p, [(9, 7), (9, 4.5), (15, 4.5), (15, 7)])
        _poly(p, [(7, 7), (8, 20), (16, 20), (17, 7)]); _poly(p, [(10.5, 11), (10.5, 16)]); _poly(p, [(13.5, 11), (13.5, 16)])
    elif name == "copy":
        p.drawRoundedRect(QRectF(8.5, 8.5, 11, 11), 2, 2)
        _poly(p, [(15.5, 5.5), (6.5, 5.5), (5.5, 6.5), (5.5, 15.5)])
    elif name == "edit":
        _poly(p, [(5, 19), (5.5, 15), (16, 4.5), (19.5, 8), (9, 18.5), (5, 19)])
        _poly(p, [(14, 6.5), (17.5, 10)])
    elif name == "up":
        _poly(p, [(6, 14.5), (12, 8.5), (18, 14.5)])
    elif name == "down":
        _poly(p, [(6, 9.5), (12, 15.5), (18, 9.5)])
    elif name == "left":
        _poly(p, [(14.5, 6), (8.5, 12), (14.5, 18)])
    elif name == "right":
        _poly(p, [(9.5, 6), (15.5, 12), (9.5, 18)])
    elif name == "save":
        _poly(p, [(5, 5), (16.5, 5), (19, 7.5), (19, 19), (5, 19)], True)
        _poly(p, [(8, 5), (8, 9.5), (15, 9.5), (15, 5)]); _poly(p, [(8, 19), (8, 14), (16, 14), (16, 19)])
    elif name == "search":
        p.drawEllipse(QRectF(5, 5, 10, 10)); _poly(p, [(13, 13), (19, 19)])
    elif name == "undo":
        _poly(p, [(9, 6), (5, 10), (9, 14)]); _poly(p, [(5, 10), (14, 10), (19, 13.5), (19, 18)])
    elif name == "redo":
        _poly(p, [(15, 6), (19, 10), (15, 14)]); _poly(p, [(19, 10), (10, 10), (5, 13.5), (5, 18)])
    elif name == "drag":
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        for x in (9, 15):
            for y in (7, 12, 17):
                p.drawEllipse(QPointF(x, y), 1.4, 1.4)
    elif name == "more":
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        for y in (6.5, 12, 17.5):
            p.drawEllipse(QPointF(12, y), 1.6, 1.6)
    elif name == "link":
        _poly(p, [(5, 12), (19, 12)]); _poly(p, [(14.5, 7.5), (19, 12), (14.5, 16.5)])
    elif name == "settings":
        p.drawEllipse(QRectF(9, 9, 6, 6))
        for a in range(8):
            import math
            r1, r2 = 6.5, 9
            x1 = 12 + r1 * math.cos(a * math.pi / 4); y1 = 12 + r1 * math.sin(a * math.pi / 4)
            x2 = 12 + r2 * math.cos(a * math.pi / 4); y2 = 12 + r2 * math.sin(a * math.pi / 4)
            _poly(p, [(x1, y1), (x2, y2)])
    elif name == "tune":
        _poly(p, [(5, 8), (19, 8)]); _poly(p, [(5, 16), (19, 16)])
        p.setBrush(col); p.drawEllipse(QPointF(9, 8), 2.2, 2.2); p.drawEllipse(QPointF(15, 16), 2.2, 2.2)
    elif name == "refresh":
        path = QPainterPath(); path.arcMoveTo(QRectF(5, 5, 14, 14), 40); path.arcTo(QRectF(5, 5, 14, 14), 40, 280); p.drawPath(path)
        _poly(p, [(17.5, 3.8), (17.5, 8.2), (13.2, 8.2)])
    elif name == "play":
        p.setBrush(col); _poly(p, [(8, 5.5), (18, 12), (8, 18.5)], True)
    elif name == "stop":
        p.setBrush(col); p.drawRoundedRect(QRectF(7, 7, 10, 10), 1.5, 1.5)
    elif name == "bookmark":
        _poly(p, [(7, 4.5), (17, 4.5), (17, 20), (12, 15.5), (7, 20)], True)
    elif name == "bookmark_fill":
        p.setBrush(col); _poly(p, [(7, 4.5), (17, 4.5), (17, 20), (12, 15.5), (7, 20)], True)
    elif name == "keyboard":
        p.drawRoundedRect(QRectF(3.5, 7, 17, 10.5), 2, 2)
        _poly(p, [(7, 10.5), (7.1, 10.5)]); _poly(p, [(10.5, 10.5), (10.6, 10.5)]); _poly(p, [(14, 10.5), (14.1, 10.5)]); _poly(p, [(7.5, 14), (16.5, 14)])
    elif name == "lock":
        p.drawRoundedRect(QRectF(6, 11, 12, 8.5), 2, 2)
        path = QPainterPath(); path.moveTo(8.5, 11); path.lineTo(8.5, 8.5); path.arcTo(QRectF(8.5, 4.5, 7, 8), 180, -180); path.lineTo(15.5, 11); p.drawPath(path)
    elif name == "unlock":
        p.drawRoundedRect(QRectF(6, 11, 12, 8.5), 2, 2)
        path = QPainterPath(); path.moveTo(8.5, 11); path.lineTo(8.5, 8.5); path.arcTo(QRectF(8.5, 4.5, 7, 8), 180, -180); p.drawPath(path)
    elif name == "folder":
        _poly(p, [(4, 18.5), (4, 6.5), (9.5, 6.5), (11.5, 9), (20, 9), (20, 18.5)], True)
    elif name == "events":
        p.drawRoundedRect(QRectF(4.5, 5, 15, 14), 2, 2); _poly(p, [(8, 9.5), (16, 9.5)]); _poly(p, [(8, 13), (16, 13)]); _poly(p, [(8, 16.5), (12.5, 16.5)])
    elif name == "role":
        p.drawRoundedRect(QRectF(4.5, 4.5, 6, 6), 1.5, 1.5); p.drawRoundedRect(QRectF(13.5, 4.5, 6, 6), 1.5, 1.5)
        p.drawRoundedRect(QRectF(4.5, 13.5, 6, 6), 1.5, 1.5); p.drawRoundedRect(QRectF(13.5, 13.5, 6, 6), 1.5, 1.5)
    elif name == "graph":
        p.drawEllipse(QRectF(4, 4, 5, 5)); p.drawEllipse(QRectF(15, 4, 5, 5)); p.drawEllipse(QRectF(9.5, 15, 5, 5))
        _poly(p, [(8.5, 8.5), (11, 15.5)]); _poly(p, [(15.5, 8.5), (13, 15.5)])
    elif name == "book":
        _poly(p, [(5, 5), (11.5, 6.5), (11.5, 19), (5, 17.5)], True); _poly(p, [(19, 5), (12.5, 6.5), (12.5, 19), (19, 17.5)], True)
    elif name == "tag":
        _poly(p, [(4.5, 12), (12, 4.5), (19.5, 4.5), (19.5, 12), (12, 19.5)], True); p.setBrush(col); p.drawEllipse(QPointF(15.5, 8.5), 1.3, 1.3)
    elif name == "warn":
        _poly(p, [(12, 4.5), (20, 19), (4, 19)], True); _poly(p, [(12, 10), (12, 14)]); _poly(p, [(12, 16.5), (12, 16.6)])
    elif name == "error":
        p.drawEllipse(QRectF(4, 4, 16, 16)); _poly(p, [(12, 8), (12, 13)]); _poly(p, [(12, 16), (12, 16.1)])
    elif name == "info":
        p.drawEllipse(QRectF(4, 4, 16, 16)); _poly(p, [(12, 11), (12, 16.5)]); _poly(p, [(12, 8), (12, 8.1)])
    elif name == "download":
        _poly(p, [(12, 5), (12, 15)]); _poly(p, [(7.5, 11), (12, 15.5), (16.5, 11)]); _poly(p, [(5, 19), (19, 19)])
    elif name == "upload":
        _poly(p, [(12, 15.5), (12, 5.5)]); _poly(p, [(7.5, 10), (12, 5.5), (16.5, 10)]); _poly(p, [(5, 19), (19, 19)])
    elif name == "build":
        _poly(p, [(14, 6), (18, 10), (9, 19), (5, 15), (14, 6)]); _poly(p, [(12, 8), (16, 12)])
    elif name == "paste":
        p.drawRoundedRect(QRectF(6, 6, 12, 14), 2, 2); p.drawRoundedRect(QRectF(9, 3.5, 6, 4), 1.5, 1.5)
    elif name == "collapse":
        _poly(p, [(7, 14), (12, 9), (17, 14)]); _poly(p, [(7, 19), (12, 14), (17, 19)])
    elif name == "expand":
        _poly(p, [(7, 5), (12, 10), (17, 5)]); _poly(p, [(7, 10), (12, 15), (17, 10)])
    elif name == "palette":
        p.drawEllipse(QRectF(4, 4, 16, 16)); p.setBrush(col)
        for x, y in ((9, 9), (14, 8.5), (16, 13), (8.5, 14)):
            p.drawEllipse(QPointF(x, y), 1.2, 1.2)
    elif name == "eyedropper":
        _poly(p, [(5, 19), (6, 15), (14, 7), (17, 10), (9, 18), (5, 19)]); _poly(p, [(13, 6), (18, 11)]); _poly(p, [(16, 4), (20, 8)])
    elif name == "filter":
        _poly(p, [(4.5, 6), (19.5, 6), (13.5, 13), (13.5, 19), (10.5, 17.5), (10.5, 13)], True)
    elif name == "sun":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        import math
        for a in range(8):
            ca, sa = math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)
            _poly(p, [(12 + 6.2 * ca, 12 + 6.2 * sa), (12 + 8.5 * ca, 12 + 8.5 * sa)])
    elif name == "moon":
        path = QPainterPath(); path.moveTo(16, 4.5); path.arcTo(QRectF(4.5, 4.5, 15, 15), 100, 230); path.arcTo(QRectF(8, 2.5, 13, 13), 260, -150); p.drawPath(path)
    else:  # 未知名: 丸
        p.drawEllipse(QRectF(6, 6, 12, 12))


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    col = color or theme.color("text")
    key = (name, col, size)
    if key in _cache:
        return _cache[key]
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size * scale / 24.0, size * scale / 24.0)
    _draw(name, p, QColor(col))
    p.end()
    pm.setDevicePixelRatio(scale)
    ic = QIcon(pm)
    _cache[key] = ic
    return ic


def clear_cache() -> None:
    _cache.clear()
