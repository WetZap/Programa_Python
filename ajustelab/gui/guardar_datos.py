"""Diálogo «Guardar datos»: toda la tabla o una parte, como fichero nuevo.

Ejemplo: una medida de 0 a 2000 s de la que solo sirven los 100 primeros valores →
«x entre 0 y 100» (o «Filas de 1 a 100») → se guarda como CSV, Excel… y, si se
quiere, se abre en lugar de la tabla actual.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout, QWidget)

from ..datos import FORMATOS_GUARDAR

MODOS = {
    "todas": "Todas las filas",
    "incluidas": "Solo las incluidas (sin excluidas ni fuera del rango)",
    "rango": "Las del rango de ajuste",
    "x": "Con x entre dos valores",
    "filas": "Filas de … a …",
    "seleccion": "Las seleccionadas en la tabla",
}


def _numero(texto: str) -> float | None:
    t = texto.strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


class DialogoGuardarDatos(QDialog):
    """Elige filas, columnas y formato. ``filas()`` y ``tabla()`` dan el resultado."""

    def __init__(self, modelo, seleccionadas: list[int], columna_x: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guardar datos")
        self.modelo = modelo
        self._df = modelo.a_dataframe(con_texto=True)
        self._seleccionadas = sorted(set(seleccionadas))
        n = len(self._df)

        self.modo = QComboBox()
        for k, v in MODOS.items():
            self.modo.addItem(v, k)
        self.modo.model().item(self.modo.findData("rango")).setEnabled(modelo.rango_x is not None)
        self.modo.model().item(self.modo.findData("seleccion")).setEnabled(bool(self._seleccionadas))
        if self._seleccionadas and len(self._seleccionadas) > 1:
            self.modo.setCurrentIndex(self.modo.findData("seleccion"))

        numericas = modelo.columnas_numericas()
        self.columna_x = QComboBox()
        self.columna_x.addItems(numericas)
        if columna_x in numericas:
            self.columna_x.setCurrentText(columna_x)
        self.x_desde = QLineEdit()
        self.x_hasta = QLineEdit()
        self.x_desde.setPlaceholderText("desde (vacío: sin límite)")
        self.x_hasta.setPlaceholderText("hasta (vacío: sin límite)")
        if modelo.rango_x is not None:
            self.x_desde.setText(f"{modelo.rango_x[0]:.10g}")
            self.x_hasta.setText(f"{modelo.rango_x[1]:.10g}")
        self.fila_desde = QSpinBox()
        self.fila_hasta = QSpinBox()
        for s in (self.fila_desde, self.fila_hasta):
            s.setRange(1, max(n, 1))
        self.fila_hasta.setValue(max(n, 1))
        self.caja_x = QWidget()
        fx = QHBoxLayout(self.caja_x)
        fx.setContentsMargins(0, 0, 0, 0)
        fx.addWidget(self.columna_x)
        fx.addWidget(self.x_desde, 1)
        fx.addWidget(QLabel("–"))
        fx.addWidget(self.x_hasta, 1)
        self.caja_filas = QWidget()
        ff = QHBoxLayout(self.caja_filas)
        ff.setContentsMargins(0, 0, 0, 0)
        ff.addWidget(QLabel("de"))
        ff.addWidget(self.fila_desde)
        ff.addWidget(QLabel("a"))
        ff.addWidget(self.fila_hasta)
        ff.addStretch(1)

        self.columnas = QListWidget()
        for c in self._df.columns:
            item = QListWidgetItem(str(c))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.columnas.addItem(item)
        self.columnas.setMaximumHeight(120)

        self.formato = QComboBox()
        for k, (nombre, ext) in FORMATOS_GUARDAR.items():
            self.formato.addItem(f"{nombre} ({ext})", k)
        self.abrir_despues = QCheckBox("Abrir el fichero nuevo en lugar de la tabla actual")
        self.resumen = QLabel()
        self.resumen.setObjectName("secundario")

        form = self._form = QFormLayout()
        form.addRow("Filas:", self.modo)
        form.addRow("", self.caja_x)
        form.addRow("", self.caja_filas)
        form.addRow("Columnas:", self.columnas)
        form.addRow("Formato:", self.formato)
        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        self.b_guardar = botones.button(QDialogButtonBox.Save)
        capa = QVBoxLayout(self)
        capa.addLayout(form)
        capa.addWidget(self.abrir_despues)
        capa.addWidget(self.resumen)
        capa.addWidget(botones)

        for w in (self.modo, self.columna_x):
            w.currentIndexChanged.connect(self._actualizar)
        for w in (self.x_desde, self.x_hasta):
            w.textChanged.connect(self._actualizar)
        for w in (self.fila_desde, self.fila_hasta):
            w.valueChanged.connect(self._actualizar)
        self.columnas.itemChanged.connect(self._actualizar)
        self._actualizar()
        self.resize(540, self.sizeHint().height())

    # -- resultado -------------------------------------------------------------
    def filas(self) -> np.ndarray:
        """Índices (desde 0) de las filas que se guardan, en el orden de la tabla."""
        n = len(self._df)
        modo = self.modo.currentData()
        todas = np.arange(n)
        if modo == "incluidas":
            excluidas = self.modelo.excluidas
            return np.array([i for i in todas if i not in excluidas and not self.modelo.fuera_de_rango(i)], int)
        if modo == "rango" and self.modelo.rango_x is not None:
            lo, hi = self.modelo.rango_x
            x = self._df[self.columna_x.currentText()].to_numpy(float) if self.columna_x.currentText() else None
            if x is None:
                return todas[:0]
            return todas[np.isfinite(x) & (x >= lo) & (x <= hi)]
        if modo == "x":
            nombre = self.columna_x.currentText()
            if not nombre:
                return todas[:0]
            x = self._df[nombre].to_numpy(float)
            lo, hi = _numero(self.x_desde.text()), _numero(self.x_hasta.text())
            m = np.isfinite(x)
            if lo is not None:
                m &= x >= min(lo, hi if hi is not None else lo)
            if hi is not None:
                m &= x <= max(hi, lo if lo is not None else hi)
            return todas[m]
        if modo == "filas":
            a, b = sorted((self.fila_desde.value(), self.fila_hasta.value()))
            return todas[a - 1:b]
        if modo == "seleccion":
            return np.array([i for i in self._seleccionadas if i < n], int)
        return todas

    def columnas_elegidas(self) -> list[str]:
        return [self.columnas.item(i).text() for i in range(self.columnas.count())
                if self.columnas.item(i).checkState() == Qt.Checked]

    def tabla(self) -> pd.DataFrame:
        return self._df.iloc[self.filas()][self.columnas_elegidas()].reset_index(drop=True)

    def _actualizar(self, *_):
        modo = self.modo.currentData()
        self._form.setRowVisible(self.caja_x, modo in ("x", "rango"))  # sin dejar huecos
        for w in (self.x_desde, self.x_hasta):
            w.setEnabled(modo == "x")
        self._form.setRowVisible(self.caja_filas, modo == "filas")
        n_filas, n_cols = len(self.filas()), len(self.columnas_elegidas())
        self.resumen.setText(f"Se guardarán {n_filas} filas × {n_cols} columnas.")
        self.b_guardar.setEnabled(n_filas > 0 and n_cols > 0)
