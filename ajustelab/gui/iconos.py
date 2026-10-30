"""Iconos de la interfaz.

Se dibujan aquí con QPainter, en el color del texto de la paleta activa en el
momento de pintarse: se ven nítidos a cualquier escala, cambian solos entre modo
claro y oscuro, todos tienen el mismo estilo y no hacen falta ficheros de imagen.

Con ``icono(nombre, nativo=True)`` se prefieren los iconos de tema del sistema
cuando existen (Windows 11, macOS o Linux con un tema de iconos, Qt ≥ 6.7).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QIconEngine, QPainter, QPainterPath, QPalette, QPen, QPixmap

_Dibujo = Callable[[QPainter], None]


class _MotorIcono(QIconEngine):
    """Pinta un dibujo definido en una rejilla de 24×24 con el color del texto."""

    def __init__(self, dibujo: _Dibujo):
        super().__init__()
        self._dibujo = dibujo

    def clone(self):
        return _MotorIcono(self._dibujo)

    def paint(self, painter: QPainter, rect, mode, state):
        pal = QGuiApplication.palette()
        grupo = QPalette.Disabled if mode == QIcon.Disabled else QPalette.Active
        color = pal.color(grupo, QPalette.ButtonText if mode != QIcon.Selected else QPalette.HighlightedText)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        lado = min(rect.width(), rect.height())
        painter.translate(rect.x() + (rect.width() - lado) / 2, rect.y() + (rect.height() - lado) / 2)
        painter.scale(lado / 24, lado / 24)
        pen = QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        self._dibujo(painter)
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        self.paint(p, QRectF(0, 0, size.width(), size.height()).toRect(), mode, state)
        p.end()
        return pm


def _ruta(*puntos) -> QPainterPath:
    r = QPainterPath(QPointF(*puntos[0]))
    for pt in puntos[1:]:
        r.lineTo(QPointF(*pt))
    return r


# --- dibujos (rejilla 24×24) -------------------------------------------------
def _abrir(p):
    p.drawPath(_ruta((3, 19), (3, 6), (9, 6), (11, 8), (19, 8), (19, 11)))
    p.drawPath(_ruta((3, 19), (6, 11), (21, 11), (18, 19), (3, 19)))


def _guardar(p):
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2)
    p.drawRect(QRectF(8, 4, 8, 5))
    p.drawRoundedRect(QRectF(7, 13, 10, 7), 1, 1)


def _nuevo(p):
    p.drawPath(_ruta((6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3)))
    p.drawPath(_ruta((14, 3), (14, 8), (19, 8)))
    p.drawLine(QPointF(12.5, 11), QPointF(12.5, 18))
    p.drawLine(QPointF(9, 14.5), QPointF(16, 14.5))


def _deshacer(p):
    r = QPainterPath(QPointF(9, 6))
    r.lineTo(4, 11)
    r.lineTo(9, 16)
    p.drawPath(r)
    c = QPainterPath(QPointF(4, 11))
    c.lineTo(14, 11)
    c.cubicTo(18, 11, 20, 13, 20, 16)
    c.cubicTo(20, 18, 19, 19, 18, 20)
    p.drawPath(c)


def _rehacer(p):
    p.save()
    p.translate(24, 0)
    p.scale(-1, 1)
    _deshacer(p)
    p.restore()


def _pegar(p):
    p.drawRoundedRect(QRectF(5, 5, 14, 16), 2, 2)
    p.drawRoundedRect(QRectF(9, 3, 6, 4), 1, 1)
    for y in (11, 14.5, 18):
        p.drawLine(QPointF(8.5, y), QPointF(15.5, y))


def _copiar(p):
    p.drawRoundedRect(QRectF(8, 8, 12, 13), 2, 2)
    p.drawPath(_ruta((16, 8), (16, 4), (4, 4), (4, 17), (8, 17)))


def _exportar(p):
    p.drawRoundedRect(QRectF(3, 5, 18, 14), 2, 2)
    p.drawPath(_ruta((3, 16), (9, 10), (13, 14), (16, 11), (21, 16)))
    p.drawEllipse(QPointF(16, 8.5), 1.4, 1.4)


def _ajustar(p):
    c = QPainterPath(QPointF(3, 19))
    c.cubicTo(8, 18, 10, 6, 21, 5)
    p.drawPath(c)
    p.save()
    p.setBrush(p.pen().color())
    for x, y in ((5, 16), (9, 14.5), (12, 9), (16, 7.5), (19.5, 6.5)):
        p.drawEllipse(QPointF(x, y), 1.3, 1.3)
    p.restore()


def _region(p):
    pen = p.pen()
    pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.drawRoundedRect(QRectF(4, 6, 16, 12), 1.5, 1.5)
    pen.setStyle(Qt.SolidLine)
    p.setPen(pen)
    p.setBrush(pen.color())
    for x, y in ((8, 14), (12, 10), (16, 13)):
        p.drawEllipse(QPointF(x, y), 1.3, 1.3)


def _rango(p):
    p.drawLine(QPointF(5, 4), QPointF(5, 20))
    p.drawLine(QPointF(19, 4), QPointF(19, 20))
    p.drawLine(QPointF(8, 12), QPointF(16, 12))
    p.drawPath(_ruta((10, 9.5), (7.5, 12), (10, 14.5)))
    p.drawPath(_ruta((14, 9.5), (16.5, 12), (14, 14.5)))


def _personalizar(p):
    for y, x in ((7, 15), (12, 8), (17, 13)):
        p.drawLine(QPointF(4, y), QPointF(20, y))
        p.save()
        p.setBrush(QGuiApplication.palette().color(QPalette.Base))
        p.drawEllipse(QPointF(x, y), 2.2, 2.2)
        p.restore()


def _seleccion(p):
    for y in (6, 12, 18):
        p.drawLine(QPointF(10, y), QPointF(20, y))
    estrella = QPainterPath()
    import math
    for i in range(10):
        r = 3 if i % 2 == 0 else 1.3
        a = -math.pi / 2 + i * math.pi / 5
        pt = QPointF(5 + r * math.cos(a), 6 + r * math.sin(a))
        estrella.moveTo(pt) if i == 0 else estrella.lineTo(pt)
    estrella.closeSubpath()
    p.save()
    p.setBrush(p.pen().color())
    p.drawPath(estrella)
    p.restore()
    p.drawEllipse(QPointF(5, 12), 1.2, 1.2)
    p.drawEllipse(QPointF(5, 18), 1.2, 1.2)


def _ejemplo(p):
    p.drawPath(_ruta((9, 3), (15, 3)))
    p.drawPath(_ruta((10, 3), (10, 9), (4.5, 19), (5.5, 21), (18.5, 21), (19.5, 19), (14, 9), (14, 3)))
    p.drawLine(QPointF(7, 15), QPointF(17, 15))


def _info(p):
    p.drawEllipse(QPointF(12, 12), 9, 9)
    p.drawLine(QPointF(12, 11), QPointF(12, 17))
    p.save()
    p.setBrush(p.pen().color())
    p.drawEllipse(QPointF(12, 7.5), 0.6, 0.6)
    p.restore()


def _quitar(p):
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _estimar(p):  # varita
    p.drawLine(QPointF(4, 20), QPointF(15, 9))
    for a, b in (((17, 3), (17, 6)), ((21, 7), (18, 7)), ((20, 3.5), (18.5, 5)), ((13.5, 5.5), (14.5, 6.5))):
        p.drawLine(QPointF(*a), QPointF(*b))


def _flecha_abajo(p):
    p.drawLine(QPointF(12, 4), QPointF(12, 16))
    p.drawPath(_ruta((7, 11), (12, 16), (17, 11)))
    p.drawLine(QPointF(5, 20), QPointF(19, 20))


_DIBUJOS: dict[str, _Dibujo] = {
    "abrir": _abrir, "guardar": _guardar, "nuevo": _nuevo, "deshacer": _deshacer, "rehacer": _rehacer,
    "pegar": _pegar, "copiar": _copiar, "exportar": _exportar, "ajustar": _ajustar, "region": _region,
    "rango": _rango, "personalizar": _personalizar, "seleccion": _seleccion, "ejemplo": _ejemplo,
    "info": _info, "quitar": _quitar, "estimar": _estimar, "usar": _flecha_abajo,
}

# Equivalencias con los iconos de tema de Qt ≥ 6.7 (nombre del enum) y freedesktop
_TEMA = {
    "abrir": ("DocumentOpen", "document-open"), "guardar": ("DocumentSave", "document-save"),
    "nuevo": ("DocumentNew", "document-new"), "deshacer": ("EditUndo", "edit-undo"),
    "rehacer": ("EditRedo", "edit-redo"), "pegar": ("EditPaste", "edit-paste"),
    "copiar": ("EditCopy", "edit-copy"), "info": ("HelpAbout", "help-about"),
}

_cache: dict[str, QIcon] = {}


def icono(nombre: str, nativo: bool = False) -> QIcon:
    """Icono por nombre (ver ``_DIBUJOS``). Por defecto se usa el juego propio para
    que todos los iconos tengan el mismo estilo; ``nativo=True`` prefiere los del sistema."""
    clave = f"{nombre}:{nativo}"
    if clave in _cache:
        return _cache[clave]
    ic = QIcon()
    if nativo and nombre in _TEMA:
        enum, freedesktop = _TEMA[nombre]
        tema_enum = getattr(getattr(QIcon, "ThemeIcon", None), enum, None)
        if tema_enum is not None:
            ic = QIcon.fromTheme(tema_enum)
        if ic.isNull():
            ic = QIcon.fromTheme(freedesktop)
    if ic.isNull():
        ic = QIcon(_MotorIcono(_DIBUJOS[nombre]))
    _cache[clave] = ic
    return ic
