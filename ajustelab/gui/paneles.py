"""Pestañas de trabajo: Ajuste, Selección, Interpolación e Intersección.

Cada panel lanza sus cálculos en segundo plano (``ventana.lanzar``), sabe
construir la :class:`~ajustelab.gui.grafica.Escena` de su último resultado y
guarda/restaura su configuración para las sesiones (``estado``/``restaurar``).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..ajuste import ResultadoAjuste, ajustar
from ..estadistica import formatear
from ..interpolacion import METODOS, ErrorInterpolacion, Interpolacion, interpolar
from ..interseccion import Interseccion, dividir, intersecar_datos
from ..modelos import CATALOGO, ErrorModelo, Modelo, clave_de, desde_expresion
from ..seleccion import Seleccion, seleccionar
from .grafica import COLORES_COMPARAR, Escena
from .iconos import icono
from .trabajos import Trabajo
from .widgets import Chip, Ecuacion, Tile

PERSONALIZADO = "__personalizado__"
BANDAS = {"Sin banda": (None, False), "Confianza 68 %": (0.6827, False), "Confianza 95 %": (0.95, False),
          "Predicción 95 %": (0.95, True)}


def _monoespaciado(widget):
    widget.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    return widget


def _numero(texto: str) -> float | None:
    t = texto.strip().replace(",", ".")
    return float(t) if t else None


def _celda(texto, alinear_derecha=False, editable=False) -> QTableWidgetItem:
    item = QTableWidgetItem(texto)
    banderas = Qt.ItemIsSelectable | Qt.ItemIsEnabled
    if editable:
        banderas |= Qt.ItemIsEditable
    item.setFlags(banderas)
    if alinear_derecha:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


def _g(v: float, cifras: int = 3) -> str:
    return "—" if v is None or not np.isfinite(v) else f"{v:.{cifras}g}"


def _boton_principal(texto: str, nombre_icono: str | None = None) -> QPushButton:
    b = QPushButton(icono(nombre_icono), texto) if nombre_icono else QPushButton(texto)
    b.setProperty("primario", True)
    b.setIconSize(QSize(18, 18))
    return b


def estado_resultado(res: ResultadoAjuste) -> tuple[str, str]:
    """(texto, estado) para el chip de compatibilidad de un ajuste."""
    if not res.convergido:
        return "El ajuste no ha convergido", "malo"
    b = res.bondad()
    if not res.errores_absolutos:
        return "Sin incertidumbres: no hay test χ²", "neutro"
    if not np.isfinite(b.p_valor):
        return "ν = 0: no se puede evaluar la bondad", "neutro"
    if b.p_valor < 0.01:
        return f"Incompatible con los datos (p = {b.p_valor:.2g})", "malo"
    if np.isfinite(b.rachas.p) and b.rachas.p < 0.05:
        return f"Residuos con estructura (rachas p = {b.rachas.p:.2g})", "aviso"
    if b.p_valor < 0.05:
        return f"Ajuste dudoso (p = {b.p_valor:.2g})", "aviso"
    if b.p_valor > 0.99:
        return f"σ probablemente sobreestimadas (p = {b.p_valor:.3g})", "aviso"
    return f"Compatible con los datos (p = {b.p_valor:.2g})", "bueno"


# ---------------------------------------------------------------------------
class SelectorModelo(QWidget):
    """Desplegable con el catálogo + campo con la expresión. Si se edita la
    expresión, el modelo pasa a ser «Personalizado»."""

    cambiado = Signal()

    def __init__(self, clave_inicial: str = "lineal", parent=None):
        super().__init__(parent)
        self.combo = QComboBox()
        for clave, m in CATALOGO.items():
            self.combo.addItem(m.nombre, clave)
        self.combo.insertSeparator(self.combo.count())
        self.combo.addItem("Personalizado…", PERSONALIZADO)
        self.combo.setMaxVisibleItems(30)
        self.expresion = QLineEdit()
        self.expresion.setPlaceholderText("p. ej. A*exp(-x/tau) + C")
        self._ayuda = ("Expresión en x. Funciones: exp log ln log10 sqrt sin cos tan asin acos atan sinh cosh "
                       "tanh abs erf; constantes pi y e; potencias con ** o ^. Cualquier otro nombre es un parámetro.")
        self.expresion.setToolTip(self._ayuda)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.combo)
        capa.addWidget(self.expresion, 1)
        self.combo.currentIndexChanged.connect(self._al_elegir)
        self.expresion.textEdited.connect(self._al_editar)
        self.expresion.editingFinished.connect(self.cambiado)
        self.seleccionar_clave(clave_inicial)

    def _al_elegir(self):
        clave = self.combo.currentData()
        if clave in CATALOGO:
            self.expresion.setText(CATALOGO[clave].expresion)
            self.expresion.setToolTip(CATALOGO[clave].descripcion or self._ayuda)
        self.cambiado.emit()

    def _al_editar(self, _):
        i = self.combo.findData(PERSONALIZADO)
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(i)
        self.combo.blockSignals(False)

    def seleccionar_clave(self, clave: str):
        i = self.combo.findData(clave)
        if i >= 0:
            self.combo.setCurrentIndex(i)
            self._al_elegir()

    def seleccionar_modelo(self, modelo: Modelo):
        modelo = modelo.original
        clave = clave_de(modelo)
        if clave:
            self.seleccionar_clave(clave)
        else:
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(self.combo.findData(PERSONALIZADO))
            self.combo.blockSignals(False)
            self.expresion.setText(modelo.expresion)
            self.cambiado.emit()

    def modelo(self) -> Modelo:
        clave = self.combo.currentData()
        if clave in CATALOGO:
            return CATALOGO[clave]
        return desde_expresion(self.expresion.text())

    def estado(self) -> dict:
        clave = self.combo.currentData()
        return {"clave": clave} if clave in CATALOGO else {"expresion": self.expresion.text()}

    def restaurar(self, e: dict) -> None:
        if "clave" in e:
            self.seleccionar_clave(e["clave"])
        elif "expresion" in e:
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(self.combo.findData(PERSONALIZADO))
            self.combo.blockSignals(False)
            self.expresion.setText(e["expresion"])
            self.cambiado.emit()


# ---------------------------------------------------------------------------
class TablaParametros(QTableWidget):
    """Parámetro | Inicial | Fijo | Mín | Máx | Resultado. Comprueba la coherencia
    (mín < máx, inicial dentro de los límites, fijo con valor) y la señala en rojo."""

    COLS = ["Parámetro", "Inicial", "Fijo", "Mín", "Máx", "Resultado"]
    cambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(0, len(self.COLS), parent)
        self.setHorizontalHeaderLabels(self.COLS)
        self.verticalHeader().setVisible(False)
        cab = self.horizontalHeader()
        for i in range(len(self.COLS)):
            cab.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(1, QHeaderView.Stretch)
        cab.setSectionResizeMode(5, QHeaderView.Stretch)
        for i, ayuda in enumerate(["", "Valor de partida del ajuste (o valor si está fijo)",
                                   "No se ajusta: se mantiene en el valor inicial", "Límite inferior (vacío = sin límite)",
                                   "Límite superior (vacío = sin límite)", "Resultado ± 1σ"]):
            if ayuda:
                self.horizontalHeaderItem(i).setToolTip(ayuda)
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self._nombres: tuple[str, ...] = ()
        self._bloqueo = False
        self.itemChanged.connect(self._al_cambiar)

    @property
    def nombres(self) -> tuple[str, ...]:
        return self._nombres

    def fijar_modelo(self, modelo: Modelo) -> None:
        """Filas para los parámetros del modelo, conservando lo que el usuario ya
        hubiera escrito para parámetros con el mismo nombre."""
        previo = self.valores()
        self._bloqueo = True
        self._nombres = modelo.parametros
        self.setRowCount(len(self._nombres))
        for i, n in enumerate(self._nombres):
            v = previo.get(n, {})
            self.setItem(i, 0, _celda(n))
            self.setItem(i, 1, _celda("" if v.get("inicial") is None else f"{v['inicial']:.8g}", True, True))
            fijo = QTableWidgetItem()
            fijo.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            fijo.setCheckState(Qt.Checked if v.get("fijo") else Qt.Unchecked)
            self.setItem(i, 2, fijo)
            for col, clave in ((3, "min"), (4, "max")):
                self.setItem(i, col, _celda("" if v.get(clave) is None else f"{v[clave]:.8g}", True, True))
            self.setItem(i, 5, _celda("", True))
        self._bloqueo = False
        self.validar()

    def valores(self) -> dict[str, dict]:
        salida = {}
        for i, n in enumerate(self._nombres):
            def num(col):
                it = self.item(i, col)
                try:
                    return _numero(it.text()) if it is not None else None
                except ValueError:
                    return None
            fijo = self.item(i, 2)
            salida[n] = {"inicial": num(1), "fijo": fijo is not None and fijo.checkState() == Qt.Checked,
                         "min": num(3), "max": num(4)}
        return salida

    def poner_iniciales(self, valores: dict[str, float], solo_vacios: bool = False) -> None:
        self._bloqueo = True
        for i, n in enumerate(self._nombres):
            it = self.item(i, 1)
            if n in valores and np.isfinite(valores[n]) and not (solo_vacios and it.text().strip()):
                it.setText(f"{valores[n]:.8g}")
        self._bloqueo = False
        self.validar()
        self.cambiado.emit()

    def poner_resultado(self, res: ResultadoAjuste | None, fmt=lambda s: s) -> None:
        self._bloqueo = True
        valores = {} if res is None else res.parametros
        for i, n in enumerate(self._nombres):
            if res is not None and n in res.fijos:
                texto = f"{res.fijos[n]:g} (fijo)"
            elif n in valores:
                texto = formatear(*valores[n])
            else:
                texto = ""
            self.item(i, 5).setText(fmt(texto))
        self._bloqueo = False

    def errores(self) -> list[str]:
        """Comprueba la coherencia y marca en rojo las celdas con problemas."""
        previo, self._bloqueo = self._bloqueo, True  # pintar celdas no es «editar»
        try:
            return self._errores()
        finally:
            self._bloqueo = previo

    def _errores(self) -> list[str]:
        problemas = []
        rojo = QBrush(QColor(208, 59, 59, 70))
        for i, n in enumerate(self._nombres):
            for col in (1, 3, 4):
                it = self.item(i, col)
                it.setBackground(QBrush())
                it.setToolTip("")
            v = self.valores()[n]
            for col in (1, 3, 4):
                texto = self.item(i, col).text().strip()
                if texto:
                    try:
                        _numero(texto)
                    except ValueError:
                        problemas.append(f"{n}: «{texto}» no es un número")
                        self.item(i, col).setBackground(rojo)
            if v["min"] is not None and v["max"] is not None and v["min"] >= v["max"]:
                problemas.append(f"{n}: el mínimo debe ser menor que el máximo")
                for col in (3, 4):
                    self.item(i, col).setBackground(rojo)
            if v["inicial"] is not None and ((v["min"] is not None and v["inicial"] < v["min"])
                                             or (v["max"] is not None and v["inicial"] > v["max"])):
                problemas.append(f"{n}: el valor inicial está fuera de los límites")
                self.item(i, 1).setBackground(rojo)
            if v["fijo"] and v["inicial"] is None:
                problemas.append(f"{n}: un parámetro fijo necesita un valor")
                self.item(i, 1).setBackground(rojo)
        if self._nombres and all(v["fijo"] for v in self.valores().values()):
            problemas.append("No se pueden fijar todos los parámetros")
        for p in problemas:
            nombre = p.split(":")[0]
            if nombre in self._nombres:
                fila = self._nombres.index(nombre)
                for col in (1, 3, 4):
                    if self.item(fila, col).background().color().alpha():
                        self.item(fila, col).setToolTip(p)
        return problemas

    def validar(self) -> bool:
        return not self.errores()

    def _al_cambiar(self, item):
        if self._bloqueo:
            return
        self.validar()
        self.cambiado.emit()


# ---------------------------------------------------------------------------
class Panel(QWidget):
    titulo = ""
    nombre_icono = "ajustar"

    def __init__(self, ventana, parent=None):
        super().__init__(parent)
        self.ventana = ventana
        self.obsoleto = False

    def tiene_resultado(self) -> bool:
        return False

    def escena(self, datos, filas) -> Escena:
        return Escena(datos=datos, filas=filas)

    def recalcular(self) -> None:
        """Rehace el último cálculo con los datos actuales (tras excluir puntos...)."""

    def marcar_obsoleto(self) -> None:
        self.obsoleto = self.tiene_resultado()

    def reiniciar(self) -> None:
        """Olvida el resultado (al abrir otro fichero)."""

    def al_cambiar_datos(self) -> None:
        """Los datos han cambiado (otra columna, otro fichero...)."""

    def texto_informe(self) -> str:
        return ""

    def estado(self) -> dict:
        return {}

    def restaurar(self, e: dict) -> None:
        pass


# ---------------------------------------------------------------------------
class PanelAjuste(Panel):
    titulo = "Ajuste"
    nombre_icono = "ajustar"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.resultado: ResultadoAjuste | None = None
        self._modelo: Modelo | None = None
        self._previa_activa = True

        # --- modelo y ecuación
        self.selector = SelectorModelo("lineal")
        self.ecuacion = Ecuacion()
        self.selector.cambiado.connect(self._al_cambiar_modelo)

        # --- parámetros
        self.tabla = TablaParametros()
        self.tabla.cambiado.connect(self._al_editar_parametros)
        b_estimar = QPushButton(icono("estimar"), "Estimar iniciales")
        b_estimar.setToolTip("Calcula valores iniciales automáticamente a partir de los datos")
        b_estimar.clicked.connect(lambda: self.estimar_iniciales(forzar=True))
        self.b_usar = QPushButton(icono("usar"), "Usar resultado")
        self.b_usar.setToolTip("Copia el resultado del último ajuste como valores iniciales")
        self.b_usar.clicked.connect(self.usar_resultado_como_iniciales)
        self.b_usar.setEnabled(False)
        self.previa = QCheckBox("Vista previa")
        self.previa.setChecked(True)
        self.previa.setToolTip("Dibuja el modelo con los valores iniciales (línea discontinua)")
        self.previa.toggled.connect(lambda _: self.ventana.actualizar_grafica())
        self.usar_dx = QCheckBox("Usar σx")
        self.usar_dx.setChecked(True)
        self.usar_dx.setToolTip("Varianza efectiva: σ_eff² = σy² + (f′·σx)²")
        self.banda = QComboBox()
        self.banda.addItems(list(BANDAS))
        self.banda.setCurrentIndex(1)
        self.banda.setToolTip("Confianza: incertidumbre de la curva. Predicción: además, la dispersión de una medida nueva")
        self.banda.currentIndexChanged.connect(lambda _: self.ventana.actualizar_grafica())
        self.b_ajustar = _boton_principal("Ajustar", "ajustar")
        self.b_ajustar.setToolTip("Ajustar (Ctrl+Intro)")
        self.b_ajustar.clicked.connect(self.ajustar)

        izq = QWidget()
        capa_izq = QVBoxLayout(izq)
        capa_izq.setContentsMargins(0, 0, 0, 0)
        capa_izq.addWidget(self.tabla, 1)
        fila1 = QHBoxLayout()
        fila1.addWidget(b_estimar)
        fila1.addWidget(self.b_usar)
        fila1.addStretch(1)
        fila1.addWidget(self.previa)
        fila2 = QHBoxLayout()
        fila2.addWidget(self.usar_dx)
        fila2.addWidget(self.banda)
        fila2.addStretch(1)
        fila2.addWidget(self.b_ajustar)
        capa_izq.addLayout(fila1)
        capa_izq.addLayout(fila2)

        # --- resultados: resumen / informe / evaluar
        self.resultados = QTabWidget()
        self.resultados.setDocumentMode(True)
        self.resultados.addTab(self._crear_resumen(), "Resumen")
        self.resultados.addTab(self._crear_informe(), "Informe")
        self.resultados.addTab(self._crear_evaluar(), "Evaluar")

        div = QSplitter(Qt.Horizontal)
        div.addWidget(izq)
        div.addWidget(self.resultados)
        div.setStretchFactor(0, 5)
        div.setStretchFactor(1, 6)

        capa = QVBoxLayout(self)
        capa.addWidget(self.selector)
        capa.addWidget(self.ecuacion)
        capa.addWidget(div, 1)
        self._al_cambiar_modelo()

    # -- construcción de las subpestañas -----------------------------------
    def _crear_resumen(self) -> QWidget:
        w = QWidget()
        self.chip = Chip()
        self.tiles = {
            "chi2": Tile("χ² / ν", "≈ 1 compatible; ≫ 1 modelo incorrecto o σ subestimadas; ≪ 1 σ sobreestimadas"),
            "p": Tile("p-valor", "Probabilidad de un χ² igual o mayor si el modelo es correcto"),
            "r2": Tile("R² ponderado", "Solo informativo: no sirve para comparar modelos no lineales"),
            "n": Tile("n · ν", "Puntos usados · grados de libertad"),
        }
        fila = QHBoxLayout()
        for t in self.tiles.values():
            fila.addWidget(t)
        self.metodo = QLabel()
        self.metodo.setObjectName("secundario")
        self.avisos = QLabel()
        self.avisos.setWordWrap(True)
        self.avisos.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.avisos.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        capa = QVBoxLayout(w)
        capa.addWidget(self.chip)
        capa.addLayout(fila)
        capa.addWidget(self.metodo)
        capa.addWidget(self.avisos, 1)
        self._limpiar_resumen()
        return w

    def _crear_informe(self) -> QWidget:
        w = QWidget()
        self.informe = _monoespaciado(QPlainTextEdit())
        self.informe.setReadOnly(True)
        self.informe.setLineWrapMode(QPlainTextEdit.NoWrap)
        b_copiar = QPushButton(icono("copiar"), "Copiar informe")
        b_latex = QPushButton(icono("copiar"), "Copiar parámetros (LaTeX)")
        b_copiar.clicked.connect(lambda: self._copiar(self.informe.toPlainText(), "Informe copiado."))
        b_latex.clicked.connect(lambda: self._copiar(self.latex(), "Tabla LaTeX copiada."))
        botones = QHBoxLayout()
        botones.addStretch(1)
        botones.addWidget(b_copiar)
        botones.addWidget(b_latex)
        capa = QVBoxLayout(w)
        capa.addWidget(self.informe, 1)
        capa.addLayout(botones)
        return w

    def _crear_evaluar(self) -> QWidget:
        w = QWidget()
        self.ev_x = QLineEdit()
        self.ev_x.setPlaceholderText("x")
        self.ev_y = QLineEdit()
        self.ev_y.setPlaceholderText("y₀")
        self.ev_sy = QLineEdit()
        self.ev_sy.setPlaceholderText("σ(y₀), opcional")
        b = QPushButton("Calcular")
        b.clicked.connect(self.evaluar)
        for le in (self.ev_x, self.ev_y, self.ev_sy):
            le.returnPressed.connect(self.evaluar)
        self.ev_salida = QLabel()
        self.ev_salida.setWordWrap(True)
        self.ev_salida.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ev_salida.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        form = QFormLayout()
        form.addRow("f(x) en x =", self.ev_x)
        fila = QHBoxLayout()
        fila.addWidget(self.ev_y)
        fila.addWidget(self.ev_sy)
        form.addRow("x tal que f(x) =", fila)
        nota = QLabel("Curvas de calibración: σ(x) = √(σ_f² + σ(y₀)²) / |f′(x)|, con σ_f la incertidumbre "
                      "de la curva ajustada.")
        nota.setObjectName("secundario")
        nota.setWordWrap(True)
        capa = QVBoxLayout(w)
        capa.addLayout(form)
        capa.addWidget(b, 0, Qt.AlignRight)
        capa.addWidget(self.ev_salida, 1)
        capa.addWidget(nota)
        return w

    # -- modelo y parámetros -----------------------------------------------
    def _al_cambiar_modelo(self) -> None:
        try:
            modelo = self.selector.modelo()
        except ErrorModelo as e:
            self.ecuacion.fijar("", f"⚠ {e}")
            self._modelo = None
            self.tabla.setRowCount(0)
            self.tabla._nombres = ()
            return
        self._modelo = modelo
        self.ecuacion.fijar(f"y = {modelo.latex}", f"y = {modelo.expresion}")
        self.tabla.fijar_modelo(modelo)
        self.estimar_iniciales(forzar=False)
        self._previa_activa = True
        self.ventana.actualizar_grafica()

    def estimar_iniciales(self, forzar: bool = True) -> None:
        if self._modelo is None:
            return
        obtenidos = self.ventana.obtener_datos(silencioso=True)
        if obtenidos is None:
            return
        d = obtenidos[0].activos()
        p0 = self._modelo.p0(d.x, d.y)
        self.tabla.poner_iniciales(dict(zip(self._modelo.parametros, p0)), solo_vacios=not forzar)
        self._previa_activa = True

    def usar_resultado_como_iniciales(self) -> None:
        if self.resultado is not None:
            valores = {n: v for n, (v, _) in self.resultado.parametros.items()}
            self.tabla.poner_iniciales(valores)

    def _al_editar_parametros(self) -> None:
        self._previa_activa = True
        if self.previa.isChecked():
            self.ventana.actualizar_grafica()

    def al_cambiar_datos(self) -> None:
        # con datos nuevos, rellena los iniciales que estén vacíos
        self.estimar_iniciales(forzar=False)

    def _configuracion(self, datos):
        """(modelo con fijos, p0 de los libres, límites o None, fijos) desde la tabla."""
        if self._modelo is None:
            raise ErrorModelo("La expresión del modelo no es válida.")
        problemas = self.tabla.errores()
        if problemas:
            raise ValueError("; ".join(problemas))
        v = self.tabla.valores()
        fijos = {n: c["inicial"] for n, c in v.items() if c["fijo"]}
        modelo = self._modelo.fijar(fijos)
        d = datos.activos()
        p0 = modelo.p0(d.x, d.y)
        for i, n in enumerate(modelo.parametros):
            if v[n]["inicial"] is not None:
                p0[i] = v[n]["inicial"]
        lo = [v[n]["min"] if v[n]["min"] is not None else -np.inf for n in modelo.parametros]
        hi = [v[n]["max"] if v[n]["max"] is not None else np.inf for n in modelo.parametros]
        limites = None if all(np.isinf(lo)) and all(np.isinf(hi)) else (lo, hi)
        return modelo, p0, limites, fijos

    # -- ajuste -------------------------------------------------------------
    def ajustar(self) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        try:
            modelo, p0, limites, _ = self._configuracion(datos)
        except (ErrorModelo, ValueError) as e:
            self.ventana.mostrar_error(f"Revisa el modelo o los parámetros: {e}")
            return
        trabajo = Trabajo(ajustar, datos, modelo, p0=p0, limites=limites, usar_dx=self.usar_dx.isChecked())
        self.ventana.lanzar(trabajo, self.mostrar_resultado, f"Ajustando «{modelo.nombre}»…", canal=self.titulo)

    def mostrar_resultado(self, res: ResultadoAjuste, silencioso: bool = False) -> None:
        self.resultado = res
        self.obsoleto = False
        self._previa_activa = False
        self.b_usar.setEnabled(True)
        fmt = self.ventana.fmt
        self.tabla.poner_resultado(res, fmt)
        self.informe.setPlainText(fmt(res.resumen()))
        texto, estado = estado_resultado(res)
        self.chip.fijar(fmt(texto), estado)
        b = res.bondad()
        self.tiles["chi2"].fijar(fmt(_g(b.chi2_red)) if res.errores_absolutos else "—")
        self.tiles["p"].fijar(fmt(_g(b.p_valor, 2)))
        self.tiles["r2"].fijar(fmt(f"{b.r2:.4f}") if np.isfinite(b.r2) else "—")
        self.tiles["n"].fijar(f"{b.n} · {b.nu}")
        self.metodo.setText(res.metodo + (f" · {res.iteraciones_ve} iteraciones" if res.iteraciones_ve else ""))
        avisos = [a for a in b.avisos]
        self.avisos.setText(fmt("\n".join(f"• {a}" for a in avisos)) if avisos else "Sin avisos.")
        self.ventana.actualizar_grafica()
        if not silencioso:
            self.ventana.notificar(fmt(f"{res.modelo.nombre}: {texto}"), estado)

    def _limpiar_resumen(self) -> None:
        self.chip.fijar("Todavía no hay ajuste", "neutro")
        for t in self.tiles.values():
            t.fijar("—")
        self.metodo.setText("")
        self.avisos.setText("Elige un modelo, revisa los valores iniciales (la línea discontinua de la gráfica) "
                            "y pulsa «Ajustar».")

    def usar(self, res: ResultadoAjuste) -> None:
        """Muestra un resultado obtenido en otra pestaña (selección)."""
        self.selector.blockSignals(True)
        self.selector.seleccionar_modelo(res.modelo)
        self.selector.blockSignals(False)
        self._modelo = res.modelo.original
        self.ecuacion.fijar(f"y = {self._modelo.latex}", f"y = {self._modelo.expresion}")
        self.tabla.fijar_modelo(self._modelo)
        self.tabla.poner_iniciales({n: v for n, (v, _) in res.parametros.items()})
        self.mostrar_resultado(res, silencioso=True)

    def evaluar(self) -> None:
        r = self.resultado
        if r is None:
            self.ev_salida.setText("Primero haz un ajuste.")
            return
        fmt = self.ventana.fmt
        lineas = []
        try:
            x, y0, sy = (_numero(w.text()) for w in (self.ev_x, self.ev_y, self.ev_sy))
        except ValueError:
            self.ev_salida.setText("Los campos deben ser números.")
            return
        if x is not None:
            f, s = float(r.evaluar(np.array([x]))[0]), float(r.sigma_f(x)[0])
            lineas.append(f"f({x:g}) = {formatear(f, s)}    ({f:.10g} ± {s:.3g})")
        if y0 is not None:
            soluciones = r.inversa(y0, sy or 0.0)
            extrapolado = False
            if not soluciones:  # se busca fuera del rango ajustado, avisando
                lo, hi = float(np.min(r.datos.x)), float(np.max(r.datos.x))
                ancho = hi - lo or 1.0
                soluciones = r.inversa(y0, sy or 0.0, intervalo=(lo - ancho, hi + ancho))
                extrapolado = bool(soluciones)
            if not soluciones:
                lineas.append(f"Ningún x cerca del rango de los datos cumple f(x) = {y0:g}.")
            for xs, sx in soluciones:
                lineas.append(f"x = {formatear(xs, sx)}    ({xs:.10g} ± {sx:.3g})")
            if extrapolado:
                lineas.append("⚠ Fuera del rango de los puntos ajustados: es una extrapolación.")
        self.ev_salida.setText(fmt("\n".join(lineas)) if lineas else "Escribe x o y₀.")

    def latex(self) -> str:
        if self.resultado is None:
            return ""
        coma = self.ventana.coma_decimal
        filas = []
        for n, v, e in zip(self.resultado.nombres, self.resultado.p, self.resultado.sigma_p):
            valor = formatear(v, e, latex=True)
            filas.append(rf"${n}$ & ${valor.replace('.', '{,}') if coma else valor}$ \\")
        for n, v in self.resultado.fijos.items():
            filas.append(rf"${n}$ & ${v:g}$ (fijo) \\")
        return "\n".join([r"\begin{tabular}{lc}", r"Parámetro & Valor \\ \hline", *filas, r"\end{tabular}"])

    def _copiar(self, texto: str, aviso: str) -> None:
        if texto:
            QGuiApplication.clipboard().setText(texto)
            self.ventana.notificar(aviso, "bueno")

    # -- panel ----------------------------------------------------------------
    def nivel(self) -> tuple[float | None, bool]:
        return BANDAS[self.banda.currentText()]

    def tiene_resultado(self) -> bool:
        return self.resultado is not None

    def escena(self, datos, filas) -> Escena:
        nivel, prediccion = self.nivel()
        previa = None
        if self.previa.isChecked() and self._previa_activa:
            try:
                modelo, p0, _, _ = self._configuracion(datos)
                previa = (modelo, p0)
            except (ErrorModelo, ValueError, KeyError, IndexError):
                previa = None
        return Escena(datos=datos, filas=filas, ajuste=self.resultado, nivel_banda=nivel, prediccion=prediccion,
                      previa=previa)

    def recalcular(self) -> None:
        if self.resultado is not None:
            self.ajustar()

    def reiniciar(self) -> None:
        self.resultado = None
        self.b_usar.setEnabled(False)
        self.tabla.poner_resultado(None)
        self.informe.clear()
        self.ev_salida.clear()
        self._limpiar_resumen()
        self._previa_activa = True
        self.estimar_iniciales(forzar=True)

    def texto_informe(self) -> str:
        return self.informe.toPlainText()

    def estado(self) -> dict:
        return {"modelo": self.selector.estado(), "parametros": self.tabla.valores(),
                "banda": self.banda.currentText(), "usar_dx": self.usar_dx.isChecked(),
                "previa": self.previa.isChecked(), "calculado": self.resultado is not None}

    def restaurar(self, e: dict) -> None:
        self.selector.restaurar(e.get("modelo", {"clave": "lineal"}))
        params = e.get("parametros", {})
        self.tabla._bloqueo = True
        for i, n in enumerate(self.tabla.nombres):
            v = params.get(n, {})
            for col, clave in ((1, "inicial"), (3, "min"), (4, "max")):
                self.tabla.item(i, col).setText("" if v.get(clave) is None else f"{v[clave]:.10g}")
            self.tabla.item(i, 2).setCheckState(Qt.Checked if v.get("fijo") else Qt.Unchecked)
        self.tabla._bloqueo = False
        self.tabla.validar()
        if e.get("banda") in BANDAS:
            self.banda.setCurrentText(e["banda"])
        self.usar_dx.setChecked(e.get("usar_dx", True))
        self.previa.setChecked(e.get("previa", True))
        if e.get("calculado"):
            self.ajustar()


# ---------------------------------------------------------------------------
class PanelSeleccion(Panel):
    titulo = "Selección de modelo"
    nombre_icono = "seleccion"
    _COLUMNAS = ["Ver", "", "Modelo", "k", "χ²/ν", "p", "Rachas p", "Δ", "Peso", "Estado / advertencias"]

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.seleccion: Seleccion | None = None
        self.elegido = None
        self.criterio = QComboBox()
        self.criterio.addItem("AICc", "aicc")
        self.criterio.addItem("BIC", "bic")
        self.criterio.setToolTip("AICc: mejor con pocos puntos. BIC: penaliza más los parámetros extra")
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("modelos propios separados por «;» o claves (p. ej. malus_grados)")
        self.usar_dx = QCheckBox("Usar σx")
        self.usar_dx.setChecked(True)
        boton = _boton_principal("Probar todos los modelos", "seleccion")
        boton.clicked.connect(self.ejecutar)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Criterio:"))
        fila.addWidget(self.criterio)
        fila.addWidget(self.extra, 1)
        fila.addWidget(self.usar_dx)
        fila.addWidget(boton)

        self.tabla = QTableWidget(0, len(self._COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self._COLUMNAS)
        self.tabla.horizontalHeaderItem(0).setToolTip("Superponer en la gráfica para comparar (máximo 3)")
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        cab = self.tabla.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(len(self._COLUMNAS) - 1, QHeaderView.Stretch)
        self.tabla.itemSelectionChanged.connect(self._al_seleccionar)
        self.tabla.itemDoubleClicked.connect(lambda _: self.usar_en_ajuste())
        self.tabla.itemChanged.connect(self._al_marcar)

        self.leyenda = QLabel("★ recomendado   ✓ compatible   ✗ incompatible   (doble clic: usar en «Ajuste»)")
        self.leyenda.setObjectName("secundario")
        self.avisos = QLabel()
        self.avisos.setWordWrap(True)
        self.avisos.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_usar = QPushButton(icono("usar"), "Usar en «Ajuste»")
        b_usar.clicked.connect(self.usar_en_ajuste)
        abajo = QHBoxLayout()
        abajo.addWidget(self.avisos, 1)
        abajo.addWidget(b_usar, 0, Qt.AlignTop)

        capa = QVBoxLayout(self)
        capa.addLayout(fila)
        capa.addWidget(self.tabla, 1)
        capa.addWidget(self.leyenda)
        capa.addLayout(abajo)

    def ejecutar(self) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        extra = [t.strip() for t in self.extra.text().split(";") if t.strip()]
        trabajo = Trabajo(seleccionar, datos, extra=extra, criterio=self.criterio.currentData(),
                          usar_dx=self.usar_dx.isChecked(), con_progreso=True)
        self.ventana.lanzar(trabajo, self.mostrar, "Probando modelos…", cancelable=True, canal=self.titulo)

    def mostrar(self, sel: Seleccion) -> None:
        self.seleccion = sel
        self.obsoleto = False
        fmt = self.ventana.fmt
        self.tabla.blockSignals(True)
        self.tabla.setHorizontalHeaderItem(7, QTableWidgetItem("ΔAICc" if sel.criterio == "aicc" else "ΔBIC"))
        self.tabla.setRowCount(len(sel.candidatos))
        fila_rec = 0
        for i, c in enumerate(sel.candidatos):
            b = c.bondad
            marca = "★" if c is sel.recomendado else ("✓" if c.compatible else ("✗" if c.valido else ""))
            estado = "; ".join(c.advertencias) if c.valido else f"excluido: {c.motivo}"
            ver = QTableWidgetItem()
            if c.valido:
                ver.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                ver.setCheckState(Qt.Unchecked)
            else:
                ver.setFlags(Qt.NoItemFlags)
            self.tabla.setItem(i, 0, ver)
            valores = [marca, c.modelo.nombre, str(c.modelo.k), _g(b.chi2_red if b else None),
                       _g(b.p_valor if b else None, 2), _g(b.rachas.p if b else None, 2),
                       _g(c.delta if c.valido else None, 3), _g(c.peso if c.valido else None, 2), estado]
            for j, v in enumerate(valores, start=1):
                item = _celda(fmt(v) if 4 <= j <= 8 else v, alinear_derecha=3 <= j <= 8)
                if not c.valido:
                    item.setForeground(self.palette().placeholderText())
                self.tabla.setItem(i, j, item)
            if c is sel.recomendado:
                fila_rec = i
        self.tabla.blockSignals(False)
        self.avisos.setText(fmt("\n".join(f"• {a}" for a in sel.avisos)))
        self.tabla.selectRow(fila_rec)
        self._al_seleccionar()
        if sel.recomendado is not None:
            self.ventana.notificar(f"Recomendado: {sel.recomendado.modelo.nombre}", "bueno")

    def comparados(self) -> list[ResultadoAjuste]:
        if self.seleccion is None or self.obsoleto:
            return []
        salida = []
        for i, c in enumerate(self.seleccion.candidatos):
            it = self.tabla.item(i, 0)
            if it is not None and it.checkState() == Qt.Checked and c.resultado is not None and c is not self.elegido:
                salida.append(c.resultado)
        return salida[:3]

    def _al_marcar(self, item) -> None:
        if item.column() != 0 or self.seleccion is None:
            return
        marcados = [i for i in range(self.tabla.rowCount())
                    if self.tabla.item(i, 0) is not None and self.tabla.item(i, 0).checkState() == Qt.Checked]
        if len(marcados) > 3 and item.checkState() == Qt.Checked:
            self.tabla.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.tabla.blockSignals(False)
            self.ventana.notificar("Se pueden comparar como máximo 3 modelos a la vez.", "aviso")
            return
        self._colorear_marcados()
        self.ventana.actualizar_grafica()

    def _colorear_marcados(self) -> None:
        colores = COLORES_COMPARAR[self.ventana.tema.oscuro]
        k = 0
        self.tabla.blockSignals(True)
        for i in range(self.tabla.rowCount()):
            it = self.tabla.item(i, 0)
            nombre = self.tabla.item(i, 2)
            if it is None or nombre is None:
                continue
            c = self.seleccion.candidatos[i] if self.seleccion else None
            if it.checkState() == Qt.Checked and c is not self.elegido and k < 3:
                it.setBackground(QBrush(QColor(colores[k])))
                k += 1
            else:
                it.setBackground(QBrush())
        self.tabla.blockSignals(False)

    def _al_seleccionar(self) -> None:
        if self.seleccion is None:
            return
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return
        c = self.seleccion.candidatos[filas[0].row()]
        self.elegido = c if c.resultado is not None and c.valido else None
        self._colorear_marcados()
        self.ventana.actualizar_grafica()

    def usar_en_ajuste(self) -> None:
        if self.elegido is not None:
            self.ventana.usar_en_ajuste(self.elegido.resultado)

    def tiene_resultado(self) -> bool:
        return self.seleccion is not None

    def escena(self, datos, filas) -> Escena:
        r = self.elegido.resultado if self.elegido is not None and not self.obsoleto else None
        return Escena(datos=datos, filas=filas, ajuste=r, nivel_banda=0.6827, comparar=self.comparados())

    def marcar_obsoleto(self) -> None:
        super().marcar_obsoleto()
        if self.obsoleto:
            self.avisos.setText("⚠ Los datos han cambiado: vuelve a pulsar «Probar todos los modelos».")

    def reiniciar(self) -> None:
        self.seleccion = None
        self.elegido = None
        self.tabla.setRowCount(0)
        self.avisos.clear()

    def texto_informe(self) -> str:
        return self.ventana.fmt(self.seleccion.resumen()) if self.seleccion is not None else ""

    def estado(self) -> dict:
        return {"criterio": self.criterio.currentData(), "extra": self.extra.text(),
                "usar_dx": self.usar_dx.isChecked(), "calculado": self.seleccion is not None}

    def restaurar(self, e: dict) -> None:
        i = self.criterio.findData(e.get("criterio", "aicc"))
        self.criterio.setCurrentIndex(max(i, 0))
        self.extra.setText(e.get("extra", ""))
        self.usar_dx.setChecked(e.get("usar_dx", True))
        if e.get("calculado"):
            self.ejecutar()


# ---------------------------------------------------------------------------
def _calcular_interpolacion(f: Interpolacion, x0, y0, a, b) -> str:
    """Evaluaciones pedidas, con incertidumbre Monte Carlo si hay σ (se ejecuta en un hilo)."""
    con_error = f.dy is not None or f.dx is not None
    lineas = []

    def con_mc(nombre, funcion):
        try:
            if con_error:
                r = f.monte_carlo(funcion, n=1000)
                lineas.append(f"{nombre} = {formatear(r.nominal, r.sigma)}    ({r.nominal:.10g} ± {r.sigma:.3g})")
            else:
                lineas.append(f"{nombre} = {float(funcion(f)):.10g}")
        except (ErrorInterpolacion, ValueError, IndexError) as e:
            lineas.append(f"{nombre}: {e}")

    if x0 is not None:
        con_mc(f"f({x0:g})", lambda g: g(x0))
        con_mc(f"f'({x0:g})", lambda g: g.derivada(x0))
    if y0 is not None:
        raices = f.inversa(y0)
        if raices.size == 0:
            lineas.append(f"No hay ningún x en el rango con f(x) = {y0:g}.")
        for r0 in raices:
            con_mc(f"x con f(x) = {y0:g} (cerca de {r0:.4g})",
                   lambda g, r0=r0: g.inversa(y0)[np.argmin(np.abs(g.inversa(y0) - r0))])
    if a is not None and b is not None:
        con_mc(f"∫ f dx de {a:g} a {b:g}", lambda g: g.integral(a, b))
    if con_error and lineas:
        lineas.append("(incertidumbres por Monte Carlo con 1000 réplicas de los datos)")
    return "\n".join(lineas)


class PanelInterpolacion(Panel):
    titulo = "Interpolación"
    nombre_icono = "ajustar"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.resultado: Interpolacion | None = None
        self.metodo = QComboBox()
        for clave, nombre in METODOS.items():
            self.metodo.addItem(nombre, clave)
        self.metodo.setCurrentIndex(self.metodo.findData("natural"))
        self.d0 = QLineEdit()
        self.d1 = QLineEdit()
        self.lam = QLineEdit()
        for w, ph in ((self.d0, "f'(x₀)"), (self.d1, "f'(xₙ)"), (self.lam, "λ (auto)")):
            w.setPlaceholderText(ph)
            w.setMaximumWidth(80)
        self.extrapolar = QCheckBox("Extrapolar")
        boton = _boton_principal("Interpolar", "ajustar")
        boton.clicked.connect(self.interpolar)
        self.metodo.currentIndexChanged.connect(self._habilitar)
        fila = QHBoxLayout()
        for w in (QLabel("Método:"), self.metodo, self.d0, self.d1, self.lam, self.extrapolar):
            fila.addWidget(w)
        fila.addStretch(1)
        fila.addWidget(boton)

        self.x0, self.y0, self.a, self.b = (QLineEdit() for _ in range(4))
        caja = QGroupBox("Calcular")
        rejilla = QGridLayout(caja)
        rejilla.addWidget(QLabel("f(x) y f'(x) en x ="), 0, 0)
        rejilla.addWidget(self.x0, 0, 1)
        rejilla.addWidget(QLabel("x tal que f(x) ="), 0, 2)
        rejilla.addWidget(self.y0, 0, 3)
        rejilla.addWidget(QLabel("∫ desde"), 1, 0)
        rejilla.addWidget(self.a, 1, 1)
        rejilla.addWidget(QLabel("hasta"), 1, 2)
        rejilla.addWidget(self.b, 1, 3)
        b_calc = QPushButton("Calcular")
        b_calc.clicked.connect(self.calcular)
        rejilla.addWidget(b_calc, 0, 4, 2, 1)

        self.salida = _monoespaciado(QPlainTextEdit())
        self.salida.setReadOnly(True)
        b_exportar = QPushButton(icono("exportar"), "Exportar tramos…")
        b_latex = QPushButton(icono("copiar"), "Copiar tramos (LaTeX)")
        b_exportar.clicked.connect(self.exportar)
        b_latex.clicked.connect(self._copiar_latex)
        botones = QHBoxLayout()
        botones.addStretch(1)
        botones.addWidget(b_exportar)
        botones.addWidget(b_latex)

        capa = QVBoxLayout(self)
        capa.addLayout(fila)
        capa.addWidget(caja)
        capa.addWidget(self.salida, 1)
        capa.addLayout(botones)
        self._habilitar()

    def _habilitar(self):
        m = self.metodo.currentData()
        self.d0.setVisible(m == "clamped")
        self.d1.setVisible(m == "clamped")
        self.lam.setVisible(m == "suavizado")
        self.metodo.setToolTip({"pchip": "Monótono: no sobreoscila", "suavizado": "No pasa por los puntos: para datos con ruido",
                                "polinomio": "Solo para pocos puntos (Runge)"}.get(m, ""))

    def interpolar(self, _=None) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        m = self.metodo.currentData()
        try:
            kw = {"extrapolar": self.extrapolar.isChecked()}
            if m == "clamped":
                kw["derivadas_extremos"] = (_numero(self.d0.text()), _numero(self.d1.text()))
                if None in kw["derivadas_extremos"]:
                    raise ValueError("indica f'(x₀) y f'(xₙ).")
            if m == "suavizado":
                kw["suavizado"] = _numero(self.lam.text())
            self.resultado = interpolar(datos, m, **kw)
        except (ErrorInterpolacion, ValueError) as e:
            self.ventana.mostrar_error(f"Interpolación: {e}")
            return
        self.obsoleto = False
        self.salida.setPlainText(self.ventana.fmt(self.resultado.resumen()))
        self.ventana.actualizar_grafica()

    def calcular(self) -> None:
        if self.resultado is None:
            self.interpolar()
            if self.resultado is None:
                return
        try:
            x0, y0, a, b = (_numero(w.text()) for w in (self.x0, self.y0, self.a, self.b))
        except ValueError:
            self.ventana.mostrar_error("Los campos de «Calcular» deben ser números.")
            return
        trabajo = Trabajo(_calcular_interpolacion, self.resultado, x0, y0, a, b)
        base = self.resultado.resumen()
        self.ventana.lanzar(trabajo, lambda texto: self.salida.setPlainText(self.ventana.fmt(base + "\n\n" + texto)),
                            "Calculando (Monte Carlo)…", canal=self.titulo)

    def _copiar_latex(self) -> None:
        if self.resultado is not None:
            QGuiApplication.clipboard().setText(self.resultado.exportar_tramos("latex"))
            self.ventana.notificar("Tramos en LaTeX copiados.", "bueno")

    def exportar(self) -> None:
        if self.resultado is None:
            return
        ruta, filtro = QFileDialog.getSaveFileName(self, "Exportar tramos", "tramos.txt",
                                                   "Texto (*.txt);;LaTeX (*.tex);;CSV (*.csv)")
        if not ruta:
            return
        formato = "latex" if ruta.lower().endswith(".tex") or "LaTeX" in filtro else (
            "csv" if ruta.lower().endswith(".csv") or "CSV" in filtro else "txt")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(self.resultado.exportar_tramos(formato))
        self.ventana.notificar(f"Tramos guardados en {ruta}", "bueno")

    def tiene_resultado(self) -> bool:
        return self.resultado is not None

    def escena(self, datos, filas) -> Escena:
        return Escena(datos=datos, filas=filas, interpolacion=self.resultado)

    def recalcular(self) -> None:
        if self.resultado is not None:
            self.interpolar()

    def reiniciar(self) -> None:
        self.resultado = None
        self.salida.clear()

    def texto_informe(self) -> str:
        return self.salida.toPlainText()

    def estado(self) -> dict:
        return {"metodo": self.metodo.currentData(), "d0": self.d0.text(), "d1": self.d1.text(),
                "lam": self.lam.text(), "extrapolar": self.extrapolar.isChecked(),
                "x0": self.x0.text(), "y0": self.y0.text(), "a": self.a.text(), "b": self.b.text(),
                "calculado": self.resultado is not None}

    def restaurar(self, e: dict) -> None:
        i = self.metodo.findData(e.get("metodo", "natural"))
        self.metodo.setCurrentIndex(max(i, 0))
        for w, k in ((self.d0, "d0"), (self.d1, "d1"), (self.lam, "lam"), (self.x0, "x0"), (self.y0, "y0"),
                     (self.a, "a"), (self.b, "b")):
            w.setText(e.get(k, ""))
        self.extrapolar.setChecked(e.get("extrapolar", False))
        if e.get("calculado"):
            self.interpolar()


# ---------------------------------------------------------------------------
class PanelInterseccion(Panel):
    titulo = "Intersección"
    nombre_icono = "rango"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.resultado: Interseccion | None = None
        self.n = QSpinBox()
        self.n.setRange(2, 2)
        self.n.setToolTip("Los n primeros puntos válidos de la tabla forman el conjunto 1; el resto, el conjunto 2.")
        self.sel1 = SelectorModelo("lineal")
        self.sel2 = SelectorModelo("lineal")
        boton = _boton_principal("Calcular intersección", "rango")
        boton.clicked.connect(self.calcular)
        form = QFormLayout()
        form.addRow("Conjunto 1 = primeros n puntos, n =", self.n)
        form.addRow("Modelo del conjunto 1:", self.sel1)
        form.addRow("Modelo del conjunto 2:", self.sel2)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(boton)
        form.addRow(fila)
        self.salida = _monoespaciado(QPlainTextEdit())
        self.salida.setReadOnly(True)
        capa = QVBoxLayout(self)
        capa.addLayout(form)
        capa.addWidget(self.salida, 1)

    def actualizar_rango(self, n_total: int) -> None:
        self.n.setRange(2, max(2, n_total - 2))

    def calcular(self) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        try:
            d1, d2 = dividir(datos, self.n.value())
            m1, m2 = self.sel1.modelo(), self.sel2.modelo()
        except (ErrorModelo, ValueError) as e:
            self.ventana.mostrar_error(str(e))
            return
        self.ventana.lanzar(Trabajo(intersecar_datos, d1, d2, m1, m2), self.mostrar, "Calculando intersección…",
                            canal=self.titulo)

    def mostrar(self, I: Interseccion) -> None:
        self.resultado = I
        self.obsoleto = False
        ancho, alto, ang = I.elipse(0.6827)
        texto = [I.resumen(), "", f"Región de confianza 68 % (Δχ² = 2.30): ejes {ancho:.4g} × {alto:.4g}, "
                 f"girada {ang:.1f}°", "", "── Ajuste 1 ──", I.ajuste1.resumen(), "", "── Ajuste 2 ──",
                 I.ajuste2.resumen()]
        self.salida.setPlainText(self.ventana.fmt("\n".join(texto)))
        self.ventana.actualizar_grafica()
        self.ventana.notificar(self.ventana.fmt(f"Corte en x* = {formatear(I.x, I.sigma_x)}"), "bueno")

    def tiene_resultado(self) -> bool:
        return self.resultado is not None

    def escena(self, datos, filas) -> Escena:
        if self.resultado is None or self.obsoleto:
            return Escena(datos=datos, filas=filas)
        return Escena(datos=datos, filas=filas, interseccion=self.resultado)

    def recalcular(self) -> None:
        if self.resultado is not None:
            self.calcular()

    def reiniciar(self) -> None:
        self.resultado = None
        self.salida.clear()

    def texto_informe(self) -> str:
        return self.salida.toPlainText()

    def estado(self) -> dict:
        return {"n": self.n.value(), "modelo1": self.sel1.estado(), "modelo2": self.sel2.estado(),
                "calculado": self.resultado is not None}

    def restaurar(self, e: dict) -> None:
        self.n.setValue(e.get("n", 2))
        self.sel1.restaurar(e.get("modelo1", {"clave": "lineal"}))
        self.sel2.restaurar(e.get("modelo2", {"clave": "lineal"}))
        if e.get("calculado"):
            self.calcular()
