"""Pestañas de trabajo: Ajuste, Selección, Interpolación e Intersección.

Cada panel lanza sus cálculos en segundo plano (``ventana.lanzar``) y sabe
construir la :class:`~ajustelab.gui.grafica.Escena` de su último resultado,
que la ventana dibuja cuando la pestaña está activa.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..ajuste import ResultadoAjuste, ajustar
from ..estadistica import formatear
from ..interpolacion import METODOS, ErrorInterpolacion, Interpolacion, interpolar
from ..interseccion import Interseccion, dividir, intersecar_datos
from ..modelos import CATALOGO, ErrorModelo, Modelo, clave_de, desde_expresion
from ..seleccion import Seleccion, seleccionar
from .grafica import Escena
from .trabajos import Trabajo

PERSONALIZADO = "__personalizado__"
NIVELES = {"Sin banda": None, "Banda 68 %": 0.6827, "Banda 95 %": 0.95}


def _monoespaciado(widget):
    widget.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
    return widget


def _numero(texto: str) -> float | None:
    t = texto.strip().replace(",", ".")
    return float(t) if t else None


def _celda(texto, alinear_derecha=False) -> QTableWidgetItem:
    item = QTableWidgetItem(texto)
    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    if alinear_derecha:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


def _g(v: float, cifras: int = 3) -> str:
    return "—" if v is None or not np.isfinite(v) else f"{v:.{cifras}g}"


# ---------------------------------------------------------------------------
class SelectorModelo(QWidget):
    """Desplegable con el catálogo + campo con la expresión. Si se edita la
    expresión, el modelo pasa a ser «Personalizado»."""

    def __init__(self, clave_inicial: str = "lineal", parent=None):
        super().__init__(parent)
        self.combo = QComboBox()
        for clave, m in CATALOGO.items():
            self.combo.addItem(m.nombre, clave)
        self.combo.insertSeparator(self.combo.count())
        self.combo.addItem("Personalizado…", PERSONALIZADO)
        self.expresion = QLineEdit()
        self.expresion.setPlaceholderText("p. ej. A*exp(-x/tau) + C")
        self.expresion.setToolTip("Expresión en x. Funciones: exp log ln log10 sqrt sin cos tan asin acos atan "
                                  "sinh cosh tanh abs erf; constantes pi y e; potencias con ** o ^. "
                                  "Cualquier otro nombre es un parámetro.")
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.combo)
        capa.addWidget(self.expresion, 1)
        self.combo.currentIndexChanged.connect(self._al_elegir)
        self.expresion.textEdited.connect(self._al_editar)
        self.seleccionar_clave(clave_inicial)

    def _al_elegir(self):
        clave = self.combo.currentData()
        if clave in CATALOGO:
            self.expresion.setText(CATALOGO[clave].expresion)
            self.expresion.setToolTip(CATALOGO[clave].descripcion or self.expresion.toolTip())

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
        clave = clave_de(modelo)
        if clave:
            self.seleccionar_clave(clave)
        else:
            self.combo.setCurrentIndex(self.combo.findData(PERSONALIZADO))
            self.expresion.setText(modelo.expresion)

    def modelo(self) -> Modelo:
        clave = self.combo.currentData()
        if clave in CATALOGO:
            return CATALOGO[clave]
        return desde_expresion(self.expresion.text())


# ---------------------------------------------------------------------------
class Panel(QWidget):
    titulo = ""

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

    def texto_informe(self) -> str:
        return ""


# ---------------------------------------------------------------------------
class PanelAjuste(Panel):
    titulo = "Ajuste"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.resultado: ResultadoAjuste | None = None
        self.selector = SelectorModelo("lineal")
        self.p0 = QLineEdit()
        self.p0.setPlaceholderText("opcional, p. ej. 1; 0.5; 2")
        self.usar_dx = QCheckBox("Usar σx (varianza efectiva)")
        self.usar_dx.setChecked(True)
        self.banda = QComboBox()
        self.banda.addItems(list(NIVELES))
        self.banda.setCurrentIndex(1)
        self.banda.currentIndexChanged.connect(lambda _: self.ventana.actualizar_grafica())
        boton = QPushButton("Ajustar")
        boton.setDefault(True)
        boton.clicked.connect(self.ajustar)

        form = QFormLayout()
        form.addRow("Modelo:", self.selector)
        fila = QHBoxLayout()
        fila.addWidget(self.p0, 1)
        fila.addWidget(self.usar_dx)
        fila.addWidget(self.banda)
        fila.addWidget(boton)
        form.addRow("Valores iniciales:", fila)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Parámetro", "Resultado", "Valor", "σ"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.informe = _monoespaciado(QPlainTextEdit())
        self.informe.setReadOnly(True)
        self.informe.setLineWrapMode(QPlainTextEdit.NoWrap)
        div = QSplitter(Qt.Horizontal)
        div.addWidget(self.tabla)
        div.addWidget(self.informe)
        div.setSizes([300, 500])

        b_copiar = QPushButton("Copiar informe")
        b_latex = QPushButton("Copiar parámetros (LaTeX)")
        b_copiar.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.informe.toPlainText()))
        b_latex.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.latex()))
        botones = QHBoxLayout()
        botones.addStretch(1)
        botones.addWidget(b_copiar)
        botones.addWidget(b_latex)

        capa = QVBoxLayout(self)
        capa.addLayout(form)
        capa.addWidget(div, 1)
        capa.addLayout(botones)

    def nivel(self) -> float | None:
        return NIVELES[self.banda.currentText()]

    def ajustar(self) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        try:
            modelo = self.selector.modelo()
            p0 = None
            if self.p0.text().strip():
                p0 = [float(v.replace(",", ".")) for v in self.p0.text().replace(" ", "").split(";") if v]
        except (ErrorModelo, ValueError) as e:
            self.ventana.mostrar_error(f"Modelo o valores iniciales no válidos: {e}")
            return
        trabajo = Trabajo(ajustar, datos, modelo, p0=p0, usar_dx=self.usar_dx.isChecked())
        self.ventana.lanzar(trabajo, self.mostrar_resultado, f"Ajustando «{modelo.nombre}»…")

    def mostrar_resultado(self, res: ResultadoAjuste) -> None:
        self.resultado = res
        self.obsoleto = False
        self.tabla.setRowCount(res.modelo.k)
        for i, (n, v, e) in enumerate(zip(res.nombres, res.p, res.sigma_p)):
            self.tabla.setItem(i, 0, _celda(n))
            self.tabla.setItem(i, 1, _celda(formatear(v, e)))
            self.tabla.setItem(i, 2, _celda(f"{v:.10g}", True))
            self.tabla.setItem(i, 3, _celda(f"{e:.4g}", True))
        self.informe.setPlainText(res.resumen())
        self.ventana.actualizar_grafica()

    def usar(self, res: ResultadoAjuste) -> None:
        """Muestra un resultado obtenido en otra pestaña (selección)."""
        self.selector.seleccionar_modelo(res.modelo)
        self.mostrar_resultado(res)

    def latex(self) -> str:
        if self.resultado is None:
            return ""
        filas = [rf"${n}$ & ${formatear(v, e, latex=True)}$ \\" for n, v, e in
                 zip(self.resultado.nombres, self.resultado.p, self.resultado.sigma_p)]
        return "\n".join([r"\begin{tabular}{lc}", r"Parámetro & Valor \\ \hline", *filas, r"\end{tabular}"])

    def tiene_resultado(self) -> bool:
        return self.resultado is not None

    def escena(self, datos, filas) -> Escena:
        return Escena(datos=datos, filas=filas, ajuste=self.resultado, nivel_banda=self.nivel())

    def recalcular(self) -> None:
        if self.resultado is not None:
            self.ajustar()

    def reiniciar(self) -> None:
        self.resultado = None
        self.tabla.setRowCount(0)
        self.informe.clear()

    def texto_informe(self) -> str:
        return self.informe.toPlainText()


# ---------------------------------------------------------------------------
class PanelSeleccion(Panel):
    titulo = "Selección de modelo"
    _COLUMNAS = ["", "Modelo", "k", "χ²_ν", "p", "Rachas p", "Δ", "Peso", "Estado / advertencias"]

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.seleccion: Seleccion | None = None
        self.elegido = None
        self.criterio = QComboBox()
        self.criterio.addItem("AICc", "aicc")
        self.criterio.addItem("BIC", "bic")
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("modelos propios separados por «;» o claves (p. ej. malus_grados)")
        self.usar_dx = QCheckBox("Usar σx")
        self.usar_dx.setChecked(True)
        boton = QPushButton("Probar todos los modelos")
        boton.clicked.connect(self.ejecutar)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Criterio:"))
        fila.addWidget(self.criterio)
        fila.addWidget(self.extra, 1)
        fila.addWidget(self.usar_dx)
        fila.addWidget(boton)

        self.tabla = QTableWidget(0, len(self._COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self._COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        cab = self.tabla.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(len(self._COLUMNAS) - 1, QHeaderView.Stretch)
        self.tabla.itemSelectionChanged.connect(self._al_seleccionar)
        self.tabla.itemDoubleClicked.connect(lambda _: self.usar_en_ajuste())

        self.avisos = QLabel()
        self.avisos.setWordWrap(True)
        self.avisos.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_usar = QPushButton("Usar el seleccionado en «Ajuste»")
        b_usar.clicked.connect(self.usar_en_ajuste)
        abajo = QHBoxLayout()
        abajo.addWidget(self.avisos, 1)
        abajo.addWidget(b_usar, 0, Qt.AlignTop)

        capa = QVBoxLayout(self)
        capa.addLayout(fila)
        capa.addWidget(self.tabla, 1)
        capa.addLayout(abajo)

    def ejecutar(self) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        extra = [t.strip() for t in self.extra.text().split(";") if t.strip()]
        trabajo = Trabajo(seleccionar, datos, extra=extra, criterio=self.criterio.currentData(),
                          usar_dx=self.usar_dx.isChecked(), con_progreso=True)
        self.ventana.lanzar(trabajo, self.mostrar, "Probando modelos…", cancelable=True)

    def mostrar(self, sel: Seleccion) -> None:
        self.seleccion = sel
        self.obsoleto = False
        nombre_crit = "ΔAICc" if sel.criterio == "aicc" else "ΔBIC"
        self.tabla.setHorizontalHeaderItem(6, QTableWidgetItem(nombre_crit))
        self.tabla.setRowCount(len(sel.candidatos))
        fila_rec = 0
        for i, c in enumerate(sel.candidatos):
            b = c.bondad
            marca = "★" if c is sel.recomendado else ("✓" if c.compatible else ("✗" if c.valido else ""))
            estado = "; ".join(c.advertencias) if c.valido else f"excluido: {c.motivo}"
            valores = [marca, c.modelo.nombre, str(c.modelo.k), _g(b.chi2_red if b else None),
                       _g(b.p_valor if b else None, 2), _g(b.rachas.p if b else None, 2),
                       _g(c.delta if c.valido else None, 3), _g(c.peso if c.valido else None, 2), estado]
            for j, v in enumerate(valores):
                item = _celda(v, alinear_derecha=2 <= j <= 7)
                if not c.valido:
                    item.setForeground(self.palette().placeholderText())
                item.setData(Qt.UserRole, i)
                self.tabla.setItem(i, j, item)
            if c is sel.recomendado:
                fila_rec = i
        self.avisos.setText("\n".join(f"• {a}" for a in sel.avisos))
        self.tabla.selectRow(fila_rec)
        self._al_seleccionar()

    def _al_seleccionar(self) -> None:
        if self.seleccion is None:
            return
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return
        c = self.seleccion.candidatos[filas[0].row()]
        self.elegido = c if c.resultado is not None and c.valido else None
        self.ventana.actualizar_grafica()

    def usar_en_ajuste(self) -> None:
        if self.elegido is not None:
            self.ventana.usar_en_ajuste(self.elegido.resultado)

    def tiene_resultado(self) -> bool:
        return self.seleccion is not None

    def escena(self, datos, filas) -> Escena:
        r = self.elegido.resultado if self.elegido is not None and not self.obsoleto else None
        return Escena(datos=datos, filas=filas, ajuste=r, nivel_banda=0.6827)

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
        return self.seleccion.resumen() if self.seleccion is not None else ""


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
        boton = QPushButton("Interpolar")
        boton.clicked.connect(self.interpolar)
        self.metodo.currentIndexChanged.connect(self._habilitar)
        fila = QHBoxLayout()
        for w in (QLabel("Método:"), self.metodo, self.d0, self.d1, self.lam, self.extrapolar, boton):
            fila.addWidget(w)
        fila.addStretch(1)

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
        b_exportar = QPushButton("Exportar tramos…")
        b_latex = QPushButton("Copiar tramos (LaTeX)")
        b_exportar.clicked.connect(self.exportar)
        b_latex.clicked.connect(lambda: self.resultado and QGuiApplication.clipboard().setText(
            self.resultado.exportar_tramos("latex")))
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

    def interpolar(self, _=None, silencioso: bool = False) -> None:
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
        self.salida.setPlainText(self.resultado.resumen())
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
        self.ventana.lanzar(trabajo, lambda texto: self.salida.setPlainText(base + "\n\n" + texto),
                            "Calculando (Monte Carlo)…")

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
        self.ventana.estado(f"Tramos guardados en {ruta}")

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


# ---------------------------------------------------------------------------
class PanelInterseccion(Panel):
    titulo = "Intersección"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.resultado: Interseccion | None = None
        self.n = QSpinBox()
        self.n.setRange(2, 2)
        self.n.setToolTip("Los n primeros puntos válidos de la tabla forman el conjunto 1; el resto, el conjunto 2.")
        self.sel1 = SelectorModelo("lineal")
        self.sel2 = SelectorModelo("lineal")
        boton = QPushButton("Calcular intersección")
        boton.clicked.connect(self.calcular)
        form = QFormLayout()
        form.addRow("Conjunto 1 = primeros n puntos, n =", self.n)
        form.addRow("Modelo del conjunto 1:", self.sel1)
        form.addRow("Modelo del conjunto 2:", self.sel2)
        form.addRow("", boton)
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
        self.ventana.lanzar(Trabajo(intersecar_datos, d1, d2, m1, m2), self.mostrar, "Calculando intersección…")

    def mostrar(self, I: Interseccion) -> None:
        self.resultado = I
        self.obsoleto = False
        ancho, alto, ang = I.elipse(0.6827)
        texto = [I.resumen(), "", f"Región de confianza 68 % (Δχ² = 2.30): ejes {ancho:.4g} × {alto:.4g}, "
                 f"girada {ang:.1f}°", "", "── Ajuste 1 ──", I.ajuste1.resumen(), "", "── Ajuste 2 ──",
                 I.ajuste2.resumen()]
        self.salida.setPlainText("\n".join(texto))
        self.ventana.actualizar_grafica()

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
