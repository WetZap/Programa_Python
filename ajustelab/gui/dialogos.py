"""Diálogos: personalizar la gráfica y exportarla para publicación."""
from __future__ import annotations

import io

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout)

from .grafica import COLORES_PUBLICACION, Escena, OpcionesGrafica, dibujar

# Tamaños habituales (ancho, alto) en cm
PRESETS = {
    "Una columna (8,5 × 6,5 cm)": (8.5, 6.5),
    "Doble columna (17 × 10 cm)": (17.0, 10.0),
    "Informe A4 (16 × 11 cm)": (16.0, 11.0),
    "Diapositiva 16:9 (24 × 13,5 cm)": (24.0, 13.5),
    "Personalizado": None,
}


class DialogoPersonalizar(QDialog):
    """Título, etiquetas (admiten LaTeX entre $…$), letra, leyenda, rejilla, cuadro de resultados."""

    def __init__(self, opciones: OpcionesGrafica, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personalizar gráfica")
        o = opciones
        self.titulo = QLineEdit(o.titulo)
        self.ex = QLineEdit(o.etiqueta_x)
        self.ey = QLineEdit(o.etiqueta_y)
        for w, ph in ((self.titulo, "sin título"), (self.ex, "nombre de la columna"), (self.ey, "nombre de la columna")):
            w.setPlaceholderText(ph)
            w.setToolTip("Admite fórmulas LaTeX entre $…$, p. ej. $\\lambda$ (nm) o $t$ (s)")
        self.fuente = QDoubleSpinBox()
        self.fuente.setRange(6, 24)
        self.fuente.setSingleStep(0.5)
        self.fuente.setValue(o.tam_fuente)
        self.leyenda = QCheckBox("Mostrar leyenda")
        self.leyenda.setChecked(o.leyenda)
        self.rejilla = QCheckBox("Mostrar rejilla")
        self.rejilla.setChecked(o.rejilla)
        self.cuadro = QCheckBox("Cuadro con la ecuación y los parámetros (arrastrable)")
        self.cuadro.setChecked(o.cuadro_resultados)
        form = QFormLayout(self)
        form.addRow("Título:", self.titulo)
        form.addRow("Eje x:", self.ex)
        form.addRow("Eje y:", self.ey)
        form.addRow("Tamaño de letra:", self.fuente)
        form.addRow(self.leyenda)
        form.addRow(self.rejilla)
        form.addRow(self.cuadro)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        botones.button(QDialogButtonBox.Reset).setText("Restablecer")
        botones.button(QDialogButtonBox.Reset).clicked.connect(self._restablecer)
        form.addRow(botones)

    def _restablecer(self):
        d = OpcionesGrafica()
        self.titulo.setText(d.titulo)
        self.ex.setText(d.etiqueta_x)
        self.ey.setText(d.etiqueta_y)
        self.fuente.setValue(d.tam_fuente)
        self.leyenda.setChecked(d.leyenda)
        self.rejilla.setChecked(d.rejilla)
        self.cuadro.setChecked(d.cuadro_resultados)

    def aplicar(self, o: OpcionesGrafica) -> None:
        o.titulo = self.titulo.text()
        o.etiqueta_x = self.ex.text()
        o.etiqueta_y = self.ey.text()
        o.tam_fuente = self.fuente.value()
        o.leyenda = self.leyenda.isChecked()
        o.rejilla = self.rejilla.isChecked()
        o.cuadro_resultados = self.cuadro.isChecked()


def renderizar(escena: Escena, opciones: OpcionesGrafica, colores: dict, oscuro: bool, ancho_cm: float,
               alto_cm: float, transparente: bool = False) -> Figure:
    """Figura independiente con el tamaño pedido (para exportar o copiar)."""
    fig = Figure(figsize=(ancho_cm / 2.54, alto_cm / 2.54), layout="constrained")
    FigureCanvasAgg(fig)
    dibujar(fig, escena, opciones, colores, oscuro)
    if transparente:
        fig.patch.set_alpha(0)
        for ax in fig.axes:
            ax.patch.set_alpha(0)
    return fig


def copiar_figura(fig: Figure, dpi: int = 200) -> None:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    QGuiApplication.clipboard().setImage(QImage.fromData(buf.getvalue(), "PNG"))


class DialogoExportar(QDialog):
    """Formato, tamaño en cm (con preajustes), resolución y estilo."""

    def __init__(self, parent=None, ultimo: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Exportar gráfica")
        u = ultimo or {}
        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS))
        self.ancho = QDoubleSpinBox()
        self.alto = QDoubleSpinBox()
        for w in (self.ancho, self.alto):
            w.setRange(3, 60)
            w.setSuffix(" cm")
            w.setDecimals(1)
        self.ancho.setValue(u.get("ancho", 16.0))
        self.alto.setValue(u.get("alto", 11.0))
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 1200)
        self.dpi.setValue(u.get("dpi", 300))
        self.dpi.setSuffix(" ppp")
        self.estilo = QComboBox()
        self.estilo.addItem("Publicación (fondo blanco)", "publicacion")
        self.estilo.addItem("Como en pantalla", "pantalla")
        self.estilo.setCurrentIndex(0 if u.get("estilo", "publicacion") == "publicacion" else 1)
        self.transparente = QCheckBox("Fondo transparente")
        self.transparente.setChecked(u.get("transparente", False))
        self.preset.currentTextChanged.connect(self._al_preset)
        self.ancho.valueChanged.connect(self._marcar_personalizado)
        self.alto.valueChanged.connect(self._marcar_personalizado)
        self._sincronizar_preset()

        form = QFormLayout()
        form.addRow("Tamaño:", self.preset)
        dims = QHBoxLayout()
        dims.addWidget(self.ancho)
        dims.addWidget(QLabel("×"))
        dims.addWidget(self.alto)
        form.addRow("", dims)
        form.addRow("Resolución (PNG):", self.dpi)
        form.addRow("Estilo:", self.estilo)
        form.addRow(self.transparente)
        nota = QLabel("PDF y SVG son vectoriales: la resolución solo afecta a PNG.")
        nota.setObjectName("secundario")
        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.b_copiar = botones.addButton("Copiar al portapapeles", QDialogButtonBox.ActionRole)
        botones.button(QDialogButtonBox.Save).setText("Guardar…")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        self.b_copiar.clicked.connect(lambda: self.done(2))
        capa = QVBoxLayout(self)
        capa.addLayout(form)
        capa.addWidget(nota)
        capa.addWidget(botones)

    def _sincronizar_preset(self):
        actual = (round(self.ancho.value(), 1), round(self.alto.value(), 1))
        nombre = next((k for k, v in PRESETS.items() if v == actual), "Personalizado")
        self.preset.blockSignals(True)
        self.preset.setCurrentText(nombre)
        self.preset.blockSignals(False)

    def _al_preset(self, nombre):
        v = PRESETS.get(nombre)
        if v:
            for w, val in ((self.ancho, v[0]), (self.alto, v[1])):
                w.blockSignals(True)
                w.setValue(val)
                w.blockSignals(False)

    def _marcar_personalizado(self, *_):
        self._sincronizar_preset()

    def valores(self) -> dict:
        return {"ancho": self.ancho.value(), "alto": self.alto.value(), "dpi": self.dpi.value(),
                "estilo": self.estilo.currentData(), "transparente": self.transparente.isChecked()}


def exportar(ventana, grafica, ultimo: dict | None, ruta_sugerida: str) -> dict | None:
    """Abre el diálogo y guarda o copia la figura. Devuelve los valores usados."""
    dlg = DialogoExportar(ventana, ultimo)
    r = dlg.exec()
    if r == QDialog.Rejected:
        return None
    v = dlg.valores()
    publicacion = v["estilo"] == "publicacion"
    colores = COLORES_PUBLICACION if publicacion else grafica.tema.colores()
    oscuro = False if publicacion else grafica.tema.oscuro
    fig = renderizar(grafica.escena, grafica.opciones, colores, oscuro, v["ancho"], v["alto"], v["transparente"])
    if r == 2:
        copiar_figura(fig, dpi=min(v["dpi"], 300))
        ventana.notificar("Gráfica copiada al portapapeles.", "bueno")
        return v
    ruta, _ = QFileDialog.getSaveFileName(ventana, "Exportar gráfica", ruta_sugerida,
                                          "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
    if not ruta:
        return None
    fig.savefig(ruta, dpi=v["dpi"], transparent=v["transparente"])
    ventana.notificar(f"Gráfica guardada en {ruta}", "bueno")
    return v

