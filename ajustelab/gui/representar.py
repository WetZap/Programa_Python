"""Pestaña «Representar»: dibuja columnas de la tabla sin ajustar nada.

* Una columna como eje x (con su incertidumbre, si se quiere) y tantas series y
  como haga falta, cada una con su incertidumbre, su eje (izquierdo o derecho),
  su estilo (puntos, línea o ambos) y su color.
* Con series en los dos ejes se puede elegir entre un eje y a cada lado o dos
  paneles apilados con la misma x. Los dos ejes y tienen escalas independientes,
  y dónde se cruzan dos curvas depende de cómo se elijan, así que los paneles
  apilados son la opción más honesta cuando se quieren comparar formas.
* «Barras de error» enseña u oculta todas las incertidumbres a la vez.
* Los colores siguen a la serie (no a su posición): quitar una serie no cambia
  el color de las demás.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QMenu, QPushButton, QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

from ..datos import _emparejar_errores
from .grafica import ESTILOS_SERIE, PALETA_SERIES, Escena, SerieDibujo
from .iconos import icono
from .paneles import Panel
from .tabla import NINGUNA

EJES = {"izq": "Izquierdo", "der": "Derecho"}
MAX_SERIES = 8
_C_VER, _C_Y, _C_DY, _C_EJE, _C_ESTILO, _C_COLOR = range(6)


def _muestra(color: str, lado: int = 14) -> QIcon:
    pm = QPixmap(lado, lado)
    pm.fill(QColor(color))
    return QIcon(pm)


def configuracion_automatica(columnas: list[str], df=None, x_preferida: str | None = None) -> dict:
    """Propuesta inicial: x = la columna x del panel Datos (o la primera); cada
    columna que no sea una incertidumbre (dV, V_err, σV…) es una serie, con su
    incertidumbre si la hay. Con dos series de escalas muy distintas (factor ≥ 3),
    la segunda va al eje derecho."""
    pares = _emparejar_errores([str(c) for c in columnas])  # {incertidumbre: columna}
    valores = [c for c in columnas if c not in pares]
    inverso = {v: e for e, v in pares.items()}
    if not valores:
        return {"x": "", "dx": NINGUNA, "series": []}
    x = x_preferida if x_preferida in valores else valores[0]
    ys = [c for c in valores if c != x][:MAX_SERIES]
    series = [{"ver": True, "y": y, "dy": inverso.get(y, NINGUNA), "eje": "izq", "estilo": "puntos", "color": None,
               "indice": k} for k, y in enumerate(ys)]
    if len(series) == 2 and df is not None:
        escalas = []
        for s in series:
            v = np.abs(np.asarray(df[s["y"]], float))
            v = v[np.isfinite(v)]
            escalas.append(float(np.max(v)) if v.size else 0.0)
        a, b = sorted(escalas)
        if a > 0 and b / a >= 3:
            series[1]["eje"] = "der"
    return {"x": x, "dx": inverso.get(x, NINGUNA), "series": series}


class PanelRepresentar(Panel):
    titulo = "Representar"
    nombre_icono = "representar"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self._columnas: list[str] = []
        self._actualizando = False

        self.x = QComboBox()
        self.dx = QComboBox()
        self.x.setToolTip("Columna del eje x, común a todas las series")
        self.dx.setToolTip("Incertidumbre de x (barras horizontales)")
        self.barras = QCheckBox("Barras de error")
        self.barras.setChecked(True)
        self.barras.setToolTip("Enseña u oculta las incertidumbres de todas las series")
        self.disposicion = QComboBox()
        self.disposicion.addItem("Eje y a cada lado", False)
        self.disposicion.addItem("Paneles apilados", True)
        self.disposicion.setToolTip(
            "Con series en el eje derecho: un eje y a cada lado o dos paneles con la misma x.\n"
            "Las dos escalas son independientes: en un mismo panel, dónde se cruzan las curvas depende\n"
            "de las escalas elegidas. Para comparar formas, los paneles apilados son más claros.")
        self.log_y2 = QCheckBox("log y dcho.")
        self.log_y2.setToolTip("Escala logarítmica en el eje derecho (o en el panel inferior)")
        for w in (self.x, self.dx, self.disposicion):
            w.currentIndexChanged.connect(self._cambio)
        self.barras.toggled.connect(self._cambio)
        self.log_y2.toggled.connect(self._al_log_y2)

        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(["Ver", "Columna", "Incertidumbre", "Eje y", "Estilo", "Color"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        cab = self.tabla.horizontalHeader()
        for col, modo in ((_C_VER, QHeaderView.ResizeToContents), (_C_Y, QHeaderView.Stretch),
                          (_C_DY, QHeaderView.Stretch), (_C_EJE, QHeaderView.ResizeToContents),
                          (_C_ESTILO, QHeaderView.ResizeToContents), (_C_COLOR, QHeaderView.ResizeToContents)):
            cab.setSectionResizeMode(col, modo)
        self.tabla.itemChanged.connect(lambda _: self._cambio())

        b_anadir = QPushButton(icono("anadir"), "Añadir serie")
        b_anadir.clicked.connect(lambda: self.anadir_serie())
        self.b_quitar = QPushButton(icono("quitar"), "Quitar")
        self.b_quitar.clicked.connect(self.quitar_serie)
        b_auto = QPushButton(icono("estimar"), "Automático")
        b_auto.setToolTip("Vuelve a proponer las series a partir de los nombres de las columnas")
        b_auto.clicked.connect(lambda: self.configurar(automatico=True))

        form = QFormLayout()
        form.addRow("Eje x:", self.x)
        form.addRow("Incertidumbre x:", self.dx)
        form.addRow("Con eje derecho:", self.disposicion)
        opciones = QHBoxLayout()
        opciones.addWidget(self.barras)
        opciones.addWidget(self.log_y2)
        opciones.addStretch(1)
        form.addRow(opciones)
        nota = QLabel("Sin ajuste: solo los datos. Clic en un punto para excluir su fila.")
        nota.setObjectName("secundario")
        nota.setWordWrap(True)
        izquierda = QVBoxLayout()
        izquierda.addLayout(form)
        izquierda.addStretch(1)
        izquierda.addWidget(nota)

        botones = QHBoxLayout()
        botones.addWidget(b_anadir)
        botones.addWidget(self.b_quitar)
        botones.addStretch(1)
        botones.addWidget(b_auto)
        derecha = QVBoxLayout()
        derecha.addWidget(self.tabla, 1)
        derecha.addLayout(botones)

        capa = QHBoxLayout(self)
        caja = QWidget()
        caja.setLayout(izquierda)
        caja.setMaximumWidth(330)
        capa.addWidget(caja)
        capa.addLayout(derecha, 1)
        tema = getattr(ventana, "tema", None)
        if tema is not None:
            tema.cambiado.connect(self._pintar_colores)

    # -- columnas -------------------------------------------------------------
    def _modelo(self):
        return self.ventana.panel_datos.modelo

    def _rellenar(self, combo: QComboBox, opciones: list[str], actual: str | None) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(opciones)
        if actual in opciones:
            combo.setCurrentText(actual)
        combo.blockSignals(False)

    def _sincronizar_columnas(self) -> None:
        """Si han cambiado las columnas de la tabla, se rehacen las listas. Si es
        otra tabla, o las series apuntan a columnas que ya no existen, se vuelve
        a proponer la configuración automática."""
        columnas = self._modelo().nombres
        if columnas == self._columnas:
            return
        antes = self._columnas
        self._columnas = list(columnas)
        if not columnas:
            return
        series = self._series_config()
        validas = bool(series) and all(s["y"] in columnas for s in series) and self.x.currentText() in columnas
        if not antes or not validas:
            self.configurar(automatico=True)
        else:
            self.configurar(self.estado())

    # -- filas de la tabla -----------------------------------------------------
    def _indice_libre(self) -> int:
        usados = {s["indice"] for s in self._series_config()}
        return next((k for k in range(MAX_SERIES) if k not in usados), len(usados))

    def anadir_serie(self, cfg: dict | None = None) -> None:
        if self.tabla.rowCount() >= MAX_SERIES:
            self.ventana.notificar(f"Como mucho {MAX_SERIES} series: con más, los colores ya no se distinguen.",
                                   "aviso")
            return
        if cfg is None:
            usadas = {s["y"] for s in self._series_config()} | {self.x.currentText()}
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
        self.tabla.setItem(f, _C_VER, ver)

        y = QComboBox()
        self._rellenar(y, self._columnas, cfg.get("y"))
        dy = QComboBox()
        self._rellenar(dy, [NINGUNA, *self._columnas], cfg.get("dy", NINGUNA))
        eje = QComboBox()
        for k, v in EJES.items():
            eje.addItem(v, k)
        eje.setCurrentIndex(max(0, eje.findData(cfg.get("eje", "izq"))))
        estilo = QComboBox()
        for k, v in ESTILOS_SERIE.items():
            estilo.addItem(v, k)
        estilo.setCurrentIndex(max(0, estilo.findData(cfg.get("estilo", "puntos"))))
        for w in (y, dy, eje, estilo):
            w.currentIndexChanged.connect(self._cambio)
        color = QToolButton()
        color.setAutoRaise(True)
        color.clicked.connect(lambda _=False, b=color: self._elegir_color(b))
        color.setContextMenuPolicy(Qt.CustomContextMenu)
        color.customContextMenuRequested.connect(lambda _p, b=color: self._menu_color(b))
        for col, w in ((_C_Y, y), (_C_DY, dy), (_C_EJE, eje), (_C_ESTILO, estilo), (_C_COLOR, color)):
            self.tabla.setCellWidget(f, col, w)
        self._actualizando = False
        self._pintar_colores()
        self._cambio()

    def quitar_serie(self) -> None:
        f = self.tabla.currentRow()
        if f < 0:
            f = self.tabla.rowCount() - 1
        if f >= 0:
            self.tabla.removeRow(f)
            self._cambio()

    def _fila_de_boton(self, boton) -> int:
        for f in range(self.tabla.rowCount()):
            if self.tabla.cellWidget(f, _C_COLOR) is boton:
                return f
        return -1

    def _meta(self, f: int) -> dict:
        return dict(self.tabla.item(f, _C_VER).data(Qt.UserRole) or {})

    def _fijar_meta(self, f: int, meta: dict) -> None:
        self.tabla.item(f, _C_VER).setData(Qt.UserRole, meta)

    def _elegir_color(self, boton) -> None:
        f = self._fila_de_boton(boton)
        if f < 0:
            return
        meta = self._meta(f)
        inicial = QColor(meta.get("color") or self._color_auto(meta.get("indice", f)))
        color = QColorDialog.getColor(inicial, self, "Color de la serie")
        if color.isValid():
            meta["color"] = color.name()
            self._fijar_meta(f, meta)
            self._pintar_colores()
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
        self._pintar_colores()
        self._cambio()

    def _color_auto(self, indice: int) -> str:
        paleta = PALETA_SERIES[self.ventana.tema.oscuro]
        return paleta[indice % len(paleta)]

    def _pintar_colores(self) -> None:
        for f in range(self.tabla.rowCount()):
            meta = self._meta(f)
            color = meta.get("color") or self._color_auto(meta.get("indice", f))
            b = self.tabla.cellWidget(f, _C_COLOR)
            if b is not None:
                b.setIcon(_muestra(color))
                b.setToolTip(f"{color} ({'elegido' if meta.get('color') else 'automático'}). "
                             "Clic para cambiarlo; clic derecho para volver al automático.")

    def _series_config(self) -> list[dict]:
        series = []
        for f in range(self.tabla.rowCount()):
            item = self.tabla.item(f, _C_VER)
            if item is None:
                continue
            meta = self._meta(f)
            series.append({
                "ver": item.checkState() == Qt.Checked,
                "y": self.tabla.cellWidget(f, _C_Y).currentText(),
                "dy": self.tabla.cellWidget(f, _C_DY).currentText(),
                "eje": self.tabla.cellWidget(f, _C_EJE).currentData(),
                "estilo": self.tabla.cellWidget(f, _C_ESTILO).currentData(),
                "color": meta.get("color"),
                "indice": int(meta.get("indice", f)),
            })
        return series

    # -- configuración completa ---------------------------------------------
    def configurar(self, cfg: dict | None = None, automatico: bool = False) -> None:
        if automatico or cfg is None:
            modelo = self._modelo()
            x_datos = self.ventana.panel_datos.combos["x"].currentText()
            cfg = {**configuracion_automatica(modelo.nombres, modelo.a_dataframe(), x_datos),
                   "barras": self.barras.isChecked(), "apilados": self.disposicion.currentData()}
        self._columnas = list(self._modelo().nombres)
        self._actualizando = True
        self._rellenar(self.x, self._columnas, cfg.get("x"))
        self._rellenar(self.dx, [NINGUNA, *self._columnas], cfg.get("dx", NINGUNA))
        self.barras.blockSignals(True)
        self.barras.setChecked(bool(cfg.get("barras", True)))
        self.barras.blockSignals(False)
        self.disposicion.blockSignals(True)
        self.disposicion.setCurrentIndex(1 if cfg.get("apilados") else 0)
        self.disposicion.blockSignals(False)
        self.tabla.setRowCount(0)
        self._actualizando = False
        for s in cfg.get("series", []):
            self.anadir_serie(s)
        self._cambio()

    def _cambio(self, *_):
        if self._actualizando:
            return
        self.b_quitar.setEnabled(self.tabla.rowCount() > 0)
        if self.ventana.pestanas.currentWidget() is self:
            self.ventana.actualizar_grafica()

    def _al_log_y2(self, activo: bool) -> None:
        self.ventana.grafica.opciones.log_y2 = activo
        self._cambio()

    # -- escena -----------------------------------------------------------------
    def escena_tabla(self) -> Escena:
        """La escena se construye directamente de la tabla (no hace falta que las
        columnas x/y del panel Datos sean válidas para un ajuste)."""
        self._sincronizar_columnas()
        modelo = self._modelo()
        df = modelo.a_dataframe()
        cx = self.x.currentText()
        if df.empty or cx not in df:
            return Escena()
        self.log_y2.blockSignals(True)
        self.log_y2.setChecked(self.ventana.grafica.opciones.log_y2)
        self.log_y2.blockSignals(False)
        x = df[cx].to_numpy(float)
        cdx = self.dx.currentText()
        dx = np.abs(df[cdx].to_numpy(float)) if cdx in df else None
        excluidas = list(modelo.excluidas)
        series = []
        for s in self._series_config():
            if not s["ver"] or s["y"] not in df:
                continue
            y = df[s["y"]].to_numpy(float)
            validas = np.isfinite(x) & np.isfinite(y)
            if not validas.any():
                continue
            filas = np.flatnonzero(validas)
            dy = np.abs(df[s["dy"]].to_numpy(float))[validas] if s["dy"] in df else None
            series.append(SerieDibujo(
                nombre=s["y"], x=x[validas], y=y[validas], dx=None if dx is None else dx[validas], dy=dy,
                incluidos=~np.isin(filas, excluidas), filas=filas, eje=s["eje"] or "izq",
                estilo=s["estilo"] or "puntos", color=s["color"], indice=s["indice"]))
        return Escena(series=series, nombre_x=cx, apilados=bool(self.disposicion.currentData()),
                      barras_error=self.barras.isChecked())

    def escena(self, datos, filas) -> Escena:
        return self.escena_tabla()

    def ejecutar(self) -> None:
        self.ventana.actualizar_grafica()

    def recalcular(self) -> None:
        self.ventana.actualizar_grafica()

    def reiniciar(self) -> None:
        self._columnas = []
        self.tabla.setRowCount(0)

    def texto_informe(self) -> str:
        lineas = [f"Representación de {len(self._series_config())} series frente a {self.x.currentText()}"]
        for s in self._series_config():
            lineas.append(f"  {'✓' if s['ver'] else '·'} {s['y']}"
                          + (f" ± {s['dy']}" if s["dy"] != NINGUNA else "") + f"  (eje {EJES.get(s['eje'], '?')})")
        return "\n".join(lineas)

    # -- sesiones ---------------------------------------------------------------
    def estado(self) -> dict:
        return {"x": self.x.currentText(), "dx": self.dx.currentText(), "barras": self.barras.isChecked(),
                "apilados": bool(self.disposicion.currentData()), "series": self._series_config()}

    def restaurar(self, e: dict) -> None:
        if e:
            self.configurar(e)
