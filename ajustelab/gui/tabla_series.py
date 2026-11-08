"""Tabla de series de «Representar»: una fila por serie con los campos que pida
cada tipo de gráfica (ver, columna, incertidumbre, eje, estilo y color)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QColorDialog, QComboBox, QHBoxLayout, QHeaderView, QMenu,
                               QPushButton, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .grafica import ESTILOS_SERIE, PALETA_SERIES
from .iconos import icono
from .tabla import NINGUNA

EJES = {"izq": "Izquierdo", "der": "Derecho"}
MAX_SERIES = 8
_CAMPOS = {"ver": "Ver", "y": "Columna", "dy": "Incertidumbre", "eje": "Eje y", "estilo": "Estilo", "color": "Color"}


def _muestra(color: str, lado: int = 14) -> QIcon:
    pm = QPixmap(lado, lado)
    pm.fill(QColor(color))
    return QIcon(pm)



class TablaSeries(QWidget):
    """Lista de series (una fila cada una) con los campos pedidos: ver, columna,
    incertidumbre, eje, estilo y color. Botones para añadir y quitar.
    ``panel``: el panel dueño (de él se toman el tema y los avisos de la ventana)."""

    cambiado = Signal()

    def __init__(self, panel, campos=tuple(_CAMPOS), cabecera_y: str = "Columna",
                 excluir: Callable[[], set] | None = None, automatico: Callable[[], None] | None = None):
        super().__init__()
        self.panel = panel
        self.campos = tuple(campos)
        self.col = {c: i for i, c in enumerate(self.campos)}
        self._columnas: list[str] = []
        self._excluir = excluir or (lambda: set())
        self._actualizando = False

        self.tabla = QTableWidget(0, len(self.campos))
        self.tabla.setHorizontalHeaderLabels([cabecera_y if c == "y" else _CAMPOS[c] for c in self.campos])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        cab = self.tabla.horizontalHeader()
        for c, i in self.col.items():
            cab.setSectionResizeMode(i, QHeaderView.Stretch if c in ("y", "dy") else QHeaderView.ResizeToContents)
        self.tabla.itemChanged.connect(lambda _: self._cambio())

        b_anadir = QPushButton(icono("anadir"), "Añadir")
        b_anadir.clicked.connect(lambda: self.anadir())
        self.b_quitar = QPushButton(icono("quitar"), "Quitar")
        self.b_quitar.clicked.connect(self.quitar)
        botones = QHBoxLayout()
        botones.addWidget(b_anadir)
        botones.addWidget(self.b_quitar)
        botones.addStretch(1)
        if automatico is not None:
            b_auto = QPushButton(icono("estimar"), "Automático")
            b_auto.setToolTip("Vuelve a proponer las series a partir de los nombres de las columnas")
            b_auto.clicked.connect(automatico)
            botones.addWidget(b_auto)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.tabla, 1)
        capa.addLayout(botones)

    # -- columnas disponibles ---------------------------------------------------
    def fijar_columnas(self, columnas: list[str]) -> None:
        self._columnas = list(columnas)

    @staticmethod
    def _rellenar(combo: QComboBox, opciones: list[str], actual: str | None) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(opciones)
        if actual in opciones:
            combo.setCurrentText(actual)
        combo.blockSignals(False)

    # -- filas ---------------------------------------------------------------------
    def _indice_libre(self) -> int:
        usados = {s["indice"] for s in self.config()}
        return next((k for k in range(MAX_SERIES) if k not in usados), len(usados))

    def anadir(self, cfg: dict | None = None) -> None:
        if self.tabla.rowCount() >= MAX_SERIES:
            self.panel.ventana.notificar(
                f"Como mucho {MAX_SERIES} series: con más, los colores ya no se distinguen.", "aviso")
            return
        if cfg is None:
            usadas = {s["y"] for s in self.config()} | self._excluir()
            libre = next((c for c in self._columnas if c not in usadas), self._columnas[0] if self._columnas else "")
            cfg = {"ver": True, "y": libre, "dy": NINGUNA, "eje": "izq", "estilo": "puntos", "color": None,
                   "indice": self._indice_libre()}
        self._actualizando = True
        f = self.tabla.rowCount()
        self.tabla.insertRow(f)
        ver = QTableWidgetItem()
        ver.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        ver.setCheckState(Qt.Checked if cfg.get("ver", True) else Qt.Unchecked)
        ver.setData(Qt.UserRole, {"indice": int(cfg.get("indice", f)), "color": cfg.get("color")})
        self.tabla.setItem(f, self.col["ver"], ver)  # «ver» siempre está: guarda el índice y el color
        widgets = {}
        if "y" in self.col:
            widgets["y"] = QComboBox()
            self._rellenar(widgets["y"], self._columnas, cfg.get("y"))
        if "dy" in self.col:
            widgets["dy"] = QComboBox()
            self._rellenar(widgets["dy"], [NINGUNA, *self._columnas], cfg.get("dy", NINGUNA))
        if "eje" in self.col:
            widgets["eje"] = QComboBox()
            for k, v in EJES.items():
                widgets["eje"].addItem(v, k)
            widgets["eje"].setCurrentIndex(max(0, widgets["eje"].findData(cfg.get("eje", "izq"))))
        if "estilo" in self.col:
            widgets["estilo"] = QComboBox()
            for k, v in ESTILOS_SERIE.items():
                widgets["estilo"].addItem(v, k)
            widgets["estilo"].setCurrentIndex(max(0, widgets["estilo"].findData(cfg.get("estilo", "puntos"))))
        for w in widgets.values():
            w.currentIndexChanged.connect(self._cambio)
        if "color" in self.col:
            color = QToolButton()
            color.setAutoRaise(True)
            color.clicked.connect(lambda _=False, b=color: self.elegir_color(b))
            color.setContextMenuPolicy(Qt.CustomContextMenu)
            color.customContextMenuRequested.connect(lambda _p, b=color: self._menu_color(b))
            widgets["color"] = color
        for campo, w in widgets.items():
            self.tabla.setCellWidget(f, self.col[campo], w)
        self._actualizando = False
        self.pintar_colores()
        self._cambio()

    def quitar(self) -> None:
        f = self.tabla.currentRow()
        if f < 0:
            f = self.tabla.rowCount() - 1
        if f >= 0:
            self.tabla.removeRow(f)
            self._cambio()

    def configurar(self, series: list[dict]) -> None:
        self._actualizando = True
        self.tabla.setRowCount(0)
        self._actualizando = False
        for s in series[:MAX_SERIES]:
            self.anadir(s)
        self._cambio()

    def _fila_de_boton(self, boton) -> int:
        for f in range(self.tabla.rowCount()):
            if self.tabla.cellWidget(f, self.col["color"]) is boton:
                return f
        return -1

    def _meta(self, f: int) -> dict:
        return dict(self.tabla.item(f, self.col["ver"]).data(Qt.UserRole) or {})

    def _fijar_meta(self, f: int, meta: dict) -> None:
        self.tabla.item(f, self.col["ver"]).setData(Qt.UserRole, meta)

    def elegir_color(self, boton) -> None:
        f = self._fila_de_boton(boton)
        if f < 0:
            return
        meta = self._meta(f)
        inicial = QColor(meta.get("color") or self._color_auto(meta.get("indice", f)))
        color = QColorDialog.getColor(inicial, self, "Color de la serie")
        if color.isValid():
            meta["color"] = color.name()
            self._fijar_meta(f, meta)
            self.pintar_colores()
            self._cambio()

    def _menu_color(self, boton) -> None:
        f = self._fila_de_boton(boton)
        if f < 0:
            return
        menu = QMenu(self)
        menu.addAction("Color automático", lambda: self._color_automatico(f))
        menu.exec(boton.mapToGlobal(boton.rect().bottomLeft()))

    def _color_automatico(self, f: int) -> None:
        meta = self._meta(f)
        meta["color"] = None
        self._fijar_meta(f, meta)
        self.pintar_colores()
        self._cambio()

    def _color_auto(self, indice: int) -> str:
        paleta = PALETA_SERIES[self.panel.ventana.tema.oscuro]
        return paleta[indice % len(paleta)]

    def pintar_colores(self) -> None:
        if "color" not in self.col:
            return
        for f in range(self.tabla.rowCount()):
            meta = self._meta(f)
            color = meta.get("color") or self._color_auto(meta.get("indice", f))
            b = self.tabla.cellWidget(f, self.col["color"])
            if b is not None:
                b.setIcon(_muestra(color))
                b.setToolTip(f"{color} ({'elegido' if meta.get('color') else 'automático'}). "
                             "Clic para cambiarlo; clic derecho para volver al automático.")

    def config(self) -> list[dict]:
        series = []
        for f in range(self.tabla.rowCount()):
            item = self.tabla.item(f, self.col["ver"])
            if item is None:
                continue
            meta = self._meta(f)

            def valor(campo, defecto, datos=False):
                if campo not in self.col:
                    return defecto
                w = self.tabla.cellWidget(f, self.col[campo])
                return (w.currentData() if datos else w.currentText()) if w is not None else defecto

            series.append({
                "ver": item.checkState() == Qt.Checked,
                "y": valor("y", ""),
                "dy": valor("dy", NINGUNA),
                "eje": valor("eje", "izq", True),
                "estilo": valor("estilo", "puntos", True),
                "color": meta.get("color"),
                "indice": int(meta.get("indice", f)),
            })
        return series

    def _cambio(self, *_):
        if self._actualizando:
            return
        self.b_quitar.setEnabled(self.tabla.rowCount() > 0)
        self.cambiado.emit()
