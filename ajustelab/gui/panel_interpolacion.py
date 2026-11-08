"""Pestaña «Interpolación».

* **Evaluar en un punto**: escribe x y pulsa Intro: f(x) y f'(x) salen al momento y
  su incertidumbre (Monte Carlo) en cuanto se calcula.
* **Tabla de valores**: f, σ_f, f' y σ_f' en una lista de x (``1; 2; 5``) o un rango
  (``0:10:0,5``); se copia para una hoja de cálculo o en LaTeX y se exporta en CSV.
* **Resumen para el informe**: un párrafo (texto o LaTeX) con el método, los
  puntos, el rango, la incertidumbre de la curva y una tabla corta de valores, en
  lugar de los N−1 tramos del spline (que siguen pudiéndose exportar).
* «x tal que f(x) = y» e integral definida, con su incertidumbre.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget)

from ..estadistica import formatear
from ..interpolacion import METODOS, ErrorInterpolacion, Interpolacion, interpolar, valores_x
from .grafica import Escena
from .iconos import icono
from .paneles import Panel, _boton_principal, _monoespaciado, _numero
from .trabajos import Trabajo

_COLUMNAS = ("x", "f(x)", "σ f", "f'(x)", "σ f'")


def _valor(v: float, e: float) -> str:
    if not np.isfinite(v):
        return "—"
    return formatear(v, e) if np.isfinite(e) and e > 0 else f"{v:.8g}"


def _calcular_interpolacion(f: Interpolacion, x0, y0, a, b) -> str:
    """Evaluaciones pedidas, con incertidumbre Monte Carlo si hay σ (se ejecuta en un hilo)."""
    lineas = []

    def con_mc(nombre, funcion):
        try:
            if f.con_errores:
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
    if f.con_errores and lineas:
        lineas.append("(incertidumbres por Monte Carlo con 1000 réplicas de los datos)")
    return "\n".join(lineas)


def _informes(f: Interpolacion, xs) -> tuple[str, str]:
    return f.informe(xs), f.informe(xs, latex=True)


class PanelInterpolacion(Panel):
    titulo = "Interpolación"
    nombre_icono = "ajustar"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.resultado: Interpolacion | None = None
        self.tabla_valores = None  # DataFrame de la última tabla evaluada
        self.informe_texto = ""
        self.informe_latex = ""

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
        self.extrapolar.setToolTip("Permite evaluar fuera del rango de los datos (con cuidado: no hay datos allí)")
        boton = _boton_principal("Interpolar", "ajustar")
        boton.clicked.connect(self.interpolar)
        self.metodo.currentIndexChanged.connect(self._habilitar)
        fila = QHBoxLayout()
        for w in (QLabel("Método:"), self.metodo, self.d0, self.d1, self.lam, self.extrapolar):
            fila.addWidget(w)
        fila.addStretch(1)
        fila.addWidget(boton)

        # -- evaluar en un punto, inversa e integral
        self.x0, self.y0, self.a, self.b = (QLineEdit() for _ in range(4))
        self.x0.setPlaceholderText("p. ej. 17")
        self.x0.setToolTip("Intro: f(x) y f'(x) al momento; la incertidumbre llega en cuanto se calcula")
        self.x0.returnPressed.connect(self.evaluar_punto)
        self.punto = QLabel("Escribe x y pulsa Intro.")
        self.punto.setObjectName("resultado_punto")
        self.punto.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.punto.setWordWrap(True)
        letra = self.punto.font()
        letra.setPointSizeF(letra.pointSizeF() * 1.15)
        self.punto.setFont(letra)
        b_punto = QPushButton("Evaluar")
        b_punto.clicked.connect(self.evaluar_punto)
        caja = QGroupBox("Evaluar")
        rejilla = QGridLayout(caja)
        rejilla.addWidget(QLabel("x ="), 0, 0)
        rejilla.addWidget(self.x0, 0, 1)
        rejilla.addWidget(b_punto, 0, 2)
        rejilla.addWidget(self.punto, 1, 0, 1, 3)
        rejilla.addWidget(QLabel("x tal que f(x) ="), 2, 0)
        rejilla.addWidget(self.y0, 2, 1)
        rejilla.addWidget(QLabel("∫ desde"), 3, 0)
        tramo = QHBoxLayout()
        tramo.addWidget(self.a)
        tramo.addWidget(QLabel("hasta"))
        tramo.addWidget(self.b)
        rejilla.addLayout(tramo, 3, 1)
        b_calc = QPushButton("Calcular")
        b_calc.setToolTip("f(x), f'(x), x tal que f(x) = y e integral, con su incertidumbre")
        b_calc.clicked.connect(self.calcular)
        rejilla.addWidget(b_calc, 2, 2, 2, 1)

        # -- tabla de valores
        self.xs = QLineEdit()
        self.xs.setPlaceholderText("1; 2; 5   o   0:10:0,5")
        self.xs.setToolTip("Una lista de x separados por «;» o espacios, o un rango inicio:fin:paso "
                           "(inicio:fin da 11 puntos). Admite coma decimal.")
        self.xs.returnPressed.connect(self.evaluar_tabla)
        b_tabla = QPushButton("Evaluar")
        b_tabla.clicked.connect(self.evaluar_tabla)
        caja_tabla = QGroupBox("Tabla de valores")
        fila_tabla = QHBoxLayout(caja_tabla)
        fila_tabla.addWidget(QLabel("x:"))
        fila_tabla.addWidget(self.xs, 1)
        fila_tabla.addWidget(b_tabla)

        izquierda = QVBoxLayout()
        izquierda.addWidget(caja)
        izquierda.addWidget(caja_tabla)
        izquierda.addStretch(1)
        columna = QWidget()
        columna.setLayout(izquierda)
        columna.setMaximumWidth(420)

        # -- resultados: texto, tabla e informe
        self.salida = _monoespaciado(QPlainTextEdit())
        self.salida.setReadOnly(True)
        self.tabla = QTableWidget(0, len(_COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(list(_COLUMNAS))
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.informe = _monoespaciado(QPlainTextEdit())  # para que la tabla salga alineada
        self.informe.setReadOnly(True)
        self.informe.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.informe.setPlaceholderText("«Resumen para el informe» escribe aquí un párrafo listo para pegar, con la "
                                        "tabla de valores si la has evaluado.")
        self.resultados = QTabWidget()
        self.resultados.addTab(self.salida, "Resultados")
        self.resultados.addTab(self.tabla, "Tabla")
        self.resultados.addTab(self.informe, "Informe")

        centro = QHBoxLayout()
        centro.addWidget(columna)
        centro.addWidget(self.resultados, 1)

        b_informe = QPushButton(icono("copiar"), "Resumen para el informe")
        b_informe.setToolTip("Un párrafo con el método, los puntos, el rango y la incertidumbre de la curva, y la "
                             "tabla de valores evaluada. Mucho más corto que los tramos.")
        b_informe.clicked.connect(self.generar_informe)
        self.b_copiar = QToolButton()
        self.b_copiar.setText("Copiar")
        self.b_copiar.setIcon(icono("copiar"))
        self.b_copiar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_copiar.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        menu.addAction("Resumen (texto)", lambda: self._copiar(self.informe_texto, "Resumen copiado."))
        menu.addAction("Resumen (LaTeX)", lambda: self._copiar(self.informe_latex, "Resumen en LaTeX copiado."))
        menu.addSeparator()
        menu.addAction("Tabla (para hoja de cálculo)", self._copiar_tabla)
        menu.addAction("Tabla (LaTeX)", lambda: self._copiar_tabla(latex=True))
        menu.addSeparator()
        menu.addAction("Tramos (LaTeX)", self._copiar_latex)
        self.b_copiar.setMenu(menu)
        self.b_exportar = QToolButton()
        self.b_exportar.setText("Exportar")
        self.b_exportar.setIcon(icono("exportar"))
        self.b_exportar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_exportar.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        menu.addAction("Tabla de valores (CSV)…", self.exportar_tabla)
        menu.addAction("Resumen (.txt o .tex)…", self.exportar_informe)
        menu.addAction("Tramos del spline…", self.exportar)
        self.b_exportar.setMenu(menu)
        botones = QHBoxLayout()
        botones.addStretch(1)
        botones.addWidget(b_informe)
        botones.addWidget(self.b_copiar)
        botones.addWidget(self.b_exportar)

        capa = QVBoxLayout(self)
        capa.addLayout(fila)
        capa.addLayout(centro, 1)
        capa.addLayout(botones)
        self._habilitar()

    def _habilitar(self):
        m = self.metodo.currentData()
        self.d0.setVisible(m == "clamped")
        self.d1.setVisible(m == "clamped")
        self.lam.setVisible(m == "suavizado")
        self.metodo.setToolTip({"pchip": "Monótono: no sobreoscila", "suavizado": "No pasa por los puntos: para datos con ruido",
                                "polinomio": "Solo para pocos puntos (Runge)"}.get(m, ""))

    # -- interpolar --------------------------------------------------------------
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
        self.resultados.setCurrentWidget(self.salida)
        self.ventana.actualizar_grafica()

    def _asegurar(self) -> bool:
        if self.resultado is None:
            self.interpolar()
        return self.resultado is not None

    # -- evaluar ---------------------------------------------------------------------
    def evaluar_punto(self) -> None:
        """f(x) y f'(x) al momento; la incertidumbre (Monte Carlo) llega después."""
        if not self._asegurar():
            return
        try:
            x0 = _numero(self.x0.text())
        except ValueError:
            x0 = None
        if x0 is None:
            self.punto.setText("Escribe un número en x.")
            return
        f = self.resultado
        v, d = float(f(x0)), float(f.derivada(x0))
        if not np.isfinite(v):
            lo, hi = f.rango
            self.punto.setText(f"x = {x0:g} está fuera del rango de los datos [{lo:g}, {hi:g}]: "
                               "activa «Extrapolar» si lo necesitas.")
            return
        nombre = f"f({x0:g})"
        self.punto.setText(self.ventana.fmt(f"{nombre} = {v:.8g}     f'({x0:g}) = {d:.6g}"
                                            + ("     (calculando la incertidumbre…)" if f.con_errores else "")))
        if f.con_errores:
            def poner(tabla, x0=x0):
                if tabla is None or not len(tabla):
                    return
                r = tabla.iloc[0]
                self.punto.setText(self.ventana.fmt(f"f({x0:g}) = {_valor(r.f, r.sigma_f)}     "
                                                    f"f'({x0:g}) = {_valor(r.derivada, r.sigma_derivada)}"))

            self.ventana.lanzar(Trabajo(f.evaluar, [x0]), poner, "Calculando la incertidumbre…", canal="punto")

    def evaluar_tabla(self) -> None:
        if not self._asegurar():
            return
        try:
            xs = valores_x(self.xs.text())
        except ErrorInterpolacion as e:
            self.ventana.mostrar_error(str(e))
            return
        self.ventana.lanzar(Trabajo(self.resultado.evaluar, xs), self._mostrar_tabla,
                            "Evaluando (Monte Carlo)…" if self.resultado.con_errores else "Evaluando…",
                            canal=self.titulo)

    def _mostrar_tabla(self, tabla) -> None:
        self.tabla_valores = tabla
        self.tabla.setRowCount(len(tabla))
        con_errores = bool(np.isfinite(tabla["sigma_f"]).any())
        for i, r in enumerate(tabla.itertuples()):
            textos = (f"{r.x:.8g}", _valor(r.f, r.sigma_f), f"{r.sigma_f:.3g}" if np.isfinite(r.sigma_f) else "—",
                      _valor(r.derivada, r.sigma_derivada),
                      f"{r.sigma_derivada:.3g}" if np.isfinite(r.sigma_derivada) else "—")
            for j, t in enumerate(textos):
                item = QTableWidgetItem(self.ventana.fmt(t))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla.setItem(i, j, item)
        self.tabla.setColumnHidden(2, not con_errores)
        self.tabla.setColumnHidden(4, not con_errores)
        self.resultados.setCurrentWidget(self.tabla)
        fuera = int((~np.isfinite(tabla["f"])).sum())
        self.ventana.notificar(f"{len(tabla)} valores evaluados" + (f"; {fuera} fuera del rango." if fuera else "."),
                               "aviso" if fuera else "bueno")

    def calcular(self) -> None:
        if not self._asegurar():
            return
        try:
            x0, y0, a, b = (_numero(w.text()) for w in (self.x0, self.y0, self.a, self.b))
        except ValueError:
            self.ventana.mostrar_error("Los campos de «Evaluar» deben ser números.")
            return
        trabajo = Trabajo(_calcular_interpolacion, self.resultado, x0, y0, a, b)
        base = self.resultado.resumen()

        def mostrar(texto):
            self.salida.setPlainText(self.ventana.fmt(base + "\n\n" + texto))
            self.resultados.setCurrentWidget(self.salida)

        self.ventana.lanzar(trabajo, mostrar, "Calculando (Monte Carlo)…", canal=self.titulo)

    # -- informe -----------------------------------------------------------------------
    def generar_informe(self) -> None:
        if not self._asegurar():
            return
        xs = None if self.tabla_valores is None else self.tabla_valores["x"].to_numpy()
        if xs is not None and xs.size > 15:  # en un informe, una tabla corta
            xs = xs[np.unique(np.linspace(0, xs.size - 1, 15).round().astype(int))]

        def mostrar(resultado):
            self.informe_texto, self.informe_latex = resultado
            self.informe.setPlainText(self.ventana.fmt(self.informe_texto))
            self.resultados.setCurrentWidget(self.informe)
            QGuiApplication.clipboard().setText(self.informe_texto)
            self.ventana.notificar("Resumen copiado. En «Copiar» está también en LaTeX.", "bueno")

        self.ventana.lanzar(Trabajo(_informes, self.resultado, xs), mostrar, "Preparando el resumen…",
                            canal=self.titulo)

    # -- copiar y exportar ---------------------------------------------------------------
    def _copiar(self, texto: str, aviso: str) -> None:
        if not texto:
            self.ventana.notificar("Primero pulsa «Resumen para el informe».", "aviso")
            return
        QGuiApplication.clipboard().setText(texto)
        self.ventana.notificar(aviso, "bueno")

    def _texto_tabla(self, latex: bool = False) -> str:
        t = self.tabla_valores
        if t is None:
            return ""
        if latex:
            filas = [rf"  ${r.x:.6g}$ & ${formatear(r.f, r.sigma_f, latex=True) if np.isfinite(r.sigma_f) and r.sigma_f > 0 else f'{r.f:.6g}'}$ \\"
                     for r in t.itertuples() if np.isfinite(r.f)]
            f = self.resultado
            return "\n".join([r"\begin{tabular}{cc}", r"  \toprule", rf"  {f.nombre_x} & {f.nombre_y} \\",
                              r"  \midrule", *filas, r"  \bottomrule", r"\end{tabular}"]) + "\n"
        return t.to_csv(sep="\t", index=False, float_format="%.10g")

    def _copiar_tabla(self, latex: bool = False) -> None:
        texto = self._texto_tabla(latex)
        if not texto:
            self.ventana.notificar("Primero evalúa una tabla de valores.", "aviso")
            return
        QGuiApplication.clipboard().setText(texto)
        self.ventana.notificar("Tabla copiada.", "bueno")

    def _copiar_latex(self) -> None:
        if self.resultado is not None:
            QGuiApplication.clipboard().setText(self.resultado.exportar_tramos("latex"))
            self.ventana.notificar("Tramos en LaTeX copiados.", "bueno")

    def exportar_tabla(self) -> None:
        if self.tabla_valores is None:
            self.ventana.notificar("Primero evalúa una tabla de valores.", "aviso")
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar tabla de valores", "valores.csv", "CSV (*.csv)")
        if ruta:
            self.tabla_valores.to_csv(ruta, index=False, float_format="%.10g")
            self.ventana.notificar(f"Tabla guardada en {ruta}", "bueno")

    def exportar_informe(self) -> None:
        if not self.informe_texto:
            self.ventana.notificar("Primero pulsa «Resumen para el informe».", "aviso")
            return
        ruta, filtro = QFileDialog.getSaveFileName(self, "Exportar resumen", "interpolacion.tex",
                                                   "LaTeX (*.tex);;Texto (*.txt)")
        if ruta:
            latex = ruta.lower().endswith(".tex") or ("LaTeX" in filtro and not ruta.lower().endswith(".txt"))
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(self.informe_latex if latex else self.informe_texto)
            self.ventana.notificar(f"Resumen guardado en {ruta}", "bueno")

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

    # -- panel ---------------------------------------------------------------------------
    def tiene_resultado(self) -> bool:
        return self.resultado is not None

    def escena(self, datos, filas) -> Escena:
        return Escena(datos=datos, filas=filas, interpolacion=self.resultado)

    def recalcular(self) -> None:
        if self.resultado is not None:
            self.interpolar()

    def reiniciar(self) -> None:
        self.resultado = None
        self.tabla_valores = None
        self.informe_texto = self.informe_latex = ""
        self.salida.clear()
        self.informe.clear()
        self.tabla.setRowCount(0)
        self.punto.setText("Escribe x y pulsa Intro.")

    def texto_informe(self) -> str:
        return self.informe_texto or self.salida.toPlainText()

    def estado(self) -> dict:
        return {"metodo": self.metodo.currentData(), "d0": self.d0.text(), "d1": self.d1.text(),
                "lam": self.lam.text(), "extrapolar": self.extrapolar.isChecked(),
                "x0": self.x0.text(), "y0": self.y0.text(), "a": self.a.text(), "b": self.b.text(),
                "xs": self.xs.text(), "calculado": self.resultado is not None}

    def restaurar(self, e: dict) -> None:
        i = self.metodo.findData(e.get("metodo", "natural"))
        self.metodo.setCurrentIndex(max(i, 0))
        for w, k in ((self.d0, "d0"), (self.d1, "d1"), (self.lam, "lam"), (self.x0, "x0"), (self.y0, "y0"),
                     (self.a, "a"), (self.b, "b"), (self.xs, "xs")):
            w.setText(e.get(k, ""))
        self.extrapolar.setChecked(e.get("extrapolar", False))
        if e.get("calculado"):
            self.interpolar()
