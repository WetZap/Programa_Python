"""Tema de la aplicación: sigue el modo claro/oscuro del sistema, en vivo.

Estilo (opción A):
* macOS → estilo nativo ``macOS`` (soporta modo oscuro).
* Windows con Qt ≥ 6.7 → estilo nativo ``windows11`` (soporta modo oscuro).
* Resto (Windows 10, Linux, BSD...) → ``Fusion`` con paleta clara u oscura según
  el sistema. Las ruedas de PySide6 no traen Breeze/GTK, así que en Linux es
  Fusion en cualquier caso.

Si el sistema no informa del esquema (``Unknown``: algunos XFCE, i3, Sway sin
portal), se deduce de la luminosidad del color de fondo de las ventanas.

Preferencia (menú Ver → Tema, guardada entre sesiones; también la variable de
entorno ``AJUSTELAB_TEMA``): ``sistema`` (por defecto), ``claro`` u ``oscuro``.
Forzar claro/oscuro usa Fusion en cualquier sistema, porque es el único estilo
cuya paleta se puede fijar de forma fiable en todas las plataformas.

Los colores de las series de la gráfica son la paleta categórica validada para
daltonismo (azul, naranja, aqua, violeta), con un paso distinto para cada modo.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

# Paleta categórica (claro, oscuro)
_SERIES = {
    "datos": ("#2a78d6", "#3987e5"),        # azul
    "ajuste": ("#eb6834", "#d95926"),       # naranja
    "interpolacion": ("#1baf7a", "#199e70"),  # aqua
    "interseccion": ("#6250d6", "#9085e9"),  # violeta
}


def _paleta_oscura() -> QPalette:
    p = QPalette()
    c = {
        QPalette.Window: "#202124", QPalette.WindowText: "#e8e8e6", QPalette.Base: "#1a1a19",
        QPalette.AlternateBase: "#26272a", QPalette.ToolTipBase: "#2b2c30", QPalette.ToolTipText: "#e8e8e6",
        QPalette.PlaceholderText: "#9a9a96", QPalette.Text: "#e8e8e6", QPalette.Button: "#2b2c30",
        QPalette.ButtonText: "#e8e8e6", QPalette.BrightText: "#ff6b6b", QPalette.Light: "#3a3b3f",
        QPalette.Midlight: "#323337", QPalette.Mid: "#3f4045", QPalette.Dark: "#151516",
        QPalette.Shadow: "#000000", QPalette.Highlight: "#3987e5", QPalette.HighlightedText: "#ffffff",
        QPalette.Link: "#6da7ec", QPalette.LinkVisited: "#9085e9",
    }
    for rol, color in c.items():
        p.setColor(rol, QColor(color))
    for rol in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, rol, QColor("#77776f"))
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#3f4045"))
    return p


def elegir_estilo() -> str:
    disponibles = {k.lower(): k for k in QStyleFactory.keys()}
    if sys.platform == "darwin" and "macos" in disponibles:
        return disponibles["macos"]
    if sys.platform.startswith("win") and "windows11" in disponibles:
        return disponibles["windows11"]
    return "Fusion"


PREFERENCIAS = ("sistema", "claro", "oscuro")


class GestorTema(QObject):
    """Aplica el estilo/paleta y avisa (``cambiado``) cuando el sistema cambia de modo."""

    cambiado = Signal()

    def __init__(self, app: QApplication, preferencia: str | None = None):
        super().__init__(app)
        self.app = app
        self.estilo_sistema = elegir_estilo()
        self.estilo = ""
        if preferencia is None:
            preferencia = os.environ.get("AJUSTELAB_TEMA") or QSettings().value("tema", "sistema")
        self.preferencia = preferencia if preferencia in PREFERENCIAS else "sistema"
        hints = app.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.aplicar())
        self.aplicar()

    def fijar_preferencia(self, preferencia: str) -> None:
        if preferencia in PREFERENCIAS:
            self.preferencia = preferencia
            QSettings().setValue("tema", preferencia)
            self.aplicar()

    def esquema_sistema(self) -> Qt.ColorScheme:
        hints = self.app.styleHints()
        return hints.colorScheme() if hasattr(hints, "colorScheme") else Qt.ColorScheme.Unknown

    def esquema(self) -> Qt.ColorScheme:
        if self.preferencia == "claro":
            return Qt.ColorScheme.Light
        if self.preferencia == "oscuro":
            return Qt.ColorScheme.Dark
        return self.esquema_sistema()

    @property
    def oscuro(self) -> bool:
        e = self.esquema()
        if e == Qt.ColorScheme.Dark:
            return True
        if e == Qt.ColorScheme.Light:
            return False
        return self.app.palette().color(QPalette.Window).lightness() < 128

    def _poner_estilo(self, nombre: str) -> None:
        if nombre != self.estilo:
            self.app.setStyle(nombre)
            self.estilo = nombre
            self.app.setPalette(self.app.style().standardPalette())

    def aplicar(self) -> None:
        self._poner_estilo(self.estilo_sistema if self.preferencia == "sistema" else "Fusion")
        if self.estilo == "Fusion":  # los estilos nativos gestionan su propia paleta
            e = self.esquema()
            if e == Qt.ColorScheme.Dark:
                self.app.setPalette(_paleta_oscura())
            elif e == Qt.ColorScheme.Light:
                self.app.setPalette(self.app.style().standardPalette())
        self.cambiado.emit()

    def colores(self) -> dict[str, str]:
        """Colores para matplotlib tomados de la paleta activa."""
        pal = self.app.palette()
        i = 1 if self.oscuro else 0
        colores = {nombre: par[i] for nombre, par in _SERIES.items()}
        texto, base = pal.color(QPalette.WindowText), pal.color(QPalette.Base)
        colores.update(
            fondo=pal.color(QPalette.Window).name(),
            ejes=base.name(),
            texto=texto.name(),
            # Mezclas opacas: PlaceholderText puede traer transparencia que matplotlib no vería
            secundario=_mezcla(texto, base, 0.6),
            excluidos=_mezcla(texto, base, 0.45),
            rejilla=_mezcla(texto, base, 0.18),
        )
        return colores


def _mezcla(a: QColor, b: QColor, t: float) -> str:
    """Color opaco a·t + b·(1 − t)."""
    return QColor(round(a.red() * t + b.red() * (1 - t)), round(a.green() * t + b.green() * (1 - t)),
                  round(a.blue() * t + b.blue() * (1 - t))).name()
