"""Diálogos: personalizar la gráfica y exportarla para publicación.

La exportación tiene vista previa al tamaño real, formatos vectoriales (PDF, SVG,
EPS) y de imagen (PNG, TIFF), anchos de revista con proporción fija, tipografía
y tamaño de letra propios, texto editable en los vectoriales, copia al
portapapeles como PNG y SVG a la vez y, opcionalmente, los datos de la gráfica
en CSV (para rehacerla con pgfplots u otro programa).
"""
from __future__ import annotations

import io
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout)

from .grafica import COLORES_PUBLICACION, Escena, OpcionesGrafica, _malla, dibujar

# formato: (nombre en el diálogo, extensión, vectorial)
FORMATOS = {
    "png": ("PNG: imagen (Word, web, presentaciones)", "png", False),
    "pdf": ("PDF: vectorial (LaTeX, imprimir)", "pdf", True),
    "svg": ("SVG: vectorial (Inkscape, web)", "svg", True),
    "eps": ("EPS: vectorial (LaTeX antiguo, algunas revistas)", "eps", True),
    "tiff": ("TIFF: imagen sin pérdidas (imprenta, revistas)", "tif", False),
}
# Anchos habituales en cm (revistas de física: APS 8,6 / 17,8 cm)
ANCHOS = {
    "Una columna de revista (8,6 cm)": 8.6,
    "Doble columna (17,8 cm)": 17.8,
    "Informe A4 (16 cm)": 16.0,
    "Diapositiva (24 cm)": 24.0,
    "Póster (32 cm)": 32.0,
    "Personalizado": None,
}
# alto / ancho
PROPORCIONES = {"4:3": 3 / 4, "3:2": 2 / 3, "Áurea (1,618 : 1)": 1 / 1.618, "16:9": 9 / 16, "1:1": 1.0,
                "Libre": None}
FUENTES = {
    "sans": "Sans (DejaVu Sans, como en pantalla)",
    "serif": "Serif (STIX, tipo Times; fórmulas a juego)",
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
        self.ey2 = QLineEdit(o.etiqueta_y2)
        for w, ph in ((self.titulo, "sin título"), (self.ex, "nombre de la columna"), (self.ey, "nombre de la columna"),
                      (self.ey2, "nombre de la columna (pestaña Representar)")):
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
        form.addRow("Eje y derecho:", self.ey2)
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
        self.ey2.setText(d.etiqueta_y2)
        self.fuente.setValue(d.tam_fuente)
        self.leyenda.setChecked(d.leyenda)
        self.rejilla.setChecked(d.rejilla)
        self.cuadro.setChecked(d.cuadro_resultados)

    def aplicar(self, o: OpcionesGrafica) -> None:
        o.titulo = self.titulo.text()
        o.etiqueta_x = self.ex.text()
        o.etiqueta_y = self.ey.text()
        o.etiqueta_y2 = self.ey2.text()
        o.tam_fuente = self.fuente.value()
        o.leyenda = self.leyenda.isChecked()
        o.rejilla = self.rejilla.isChecked()
        o.cuadro_resultados = self.cuadro.isChecked()


@contextmanager
def estilo_fuente(fuente: str = "sans", editable: bool = True):
    """Parámetros de matplotlib para dibujar *y* guardar (la familia se fija al
    crear los textos y las fórmulas al dibujarlas: las dos cosas, dentro).

    * PDF/EPS con fuentes TrueType incrustadas (tipo 42), que es lo que piden las
      revistas y lo que permite editar el texto en Inkscape o Illustrator.
    * SVG con el texto como texto (editable) o convertido en trazos (se ve igual
      aunque el ordenador que lo abra no tenga la fuente)."""
    rc = {"pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none" if editable else "path"}
    if fuente == "serif":
        rc.update({"font.family": "serif", "font.serif": ["STIXGeneral", "DejaVu Serif"], "mathtext.fontset": "stix"})
    with matplotlib.rc_context(rc):
        yield


def renderizar(escena: Escena, opciones: OpcionesGrafica, colores: dict, oscuro: bool, ancho_cm: float,
               alto_cm: float, transparente: bool = False, fuente: str = "sans", tam_fuente: float | None = None,
               editable: bool = True) -> Figure:
    """Figura independiente con el tamaño exacto pedido (para exportar o copiar).

    Con ``constrained`` el contenido se ajusta *dentro* del tamaño pedido (no se
    recorta después), así que el fichero mide exactamente ancho × alto."""
    o = replace(opciones, tam_fuente=tam_fuente) if tam_fuente else opciones
    with estilo_fuente(fuente, editable):
        fig = Figure(figsize=(ancho_cm / 2.54, alto_cm / 2.54), layout="constrained")
        FigureCanvasAgg(fig)
        dibujar(fig, escena, o, colores, oscuro)
        if transparente:
            fig.patch.set_alpha(0)
            for ax in fig.axes:
                ax.patch.set_alpha(0)
    fig._ajustelab_fuente = (fuente, editable)  # para guardarla con el mismo estilo
    return fig


def guardar_figura(fig: Figure, ruta, formato: str | None = None, dpi: int = 300, transparente: bool = False) -> None:
    fuente, editable = getattr(fig, "_ajustelab_fuente", ("sans", True))
    formato = formato or Path(str(ruta)).suffix.lstrip(".").lower()
    formato = {"tif": "tiff", "jpg": "jpeg"}.get(formato, formato)
    extra = {"pil_kwargs": {"compression": "tiff_lzw"}} if formato == "tiff" else {}
    with estilo_fuente(fuente, editable):
        fig.savefig(ruta, format=formato, dpi=dpi, transparent=transparente and formato != "eps", **extra)


def _bytes(fig: Figure, formato: str, dpi: int = 200, transparente: bool = False) -> bytes:
    buf = io.BytesIO()
    guardar_figura(fig, buf, formato, dpi, transparente)
    return buf.getvalue()


def copiar_figura(fig: Figure, dpi: int = 200, transparente: bool = False) -> None:
    """Al portapapeles como imagen (PNG) y como SVG: los programas que entienden
    SVG (Inkscape, LibreOffice…) pegan la versión vectorial."""
    png = _bytes(fig, "png", dpi, transparente)
    mime = QMimeData()
    mime.setImageData(QImage.fromData(png, "PNG"))
    mime.setData("image/png", QByteArray(png))
    try:
        mime.setData("image/svg+xml", QByteArray(_bytes(fig, "svg", dpi, transparente)))
    except Exception:  # noqa: BLE001 — el SVG es un extra: si falla, queda la imagen
        pass
    QGuiApplication.clipboard().setMimeData(mime)


# --- datos de la gráfica ---------------------------------------------------------
def tablas_escena(escena: Escena, n: int = 400) -> dict[str, pd.DataFrame]:
    """Los números que hay dibujados, como tablas: puntos, curvas y bandas."""
    t: dict[str, pd.DataFrame] = {}
    e = escena
    if e.series:
        columnas = {}
        filas = sorted({int(f) for s in e.series if s.filas is not None for f in s.filas})
        indice = pd.Index(filas, name="fila")
        x = pd.Series(np.nan, index=indice)
        for s in e.series:
            idx = s.filas if s.filas is not None else np.arange(s.x.size)
            x.loc[idx] = s.x
            columnas[s.nombre] = pd.Series(s.y, index=idx)
            if s.dy is not None:
                columnas[f"σ {s.nombre}"] = pd.Series(s.dy, index=idx)
            if s.dx is not None and f"σ {e.nombre_x}" not in columnas:
                columnas[f"σ {e.nombre_x}"] = pd.Series(s.dx, index=idx)
        df = pd.DataFrame({e.nombre_x or "x": x, **columnas})
        df.index = pd.Index(df.index + 1, name="fila")  # filas como en la tabla (desde 1)
        t["datos"] = df.reset_index()
        return t
    if e.interseccion is not None:
        I = e.interseccion
        for k, r in ((1, I.ajuste1), (2, I.ajuste2)):
            d = r.datos
            t[f"conjunto{k}"] = pd.DataFrame({d.nombre_x: d.x, d.nombre_y: d.y, **({f"σ {d.nombre_y}": d.dy}
                                                                                     if d.dy is not None else {})})
            xx = np.linspace(min(d.x.min(), I.x), max(d.x.max(), I.x), n)
            t[f"ajuste{k}"] = pd.DataFrame({d.nombre_x: xx, "f": r.evaluar(xx)})
        t["interseccion"] = pd.DataFrame({"x*": [I.x], "σ x*": [I.sigma_x], "y*": [I.y], "σ y*": [I.sigma_y]})
        return t
    d = e.datos
    if d is None:
        return t
    puntos = {d.nombre_x: d.x}
    if d.tiene_dx:
        puntos[f"σ {d.nombre_x}"] = d.dx
    puntos[d.nombre_y] = d.y
    if d.dy is not None:
        puntos[f"σ {d.nombre_y}"] = d.dy
    puntos["incluido"] = d.incluidos.astype(int)
    t["datos"] = pd.DataFrame(puntos)
    if e.ajuste is not None:
        r = e.ajuste
        xx = _malla(r.datos.x, False, r.modelo, n)
        curva = {d.nombre_x: xx}
        if e.nivel_banda:
            f, lo, hi = r.banda(xx, nivel=e.nivel_banda, prediccion=e.prediccion)
            curva.update({"f": f, "banda_inferior": lo, "banda_superior": hi})
        else:
            curva["f"] = r.evaluar(xx)
        t["ajuste"] = pd.DataFrame(curva)
    for k, r in enumerate(e.comparar[:3], 1):
        xx = _malla(r.datos.x, False, r.modelo, n)
        t[f"modelo{k}"] = pd.DataFrame({d.nombre_x: xx, r.modelo.nombre: r.evaluar(xx)})
    if e.interpolacion is not None:
        lo, hi = e.interpolacion.rango
        xx = np.linspace(lo, hi, n)
        t["interpolacion"] = pd.DataFrame({d.nombre_x: xx, "f": e.interpolacion(xx)})
    return t


def guardar_tablas(escena: Escena, ruta_figura: Path) -> list[Path]:
    rutas = []
    for nombre, df in tablas_escena(escena).items():
        ruta = ruta_figura.with_name(f"{ruta_figura.stem}_{nombre}.csv")
        df.to_csv(ruta, index=False, encoding="utf-8")
        rutas.append(ruta)
    return rutas


# --- diálogo de exportación -----------------------------------------------------------
class VistaPrevia(QLabel):
    """La figura tal como saldrá, a escala, sobre un damero si el fondo es transparente."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(QSize(460, 340))
        self.setAlignment(Qt.AlignCenter)
        self.setFrameShape(QFrame.StyledPanel)

    def mostrar(self, png: bytes, transparente: bool) -> None:
        img = QImage.fromData(png, "PNG")
        dpr = self.devicePixelRatioF()
        disponible = QSize(int((self.width() - 16) * dpr), int((self.height() - 16) * dpr))
        img = img.scaled(disponible, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lienzo = QPixmap(img.size())
        lienzo.fill(Qt.white)
        p = QPainter(lienzo)
        if transparente:
            lado = int(8 * dpr)
            gris = QColor("#d9d9d6")
            for i in range(0, img.width(), lado):
                for j in range(0, img.height(), lado):
                    if (i // lado + j // lado) % 2:
                        p.fillRect(i, j, lado, lado, gris)
        p.drawImage(0, 0, img)
        p.end()
        lienzo.setDevicePixelRatio(dpr)
        self.setPixmap(lienzo)


class DialogoExportar(QDialog):
    """Formato, tamaño (anchos de revista + proporción), resolución, estilo,
    tipografía y tamaño de letra, con vista previa al tamaño real."""

    def __init__(self, parent=None, ultimo: dict | None = None, escena: Escena | None = None,
                 opciones: OpcionesGrafica | None = None, tema=None):
        super().__init__(parent)
        self.setWindowTitle("Exportar gráfica")
        self.escena, self.opciones, self.tema = escena, opciones, tema
        u = ultimo or {}
        self.formato = QComboBox()
        for k, (texto, _, _) in FORMATOS.items():
            self.formato.addItem(texto, k)
        self.formato.setCurrentIndex(max(0, self.formato.findData(u.get("formato", "png"))))
        self.preset = QComboBox()
        self.preset.addItems(list(ANCHOS))
        self.proporcion = QComboBox()
        self.proporcion.addItems(list(PROPORCIONES))
        self.proporcion.setCurrentText(u.get("proporcion", "4:3") if u.get("proporcion") in PROPORCIONES else "4:3")
        self.ancho = QDoubleSpinBox()
        self.alto = QDoubleSpinBox()
        for w in (self.ancho, self.alto):
            w.setRange(3, 80)
            w.setSuffix(" cm")
            w.setDecimals(1)
            w.setSingleStep(0.5)
        self.ancho.setValue(u.get("ancho", 16.0))
        self.alto.setValue(u.get("alto", 12.0))
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 1200)
        self.dpi.setSingleStep(50)
        self.dpi.setValue(u.get("dpi", 300))
        self.dpi.setSuffix(" ppp")
        self.estilo = QComboBox()
        self.estilo.addItem("Publicación (fondo blanco)", "publicacion")
        self.estilo.addItem("Como en pantalla", "pantalla")
        self.estilo.setCurrentIndex(0 if u.get("estilo", "publicacion") == "publicacion" else 1)
        self.fuente = QComboBox()
        for k, v in FUENTES.items():
            self.fuente.addItem(v, k)
        self.fuente.setCurrentIndex(max(0, self.fuente.findData(u.get("fuente", "sans"))))
        self.tam_fuente = QDoubleSpinBox()
        self.tam_fuente.setRange(5, 30)
        self.tam_fuente.setSingleStep(0.5)
        self.tam_fuente.setSuffix(" pt")
        self.tam_fuente.setValue(u.get("tam_fuente", opciones.tam_fuente if opciones else 10.0))
        self.tam_fuente.setToolTip("Tamaño real en el papel. Las revistas suelen pedir de 7 a 9 pt.")
        self.transparente = QCheckBox("Fondo transparente")
        self.transparente.setChecked(u.get("transparente", False))
        self.editable = QCheckBox("Texto editable (PDF, SVG, EPS)")
        self.editable.setChecked(u.get("editable", True))
        self.editable.setToolTip("Las fuentes se incrustan y el texto se puede editar en Inkscape o Illustrator.\n"
                                 "Sin marcar, en SVG el texto se convierte en trazos (se ve igual en cualquier "
                                 "ordenador, pero ya no es texto).")
        self.con_datos = QCheckBox("Guardar también los datos de la gráfica (CSV)")
        self.con_datos.setChecked(u.get("datos", False))
        self.con_datos.setToolTip("Puntos, curvas y bandas en ficheros .csv junto a la figura, para rehacerla "
                                  "con pgfplots u otro programa.")
        self.aviso = QLabel()
        self.aviso.setObjectName("secundario")
        self.aviso.setWordWrap(True)
        self.vista = VistaPrevia()
        self.info = QLabel()
        self.info.setObjectName("secundario")
        self.info.setAlignment(Qt.AlignCenter)

        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(180)
        self._temporizador.timeout.connect(self._actualizar_vista)
        self.preset.currentTextChanged.connect(self._al_preset)
        self.proporcion.currentTextChanged.connect(self._al_proporcion)
        self.ancho.valueChanged.connect(self._al_ancho)
        self.alto.valueChanged.connect(self._al_alto)
        for w in (self.formato, self.estilo, self.fuente):
            w.currentIndexChanged.connect(self._cambio)
        for w in (self.dpi, self.tam_fuente):
            w.valueChanged.connect(self._cambio)
        for w in (self.transparente, self.editable):
            w.toggled.connect(self._cambio)
        self._sincronizar_preset()
        self._al_proporcion(self.proporcion.currentText())

        form = QFormLayout()
        form.addRow("Formato:", self.formato)
        form.addRow("Ancho:", self.preset)
        dims = QHBoxLayout()
        dims.addWidget(self.ancho)
        dims.addWidget(QLabel("×"))
        dims.addWidget(self.alto)
        form.addRow("", dims)
        form.addRow("Proporción:", self.proporcion)
        form.addRow("Resolución:", self.dpi)
        form.addRow("Estilo:", self.estilo)
        form.addRow("Tipografía:", self.fuente)
        form.addRow("Tamaño de letra:", self.tam_fuente)
        form.addRow(self.transparente)
        form.addRow(self.editable)
        form.addRow(self.con_datos)
        form.addRow(self.aviso)
        derecha = QVBoxLayout()
        derecha.addWidget(self.vista, 1)
        derecha.addWidget(self.info)
        cuerpo = QHBoxLayout()
        cuerpo.addLayout(form)
        cuerpo.addLayout(derecha, 1)

        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.b_copiar = botones.addButton("Copiar al portapapeles", QDialogButtonBox.ActionRole)
        botones.button(QDialogButtonBox.Save).setText("Guardar…")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        self.b_copiar.clicked.connect(lambda: self.done(2))
        capa = QVBoxLayout(self)
        capa.addLayout(cuerpo, 1)
        capa.addWidget(botones)
        self._cambio()

    # -- tamaño -------------------------------------------------------------
    def _fijar(self, w, valor):
        w.blockSignals(True)
        w.setValue(valor)
        w.blockSignals(False)

    def _sincronizar_preset(self):
        nombre = next((k for k, v in ANCHOS.items() if v is not None and abs(v - self.ancho.value()) < 0.05),
                      "Personalizado")
        self.preset.blockSignals(True)
        self.preset.setCurrentText(nombre)
        self.preset.blockSignals(False)

    def _alto_segun_proporcion(self):
        r = PROPORCIONES.get(self.proporcion.currentText())
        if r is not None:
            self._fijar(self.alto, round(self.ancho.value() * r, 1))

    def _al_preset(self, nombre):
        v = ANCHOS.get(nombre)
        if v:
            self._fijar(self.ancho, v)
            if nombre.startswith("Diapositiva"):
                self.proporcion.setCurrentText("16:9")
            self._alto_segun_proporcion()
            self._cambio()

    def _al_proporcion(self, nombre):
        self.alto.setEnabled(PROPORCIONES.get(nombre) is None)
        self._alto_segun_proporcion()
        self._cambio()

    def _al_ancho(self, *_):
        self._sincronizar_preset()
        self._alto_segun_proporcion()
        self._cambio()

    def _al_alto(self, *_):
        self._cambio()

    # -- vista previa ------------------------------------------------------------
    def _cambio(self, *_):
        formato = self.formato.currentData()
        vectorial = FORMATOS[formato][2]
        self.dpi.setEnabled(not vectorial)
        self.editable.setEnabled(vectorial)
        self.transparente.setEnabled(formato != "eps")
        avisos = []
        if formato == "eps":
            avisos.append("EPS no admite transparencias: las bandas de confianza saldrían opacas. Para LaTeX, "
                          "mejor PDF.")
        if self.tam_fuente.value() < 7:
            avisos.append("Por debajo de 7 pt el texto cuesta de leer impreso.")
        self.aviso.setText("\n".join(avisos))
        self.aviso.setVisible(bool(avisos))
        ancho, alto = self.ancho.value(), self.alto.value()
        texto = f"{ancho:.1f} × {alto:.1f} cm".replace(".", ",")
        if not vectorial:
            px = (int(ancho / 2.54 * self.dpi.value()), int(alto / 2.54 * self.dpi.value()))  # como matplotlib
            texto += f"  ·  {px[0]} × {px[1]} px a {self.dpi.value()} ppp"
        else:
            texto += "  ·  vectorial: se puede ampliar sin perder calidad"
        self.info.setText(texto)
        self._temporizador.start()

    def figura(self) -> Figure | None:
        if self.escena is None or self.opciones is None:
            return None
        v = self.valores()
        publicacion = v["estilo"] == "publicacion" or self.tema is None
        colores = COLORES_PUBLICACION if publicacion else self.tema.colores()
        oscuro = False if publicacion else self.tema.oscuro
        return renderizar(self.escena, self.opciones, colores, oscuro, v["ancho"], v["alto"],
                          v["transparente"] and v["formato"] != "eps", v["fuente"], v["tam_fuente"], v["editable"])

    def _actualizar_vista(self):
        fig = self.figura()
        if fig is None:
            return
        pulgadas = max(self.ancho.value(), self.alto.value()) / 2.54
        lado = max(self.vista.width(), self.vista.height()) * self.vista.devicePixelRatioF()
        dpi = max(30, min(200, lado / pulgadas))
        transparente = self.transparente.isChecked() and self.formato.currentData() != "eps"
        self.vista.mostrar(_bytes(fig, "png", int(dpi), transparente), transparente)

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self._temporizador.start()

    def valores(self) -> dict:
        return {"formato": self.formato.currentData(), "ancho": self.ancho.value(), "alto": self.alto.value(),
                "proporcion": self.proporcion.currentText(), "dpi": self.dpi.value(),
                "estilo": self.estilo.currentData(), "fuente": self.fuente.currentData(),
                "tam_fuente": self.tam_fuente.value(), "transparente": self.transparente.isChecked(),
                "editable": self.editable.isChecked(), "datos": self.con_datos.isChecked()}


def figura_para(grafica, v: dict) -> Figure:
    """Figura con los ajustes de exportación ``v`` (los del diálogo o los últimos usados)."""
    publicacion = v.get("estilo", "publicacion") == "publicacion"
    colores = COLORES_PUBLICACION if publicacion else grafica.tema.colores()
    oscuro = False if publicacion else grafica.tema.oscuro
    return renderizar(grafica.escena, grafica.opciones, colores, oscuro, v.get("ancho", 16.0), v.get("alto", 12.0),
                      v.get("transparente", False) and v.get("formato") != "eps", v.get("fuente", "sans"),
                      v.get("tam_fuente"), v.get("editable", True))


def exportar(ventana, grafica, ultimo: dict | None, ruta_sugerida: str) -> dict | None:
    """Abre el diálogo y guarda o copia la figura. Devuelve los valores usados."""
    dlg = DialogoExportar(ventana, ultimo, grafica.escena, grafica.opciones, grafica.tema)
    r = dlg.exec()
    if r == QDialog.Rejected:
        return None
    v = dlg.valores()
    fig = figura_para(grafica, v)
    if r == 2:
        copiar_figura(fig, dpi=min(v["dpi"], 300), transparente=v["transparente"])
        ventana.notificar("Gráfica copiada al portapapeles (imagen y SVG).", "bueno")
        return v
    texto, ext, _ = FORMATOS[v["formato"]]
    sugerida = str(Path(ruta_sugerida).with_suffix("." + ext))
    ruta, _ = QFileDialog.getSaveFileName(ventana, "Exportar gráfica", sugerida, f"{texto.split(':')[0]} (*.{ext})")
    if not ruta:
        return None
    ruta = Path(ruta)
    if ruta.suffix.lower().lstrip(".") not in (ext, v["formato"]):
        ruta = ruta.with_name(ruta.name + "." + ext)
    guardar_figura(fig, ruta, v["formato"], v["dpi"], v["transparente"])
    mensaje = f"Gráfica guardada en {ruta}"
    if v["datos"]:
        tablas = guardar_tablas(grafica.escena, ruta)
        if tablas:
            mensaje += f" (y {len(tablas)} CSV con los datos)"
    ventana.notificar(mensaje, "bueno")
    return v
