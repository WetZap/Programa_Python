"""Pestaña «Representar»: dibuja columnas de la tabla sin ajustar nada.

Tipos de gráfica (selector «Tipo»):

* **Puntos x-y**: una columna como eje x y varias series y, cada una con su
  incertidumbre, su eje (izquierdo o derecho), su estilo y su color. Con series en
  los dos ejes, un eje y a cada lado o dos paneles apilados. El eje x se puede
  partir (cortes «//») para quitar tramos sin datos: a mano, con la herramienta
  «Cortar» de la gráfica o detectando los huecos automáticamente.
* **Histograma** de una o varias columnas (mismos intervalos), con errores √N,
  normalización y ajuste de una distribución (normal, Poisson, exponencial) con test χ².
* **Barras**: categorías (columna de texto, de números o el número de fila) y una o
  varias series de valores con su incertidumbre.
* **Sectores**: una columna de valores con sus etiquetas (anillo o tarta).
* **Cajas / violín** de varias columnas.
* **Polar**: ángulo (grados o radianes) y una o varias series de radios.

Los colores siguen a la serie (no a su posición): quitar una serie no cambia el
color de las demás. Las filas excluidas no cuentan en histogramas, barras, sectores
ni cajas; en x-y y polar se ven huecas.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QPlainTextEdit,
                               QPushButton, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

from ..datos import _emparejar_errores
from ..histograma import DISTRIBUCIONES, NORMALIZACIONES, REGLAS, resumen
from .grafica import ESTILOS_SERIE, PALETA_SERIES, Escena, SerieDibujo, detectar_huecos, fusionar_cortes
from .graficas import (TIPOS, Aviso, BarrasGrafica, CajasGrafica, CircularGrafica, Columna, ErrorGrafica,
                       PolarGrafica, construir_histograma, ordenar_categorias, preparar_sectores)
from .iconos import icono
from .paneles import Panel
from .tabla import NINGUNA

EJES = {"izq": "Izquierdo", "der": "Derecho"}
MAX_SERIES = 8
FILA = "(número de fila)"
_CAMPOS = {"ver": "Ver", "y": "Columna", "dy": "Incertidumbre", "eje": "Eje y", "estilo": "Estilo", "color": "Color"}
# Compatibilidad: posiciones de las columnas en la tabla de series x-y
_C_VER, _C_Y, _C_DY, _C_EJE, _C_ESTILO, _C_COLOR = range(6)


def _muestra(color: str, lado: int = 14) -> QIcon:
    pm = QPixmap(lado, lado)
    pm.fill(QColor(color))
    return QIcon(pm)


def _numero(texto: str) -> float | None:
    try:
        return float(texto.strip().replace(",", "."))
    except ValueError:
        return None


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


class TablaSeries(QWidget):
    """Lista de series (una fila cada una) con los campos pedidos: ver, columna,
    incertidumbre, eje, estilo y color. Botones para añadir y quitar."""

    cambiado = Signal()

    def __init__(self, panel: "PanelRepresentar", campos=tuple(_CAMPOS), cabecera_y: str = "Columna",
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


class PanelRepresentar(Panel):
    titulo = "Representar"
    nombre_icono = "representar"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self._columnas: list[str] = []
        self._actualizando = False
        self.cortes: list[tuple[float, float]] = []
        self._resumen_histograma = ""

        self.tipo = QComboBox()
        for k, v in TIPOS.items():
            self.tipo.addItem(v, k)
        self.tipo.setToolTip("Tipo de gráfica")
        self.tipo.currentIndexChanged.connect(self._al_cambiar_tipo)
        self.izquierda = QStackedWidget()
        self.derecha = QStackedWidget()
        self._paginas: dict[str, int] = {}
        self._construir_xy()
        self._construir_histograma()
        self._construir_barras()
        self._construir_circular()
        self._construir_cajas()
        self._construir_polar()

        self.nota = QLabel()
        self.nota.setObjectName("secundario")
        self.nota.setWordWrap(True)
        cabecera = QFormLayout()
        cabecera.addRow("Tipo:", self.tipo)
        columna_izq = QVBoxLayout()
        columna_izq.addLayout(cabecera)
        columna_izq.addWidget(self.izquierda)
        columna_izq.addStretch(1)
        columna_izq.addWidget(self.nota)
        caja = QWidget()
        caja.setLayout(columna_izq)
        caja.setMaximumWidth(340)
        capa = QHBoxLayout(self)
        capa.addWidget(caja)
        capa.addWidget(self.derecha, 1)
        tema = getattr(ventana, "tema", None)
        if tema is not None:
            tema.cambiado.connect(self._pintar_colores)
        self._al_cambiar_tipo()

    # -- construcción de las páginas ---------------------------------------------------
    def _pagina(self, clave: str, izquierda: QWidget, derecha: QWidget) -> None:
        self._paginas[clave] = self.izquierda.addWidget(izquierda)
        self.derecha.addWidget(derecha)

    @staticmethod
    def _formulario() -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        return w, form

    def _combo(self, ayuda: str = "", datos: dict | None = None) -> QComboBox:
        c = QComboBox()
        c.setToolTip(ayuda)
        for k, v in (datos or {}).items():
            c.addItem(v, k)
        c.currentIndexChanged.connect(self._cambio)
        return c

    def _casilla(self, texto: str, marcada: bool = False, ayuda: str = "") -> QCheckBox:
        c = QCheckBox(texto)
        c.setChecked(marcada)
        c.setToolTip(ayuda)
        c.toggled.connect(self._cambio)
        return c

    def _construir_xy(self) -> None:
        self.x = self._combo("Columna del eje x, común a todas las series")
        self.dx = self._combo("Incertidumbre de x (barras horizontales)")
        self.barras = self._casilla("Barras de error", True, "Enseña u oculta las incertidumbres de todas las series")
        self.disposicion = self._combo(
            "Con series en el eje derecho: un eje y a cada lado o dos paneles con la misma x.\n"
            "Las dos escalas son independientes: en un mismo panel, dónde se cruzan las curvas depende\n"
            "de las escalas elegidas. Para comparar formas, los paneles apilados son más claros.",
            {False: "Eje y a cada lado", True: "Paneles apilados"})
        self.log_y2 = QCheckBox("log y dcho.")
        self.log_y2.setToolTip("Escala logarítmica en el eje derecho (o en el panel inferior)")
        self.log_y2.toggled.connect(self._al_log_y2)
        self.texto_cortes = QLabel("ninguno")
        self.texto_cortes.setWordWrap(True)
        self.b_cortes = QToolButton()
        self.b_cortes.setIcon(icono("cortar"))
        self.b_cortes.setText("Cortes")
        self.b_cortes.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_cortes.setPopupMode(QToolButton.InstantPopup)
        self.b_cortes.setToolTip("Quitar tramos del eje x (eje partido «//»): la gráfica se acorta")
        self.menu_cortes = QMenu(self)
        self.menu_cortes.aboutToShow.connect(self._rellenar_menu_cortes)
        self.b_cortes.setMenu(self.menu_cortes)

        w, form = self._formulario()
        form.addRow("Eje x:", self.x)
        form.addRow("Incertidumbre x:", self.dx)
        form.addRow("Con eje derecho:", self.disposicion)
        opciones = QHBoxLayout()
        opciones.addWidget(self.barras)
        opciones.addWidget(self.log_y2)
        opciones.addStretch(1)
        form.addRow(opciones)
        fila = QHBoxLayout()
        fila.addWidget(self.texto_cortes, 1)
        fila.addWidget(self.b_cortes)
        form.addRow("Cortes en x:", fila)
        self.series_xy = TablaSeries(self, excluir=lambda: {self.x.currentText()},
                                     automatico=lambda: self.configurar(automatico=True))
        self.series_xy.cambiado.connect(self._cambio)
        self._pagina("xy", w, self.series_xy)

    def _construir_histograma(self) -> None:
        self.h_regla = self._combo("Cómo se eligen los intervalos", {
            **{k: v for k, v in REGLAS.items()}, "numero": "Número fijo", "ancho": "Anchura fija"})
        self.h_regla.setItemData(0, "Freedman–Diaconis: robusta frente a colas y valores atípicos (recomendada)",
                                 Qt.ToolTipRole)
        self.h_numero = QSpinBox()
        self.h_numero.setRange(1, 500)
        self.h_numero.setValue(20)
        self.h_numero.valueChanged.connect(self._cambio)
        self.h_ancho = QLineEdit()
        self.h_ancho.setPlaceholderText("anchura")
        self.h_ancho.editingFinished.connect(self._cambio)
        self.h_norm = self._combo("Altura de las barras", NORMALIZACIONES)
        self.h_errores = self._casilla("Errores √N", True, "Barras de error de Poisson: √N en cada intervalo")
        self.h_ajuste = self._combo("Distribución que se ajusta (máxima verosimilitud) con su test χ²",
                                    {"": "Ninguno", **DISTRIBUCIONES})
        w, form = self._formulario()
        form.addRow("Intervalos:", self.h_regla)
        fila = QHBoxLayout()
        fila.addWidget(self.h_numero)
        fila.addWidget(self.h_ancho)
        form.addRow("", fila)
        form.addRow("Altura:", self.h_norm)
        form.addRow("Ajustar:", self.h_ajuste)
        form.addRow(self.h_errores)
        self.h_series = TablaSeries(self, ("ver", "y", "color"), automatico=lambda: self._auto_pagina("histograma"))
        self.h_series.cambiado.connect(self._cambio)
        self.h_resultados = QPlainTextEdit()
        self.h_resultados.setReadOnly(True)
        self.h_resultados.setPlaceholderText("Estadística de cada columna y resultado del ajuste")
        derecha = QWidget()
        capa = QHBoxLayout(derecha)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.h_series, 1)
        capa.addWidget(self.h_resultados, 1)
        self._pagina("histograma", w, derecha)

    def _construir_barras(self) -> None:
        self.b_categorias = self._combo("Nombres de las barras: una columna de texto, de números o el número de fila")
        self.b_orden = self._combo("Orden de las barras (según la primera serie)",
                                   {"tabla": "Como en la tabla", "desc": "De mayor a menor", "asc": "De menor a mayor"})
        self.b_horizontal = self._casilla("Horizontales", False, "Barras horizontales: mejor con nombres largos")
        self.b_valores = self._casilla("Valores", False, "Escribe el valor encima de cada barra")
        self.b_errores = self._casilla("Barras de error", True)
        w, form = self._formulario()
        form.addRow("Categorías:", self.b_categorias)
        form.addRow("Orden:", self.b_orden)
        fila = QHBoxLayout()
        for c in (self.b_horizontal, self.b_valores, self.b_errores):
            fila.addWidget(c)
        fila.addStretch(1)
        form.addRow(fila)
        self.b_series = TablaSeries(self, ("ver", "y", "dy", "color"), cabecera_y="Valores",
                                    automatico=lambda: self._auto_pagina("barras"))
        self.b_series.cambiado.connect(self._cambio)
        self._pagina("barras", w, self.b_series)

    def _construir_circular(self) -> None:
        self.c_etiquetas = self._combo("Nombre de cada sector")
        self.c_valores = self._combo("Tamaño de cada sector (valores ≥ 0)")
        self.c_anillo = self._casilla("Anillo", True, "Anillo (con el total en el centro) o tarta")
        self.c_porcentajes = self._casilla("Porcentajes", True)
        self.c_ordenar = self._casilla("De mayor a menor", True)
        self.c_otros = QDoubleSpinBox()
        self.c_otros.setRange(0, 20)
        self.c_otros.setSingleStep(0.5)
        self.c_otros.setValue(3)
        self.c_otros.setSuffix(" %")
        self.c_otros.setToolTip("Los sectores menores que esto se juntan en «Otros» (como mucho hay 8 sectores)")
        self.c_otros.valueChanged.connect(self._cambio)
        w, form = self._formulario()
        form.addRow("Etiquetas:", self.c_etiquetas)
        form.addRow("Valores:", self.c_valores)
        form.addRow("Agrupar menores de:", self.c_otros)
        fila = QHBoxLayout()
        for c in (self.c_anillo, self.c_porcentajes, self.c_ordenar):
            fila.addWidget(c)
        fila.addStretch(1)
        form.addRow(fila)
        derecha = QWidget()
        capa = QVBoxLayout(derecha)
        capa.setContentsMargins(0, 0, 0, 0)
        texto = QLabel("Los ángulos y las áreas se comparan peor que las longitudes: con sectores parecidos o "
                       "muchos sectores, unas barras ordenadas se leen mejor. Los sectores van de mayor a menor "
                       "desde las 12, en sentido horario.")
        texto.setWordWrap(True)
        texto.setObjectName("secundario")
        b_barras = QPushButton("Ver como barras ordenadas")
        b_barras.clicked.connect(self.circular_a_barras)
        capa.addWidget(texto)
        capa.addWidget(b_barras, 0, Qt.AlignLeft)
        capa.addStretch(1)
        self._pagina("circular", w, derecha)

    def _construir_cajas(self) -> None:
        self.k_modo = self._combo("Cajas (mediana, cuartiles y bigotes de 1.5·IQR), violín (forma de la "
                                  "distribución) o las dos", {"cajas": "Cajas", "violin": "Violín",
                                                             "ambos": "Cajas y violín"})
        self.k_puntos = self._casilla("Puntos", True, "Todos los datos, con un poco de dispersión horizontal")
        self.k_media = self._casilla("Media (◆)", True)
        w, form = self._formulario()
        form.addRow("Forma:", self.k_modo)
        fila = QHBoxLayout()
        fila.addWidget(self.k_puntos)
        fila.addWidget(self.k_media)
        fila.addStretch(1)
        form.addRow(fila)
        self.k_series = TablaSeries(self, ("ver", "y", "color"), automatico=lambda: self._auto_pagina("cajas"))
        self.k_series.cambiado.connect(self._cambio)
        self._pagina("cajas", w, self.k_series)

    def _construir_polar(self) -> None:
        self.p_theta = self._combo("Columna del ángulo")
        self.p_unidades = self._combo("Unidades del ángulo en la tabla", {"grados": "Grados", "rad": "Radianes"})
        self.p_orientacion = self._combo("Dónde está el 0 y hacia dónde crece el ángulo", {
            "matematico": "0 a la derecha, antihorario", "brujula": "0 arriba, horario"})
        self.p_errores = self._casilla("Barras de error", True)
        w, form = self._formulario()
        form.addRow("Ángulo θ:", self.p_theta)
        form.addRow("Unidades:", self.p_unidades)
        form.addRow("Orientación:", self.p_orientacion)
        form.addRow(self.p_errores)
        self.p_series = TablaSeries(self, ("ver", "y", "dy", "estilo", "color"), cabecera_y="Radio r",
                                    excluir=lambda: {self.p_theta.currentText()},
                                    automatico=lambda: self._auto_pagina("polar"))
        self.p_series.cambiado.connect(self._cambio)
        self._pagina("polar", w, self.p_series)

    # -- compatibilidad (pruebas y sesiones de la versión anterior) ---------------------
    @property
    def tabla(self) -> QTableWidget:
        return self.series_xy.tabla

    def anadir_serie(self, cfg: dict | None = None) -> None:
        self.series_xy.anadir(cfg)

    def quitar_serie(self) -> None:
        self.series_xy.quitar()

    def _series_config(self) -> list[dict]:
        return self.series_xy.config()

    def _elegir_color(self, boton) -> None:
        self.series_xy.elegir_color(boton)

    def _pintar_colores(self) -> None:
        for t in self._tablas():
            t.pintar_colores()

    def _tablas(self) -> list[TablaSeries]:
        return [self.series_xy, self.h_series, self.b_series, self.k_series, self.p_series]

    # -- columnas -------------------------------------------------------------
    def _modelo(self):
        return self.ventana.panel_datos.modelo

    def _numericas(self) -> list[str]:
        return self._modelo().columnas_numericas()

    def _sincronizar_columnas(self) -> None:
        """Si han cambiado las columnas de la tabla, se rehacen las listas. Si es
        otra tabla, o las series apuntan a columnas que ya no existen, se vuelve
        a proponer la configuración automática."""
        modelo = self._modelo()
        clave = [*modelo.nombres, "|", *modelo.columnas_numericas()]
        if clave == self._columnas:
            return
        antes = self._columnas
        self._columnas = clave
        if not modelo.nombres:
            return
        numericas = self._numericas()
        series = self._series_config()
        validas = (bool(series) and all(s["y"] in numericas for s in series)
                   and self.x.currentText() in numericas)
        e = self.estado()
        if not antes or not validas:
            self.configurar(automatico=True, conservar_otras=bool(antes))
        else:
            self.configurar(e)

    def _rellenar(self, combo: QComboBox, opciones: list[str], actual: str | None) -> None:
        TablaSeries._rellenar(combo, opciones, actual)

    # -- configuración completa ---------------------------------------------
    def _propuestas(self) -> dict:
        """Configuración automática de todas las páginas a partir de las columnas."""
        modelo = self._modelo()
        numericas = self._numericas()
        texto = modelo.columnas_texto()
        pares = _emparejar_errores(numericas)
        inverso = {v: e for e, v in pares.items()}
        valores = [c for c in numericas if c not in pares]
        y_datos = self.ventana.panel_datos.combos["y"].currentText()
        principal = y_datos if y_datos in valores else (valores[1] if len(valores) > 1 else
                                                        (valores[0] if valores else ""))

        def serie(c, k, **extra):
            return {"ver": True, "y": c, "dy": inverso.get(c, NINGUNA), "eje": "izq", "estilo": "puntos",
                    "color": None, "indice": k, **extra}

        etiquetas = texto[0] if texto else FILA
        theta = valores[0] if valores else ""
        return {
            "histograma": {"series": [serie(principal, 0)] if principal else []},
            "barras": {"categorias": etiquetas, "series": [serie(principal if texto else
                                                                 (valores[0] if valores else ""), 0)]
                       if valores else []},
            "circular": {"etiquetas": etiquetas, "valores": principal if texto else (valores[0] if valores else "")},
            "cajas": {"series": [serie(c, k) for k, c in enumerate(valores[:MAX_SERIES])]},
            "polar": {"theta": theta, "series": [serie(c, k, estilo="puntos_linea")
                                                 for k, c in enumerate([v for v in valores if v != theta][:2])]},
        }

    def configurar(self, cfg: dict | None = None, automatico: bool = False, conservar_otras: bool = False) -> None:
        modelo = self._modelo()
        if automatico or cfg is None:
            x_datos = self.ventana.panel_datos.combos["x"].currentText()
            numericas = self._numericas()
            df = modelo.a_dataframe()
            otras = self.estado() if conservar_otras else {}
            cfg = {**configuracion_automatica(numericas, df[numericas] if numericas else None, x_datos),
                   "barras": self.barras.isChecked(), "apilados": self.disposicion.currentData(),
                   "tipo": self.tipo.currentData(), "cortes": [],
                   **({k: v for k, v in otras.items() if k in ("histograma", "barras_cfg", "circular", "cajas",
                                                                "polar")} if conservar_otras else {})}
            for k, v in self._propuestas().items():
                clave = "barras_cfg" if k == "barras" else k
                if clave not in cfg or not self._pagina_valida(k, cfg[clave]):
                    cfg[clave] = {**cfg.get(clave, {}), **v}
        numericas = self._numericas()
        todas = list(modelo.nombres)
        self._columnas = [*modelo.nombres, "|", *numericas]
        self._actualizando = True
        for t in self._tablas():
            t.fijar_columnas(numericas)
        # Puntos x-y
        self._rellenar(self.x, numericas, cfg.get("x"))
        self._rellenar(self.dx, [NINGUNA, *numericas], cfg.get("dx", NINGUNA))
        self._fijar(self.barras, bool(cfg.get("barras", True)))
        self._fijar_dato(self.disposicion, bool(cfg.get("apilados")))
        self.cortes = fusionar_cortes([tuple(c) for c in cfg.get("cortes", [])])
        self._actualizar_texto_cortes()
        # Histograma
        h = cfg.get("histograma", {})
        self._fijar_dato(self.h_regla, h.get("regla", "fd"))
        self.h_numero.blockSignals(True)
        self.h_numero.setValue(int(h.get("intervalos", 20)))
        self.h_numero.blockSignals(False)
        self.h_ancho.setText(str(h.get("ancho", "")))
        self._fijar_dato(self.h_norm, h.get("normalizacion", "cuentas"))
        self._fijar(self.h_errores, bool(h.get("errores", True)))
        self._fijar_dato(self.h_ajuste, h.get("ajuste", ""))
        # Barras
        b = cfg.get("barras_cfg", {})
        self._rellenar(self.b_categorias, [FILA, *todas], b.get("categorias", FILA))
        self._fijar_dato(self.b_orden, b.get("orden", "tabla"))
        self._fijar(self.b_horizontal, bool(b.get("horizontal", False)))
        self._fijar(self.b_valores, bool(b.get("valores", False)))
        self._fijar(self.b_errores, bool(b.get("errores", True)))
        # Sectores
        c = cfg.get("circular", {})
        self._rellenar(self.c_etiquetas, [FILA, *todas], c.get("etiquetas", FILA))
        self._rellenar(self.c_valores, numericas, c.get("valores"))
        self._fijar(self.c_anillo, bool(c.get("anillo", True)))
        self._fijar(self.c_porcentajes, bool(c.get("porcentajes", True)))
        self._fijar(self.c_ordenar, bool(c.get("ordenar", True)))
        self.c_otros.blockSignals(True)
        self.c_otros.setValue(float(c.get("otros", 3.0)))
        self.c_otros.blockSignals(False)
        # Cajas
        k = cfg.get("cajas", {})
        self._fijar_dato(self.k_modo, k.get("modo", "cajas"))
        self._fijar(self.k_puntos, bool(k.get("puntos", True)))
        self._fijar(self.k_media, bool(k.get("media", True)))
        # Polar
        p = cfg.get("polar", {})
        self._rellenar(self.p_theta, numericas, p.get("theta"))
        self._fijar_dato(self.p_unidades, p.get("unidades", "grados"))
        self._fijar_dato(self.p_orientacion, p.get("orientacion", "matematico"))
        self._fijar(self.p_errores, bool(p.get("errores", True)))
        if cfg.get("tipo") in TIPOS:
            self.tipo.blockSignals(True)
            self.tipo.setCurrentIndex(self.tipo.findData(cfg["tipo"]))
            self.tipo.blockSignals(False)
            self._mostrar_pagina()
        self._actualizando = False
        self.series_xy.configurar(cfg.get("series", []))
        self.h_series.configurar(h.get("series", []))
        self.b_series.configurar(b.get("series", []))
        self.k_series.configurar(k.get("series", []))
        self.p_series.configurar(p.get("series", []))
        self._cambio()

    def _pagina_valida(self, tipo: str, cfg: dict) -> bool:
        numericas = set(self._numericas())
        series = cfg.get("series")
        if series is not None and (not series or any(s.get("y") not in numericas for s in series)):
            return False
        if tipo == "circular":
            return cfg.get("valores") in numericas
        if tipo == "polar":
            return cfg.get("theta") in numericas
        return True

    def _auto_pagina(self, tipo: str) -> None:
        e = self.estado()
        clave = "barras_cfg" if tipo == "barras" else tipo
        e[clave] = {**e.get(clave, {}), **self._propuestas()[tipo]}
        self.configurar(e)

    @staticmethod
    def _fijar(casilla: QCheckBox, valor: bool) -> None:
        casilla.blockSignals(True)
        casilla.setChecked(valor)
        casilla.blockSignals(False)

    @staticmethod
    def _fijar_dato(combo: QComboBox, dato) -> None:
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, combo.findData(dato)))
        combo.blockSignals(False)

    # -- tipo de gráfica -----------------------------------------------------------
    def _mostrar_pagina(self) -> None:
        tipo = self.tipo.currentData()
        i = self._paginas.get(tipo, 0)
        self.izquierda.setCurrentIndex(i)
        self.derecha.setCurrentIndex(i)
        regla = self.h_regla.currentData()
        self.h_numero.setVisible(regla == "numero")
        self.h_ancho.setVisible(regla == "ancho")
        self.nota.setText({
            "xy": "Sin ajuste: solo los datos. Clic en un punto para excluir su fila. "
                  "«Cortar» en la gráfica quita un tramo de x.",
            "histograma": "Las filas excluidas no cuentan. Ajuste por máxima verosimilitud con los datos sin "
                          "agrupar; test χ² con ≥ 5 entradas esperadas por intervalo.",
            "barras": "Las filas excluidas y las vacías no se dibujan.",
            "circular": "Las filas excluidas, vacías o con valor 0 no se dibujan.",
            "cajas": "Las filas excluidas no cuentan. Pasa el ratón por una caja para ver sus estadísticos.",
            "polar": "Las filas excluidas se ven huecas.",
        }.get(tipo, ""))

    def _al_cambiar_tipo(self, *_):
        self._mostrar_pagina()
        self._cambio()

    def _cambio(self, *_):
        if self._actualizando:
            return
        if self.sender() is self.h_regla:
            self._mostrar_pagina()
        pestanas = getattr(self.ventana, "pestanas", None)
        if pestanas is not None and pestanas.currentWidget() is self:
            self.ventana.actualizar_grafica()

    def _al_log_y2(self, activo: bool) -> None:
        self.ventana.grafica.opciones.log_y2 = activo
        self._cambio()

    # -- cortes del eje x -------------------------------------------------------
    def _actualizar_texto_cortes(self) -> None:
        self.texto_cortes.setText(", ".join(f"{a:.4g} – {b:.4g}" for a, b in self.cortes) or "ninguno")

    def anadir_corte(self, a: float, b: float) -> None:
        self.cortes = fusionar_cortes([*self.cortes, (a, b)])
        self._actualizar_texto_cortes()
        self._cambio()

    def quitar_cortes(self, indice: int | None = None) -> None:
        if indice is None:
            self.cortes = []
        elif 0 <= indice < len(self.cortes):
            self.cortes.pop(indice)
        self._actualizar_texto_cortes()
        self._cambio()

    def cortar_huecos(self) -> int:
        """Corta los huecos grandes del eje x (datos quitados de en medio). Devuelve cuántos."""
        df = self._modelo().a_dataframe()
        cx = self.x.currentText()
        if cx not in df:
            return 0
        x = df[cx].to_numpy(float)
        visibles = [s["y"] for s in self._series_config() if s["ver"] and s["y"] in df]
        if visibles:
            x = x[np.any(np.isfinite(df[visibles].to_numpy(float)), axis=1)]
        huecos = detectar_huecos(x)
        if huecos:
            self.cortes = fusionar_cortes([*self.cortes, *huecos])
            self._actualizar_texto_cortes()
            self._cambio()
        else:
            self.ventana.notificar("No hay huecos grandes en x: elige el tramo con «Cortar» en la gráfica.", "aviso")
        return len(huecos)

    def _pedir_corte(self) -> None:
        texto, ok = QInputDialog.getText(self, "Añadir corte", "Tramo de x que se quita (desde; hasta):")
        if not ok:
            return
        trozos = [t for t in texto.replace(";", " ").split() if t]
        valores = [_numero(t) for t in trozos]
        if len(valores) != 2 or None in valores or valores[0] == valores[1]:
            self.ventana.notificar("Escribe dos números distintos, por ejemplo «12; 45».", "aviso")
            return
        self.anadir_corte(*valores)

    def _rellenar_menu_cortes(self) -> None:
        m = self.menu_cortes
        m.clear()
        m.addAction("Cortar los huecos grandes", self.cortar_huecos)
        m.addAction("Elegir el tramo en la gráfica",
                    lambda: self.ventana.grafica.b_cortar.setChecked(True))
        m.addAction("Escribir el tramo…", self._pedir_corte)
        if self.cortes:
            m.addSeparator()
            for i, (a, b) in enumerate(self.cortes):
                m.addAction(icono("quitar"), f"Quitar {a:.4g} – {b:.4g}", lambda i=i: self.quitar_cortes(i))
            m.addAction("Quitar todos", lambda: self.quitar_cortes())

    # -- escena -----------------------------------------------------------------
    def _incluidas(self, n: int) -> np.ndarray:
        m = np.ones(n, bool)
        ex = [f for f in self._modelo().excluidas if f < n]
        m[ex] = False
        return m

    def _columna(self, df, cfg: dict, incluidas: np.ndarray, con_errores: bool = True) -> Columna | None:
        if cfg["y"] not in df:
            return None
        v = df[cfg["y"]].to_numpy(float)
        m = np.isfinite(v) & incluidas
        if not m.any():
            return None
        e = np.abs(df[cfg["dy"]].to_numpy(float))[m] if (con_errores and cfg.get("dy") in df) else None
        return Columna(cfg["y"], v[m], e, cfg["indice"], cfg["color"], np.flatnonzero(m))

    def escena_tabla(self) -> Escena:
        """La escena se construye directamente de la tabla (no hace falta que las
        columnas x/y del panel Datos sean válidas para un ajuste)."""
        self._sincronizar_columnas()
        tipo = self.tipo.currentData()
        df = self._modelo().a_dataframe()
        if df.empty:
            return Escena()
        try:
            if tipo == "xy":
                return self._escena_xy(df)
            especial = getattr(self, f"_grafica_{tipo}")(df)
        except ErrorGrafica as exc:
            especial = Aviso(str(exc))
            if tipo == "histograma":
                self.h_resultados.setPlainText(str(exc))
        if tipo != "histograma":
            self._resumen_histograma = ""
        return Escena(especial=especial)

    def _escena_xy(self, df) -> Escena:
        cx = self.x.currentText()
        if cx not in df:
            return Escena()
        self.log_y2.blockSignals(True)
        self.log_y2.setChecked(self.ventana.grafica.opciones.log_y2)
        self.log_y2.blockSignals(False)
        x = df[cx].to_numpy(float)
        cdx = self.dx.currentText()
        dx = np.abs(df[cdx].to_numpy(float)) if cdx in df else None
        excluidas = list(self._modelo().excluidas)
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
                      barras_error=self.barras.isChecked(), cortes=list(self.cortes))

    def _grafica_histograma(self, df):
        incl = self._incluidas(len(df))
        columnas = [c for s in self.h_series.config() if s["ver"]
                    for c in [self._columna(df, s, incl, False)] if c is not None]
        regla = self.h_regla.currentData()
        ancho = _numero(self.h_ancho.text()) if regla == "ancho" else None
        if regla == "ancho" and not (ancho and ancho > 0):
            raise ErrorGrafica("Escribe la anchura de los intervalos (un número positivo).")
        g = construir_histograma(columnas, regla if regla in REGLAS else "fd",
                                 intervalos=self.h_numero.value() if regla == "numero" else None, ancho=ancho,
                                 normalizacion=self.h_norm.currentData(), errores=self.h_errores.isChecked(),
                                 distribucion=self.h_ajuste.currentData() or None)
        self._resumen_histograma = self._texto_histograma(g)
        self.h_resultados.setPlainText(self._resumen_histograma)
        return g

    @staticmethod
    def _texto_histograma(g) -> str:
        bloques = []
        h0 = g.histogramas[0]
        bloques.append(f"{h0.cuentas.size} intervalos de anchura {h0.anchos[0]:.4g} ({h0.regla})")
        for col, aj in zip(g.columnas, g.ajustes):
            r = resumen(col.valores)
            lineas = [f"— {col.nombre} —"] + [f"  {a}: {b}" for a, b in r.filas()]
            if aj is not None:
                lineas.append(aj.texto())
            bloques.append("\n".join(lineas))
        bloques += [f"⚠ {a}" for a in g.avisos]
        return "\n\n".join(bloques)

    def _categorias(self, df, columna: str) -> list[str]:
        if columna == FILA or columna not in df:
            return [str(i + 1) for i in range(len(df))]
        return self._modelo().etiquetas(columna)

    def _grafica_barras(self, df):
        incl = self._incluidas(len(df))
        cfgs = [s for s in self.b_series.config() if s["ver"] and s["y"] in df]
        if not cfgs:
            raise ErrorGrafica("Elige al menos una columna de valores para las barras.")
        valores = np.column_stack([df[s["y"]].to_numpy(float) for s in cfgs])
        filas = np.flatnonzero(incl & np.any(np.isfinite(valores), axis=1))
        if not filas.size:
            raise ErrorGrafica("No hay valores para las barras.")
        etiquetas = self._categorias(df, self.b_categorias.currentText())
        series = []
        for s in cfgs:
            e = (np.abs(df[s["dy"]].to_numpy(float))[filas]
                 if (self.b_errores.isChecked() and s["dy"] in df) else None)
            series.append(Columna(s["y"], df[s["y"]].to_numpy(float)[filas], e, s["indice"], s["color"], filas))
        cats, series = ordenar_categorias([etiquetas[i] for i in filas], series, self.b_orden.currentData())
        nombre = "" if self.b_categorias.currentText() == FILA else self.b_categorias.currentText()
        return BarrasGrafica(cats, series, self.b_horizontal.isChecked(), self.b_valores.isChecked(), nombre)

    def _grafica_circular(self, df):
        cv = self.c_valores.currentText()
        if cv not in df:
            raise ErrorGrafica("Elige la columna de valores de los sectores.")
        incl = self._incluidas(len(df))
        etiquetas = self._categorias(df, self.c_etiquetas.currentText())
        v = df[cv].to_numpy(float)
        filas = np.flatnonzero(incl)
        etq, vals, otros = preparar_sectores([etiquetas[i] for i in filas], v[filas], self.c_otros.value(),
                                             self.c_ordenar.isChecked())
        return CircularGrafica(etq, vals, otros, self.c_anillo.isChecked(), self.c_porcentajes.isChecked(), cv)

    def _grafica_cajas(self, df):
        incl = self._incluidas(len(df))
        grupos = [c for s in self.k_series.config() if s["ver"]
                  for c in [self._columna(df, s, incl, False)] if c is not None]
        if not grupos:
            raise ErrorGrafica("Elige al menos una columna con números para las cajas.")
        return CajasGrafica(grupos, self.k_modo.currentData(), self.k_puntos.isChecked(), self.k_media.isChecked())

    def _grafica_polar(self, df):
        ct = self.p_theta.currentText()
        if ct not in df:
            raise ErrorGrafica("Elige la columna del ángulo.")
        grados = self.p_unidades.currentData() == "grados"
        theta = df[ct].to_numpy(float)
        theta = np.radians(theta) if grados else theta
        excluidas = list(self._modelo().excluidas)
        series = []
        for s in self.p_series.config():
            if not s["ver"] or s["y"] not in df:
                continue
            r = df[s["y"]].to_numpy(float)
            validas = np.isfinite(theta) & np.isfinite(r)
            if not validas.any():
                continue
            filas = np.flatnonzero(validas)
            dr = np.abs(df[s["dy"]].to_numpy(float))[validas] if s["dy"] in df else None
            series.append(SerieDibujo(s["y"], theta[validas], r[validas], dy=dr, incluidos=~np.isin(filas, excluidas),
                                      filas=filas, estilo=s["estilo"] or "puntos", color=s["color"],
                                      indice=s["indice"]))
        if not series:
            raise ErrorGrafica("Elige al menos una columna para el radio r.")
        return PolarGrafica(series, ct, grados, self.p_orientacion.currentData() == "brujula",
                            self.p_errores.isChecked())

    def circular_a_barras(self) -> None:
        """Los mismos datos de los sectores, como barras horizontales de mayor a menor."""
        e = self.estado()
        c = e["circular"]
        e["barras_cfg"] = {**e["barras_cfg"], "categorias": c["etiquetas"], "orden": "desc", "horizontal": True,
                           "series": [{"ver": True, "y": c["valores"], "dy": NINGUNA, "eje": "izq",
                                       "estilo": "puntos", "color": None, "indice": 0}]}
        e["tipo"] = "barras"
        self.configurar(e)

    def escena(self, datos, filas) -> Escena:
        return self.escena_tabla()

    def ejecutar(self) -> None:
        self.ventana.actualizar_grafica()

    def recalcular(self) -> None:
        self.ventana.actualizar_grafica()

    def reiniciar(self) -> None:
        self._columnas = []
        self.cortes = []
        self._actualizar_texto_cortes()
        for t in self._tablas():
            t.tabla.setRowCount(0)

    def texto_informe(self) -> str:
        tipo = self.tipo.currentData()
        if tipo == "histograma" and self._resumen_histograma:
            return "Histograma\n" + self._resumen_histograma
        if tipo != "xy":
            return f"Gráfica: {TIPOS[tipo]}"
        lineas = [f"Representación de {len(self._series_config())} series frente a {self.x.currentText()}"]
        for s in self._series_config():
            lineas.append(f"  {'✓' if s['ver'] else '·'} {s['y']}"
                          + (f" ± {s['dy']}" if s["dy"] != NINGUNA else "") + f"  (eje {EJES.get(s['eje'], '?')})")
        if self.cortes:
            lineas.append("  Eje x partido; tramos quitados: "
                          + ", ".join(f"{a:.4g} – {b:.4g}" for a, b in self.cortes))
        return "\n".join(lineas)

    # -- sesiones ---------------------------------------------------------------
    def estado(self) -> dict:
        return {
            "tipo": self.tipo.currentData(),
            "x": self.x.currentText(), "dx": self.dx.currentText(), "barras": self.barras.isChecked(),
            "apilados": bool(self.disposicion.currentData()), "series": self._series_config(),
            "cortes": [list(c) for c in self.cortes],
            "histograma": {"regla": self.h_regla.currentData(), "intervalos": self.h_numero.value(),
                           "ancho": self.h_ancho.text(), "normalizacion": self.h_norm.currentData(),
                           "errores": self.h_errores.isChecked(), "ajuste": self.h_ajuste.currentData(),
                           "series": self.h_series.config()},
            "barras_cfg": {"categorias": self.b_categorias.currentText(), "orden": self.b_orden.currentData(),
                           "horizontal": self.b_horizontal.isChecked(), "valores": self.b_valores.isChecked(),
                           "errores": self.b_errores.isChecked(), "series": self.b_series.config()},
            "circular": {"etiquetas": self.c_etiquetas.currentText(), "valores": self.c_valores.currentText(),
                         "anillo": self.c_anillo.isChecked(), "porcentajes": self.c_porcentajes.isChecked(),
                         "ordenar": self.c_ordenar.isChecked(), "otros": self.c_otros.value()},
            "cajas": {"modo": self.k_modo.currentData(), "puntos": self.k_puntos.isChecked(),
                      "media": self.k_media.isChecked(), "series": self.k_series.config()},
            "polar": {"theta": self.p_theta.currentText(), "unidades": self.p_unidades.currentData(),
                      "orientacion": self.p_orientacion.currentData(), "errores": self.p_errores.isChecked(),
                      "series": self.p_series.config()},
        }

    def restaurar(self, e: dict) -> None:
        if e:
            self.configurar(e)
