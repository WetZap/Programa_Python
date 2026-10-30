"""Gráfica integrada (matplotlib en Qt).

* El dibujo está en :func:`dibujar`, independiente del widget, para que la
  exportación (otro tamaño, estilo de publicación) use exactamente el mismo código.
* Herramientas sobre la gráfica:
    - clic en un punto → excluir/incluir;
    - **Región**: arrastrar un rectángulo excluye (o vuelve a incluir) todos los
      puntos de dentro;
    - **Rango**: arrastrar en horizontal fija el rango de x usado en el ajuste;
    - zoom y desplazamiento con la barra de matplotlib.
* Cuadro de resultados (ecuación + parámetros + χ²_ν) que se puede arrastrar.
* Vista previa del modelo con los valores iniciales, comparación de varios
  ajustes, banda de confianza o de predicción.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse
from matplotlib.widgets import RectangleSelector, SpanSelector
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from ..ajuste import ResultadoAjuste
from ..datos import Datos
from ..estadistica import formatear
from ..interpolacion import METODOS, Interpolacion
from ..interseccion import Interseccion
from ..modelos import Modelo
from .iconos import icono
from .tema import GestorTema

_RADIO_CLIC_PX = 9
_ESTILOS_COMPARAR = ["--", ":", "-."]
_RE_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")

# Colores fijos para exportar con estilo de publicación (fondo blanco)
COLORES_PUBLICACION = {
    "datos": "#2a78d6", "ajuste": "#eb6834", "interpolacion": "#1baf7a", "interseccion": "#6250d6",
    "fondo": "#ffffff", "ejes": "#ffffff", "texto": "#111111", "secundario": "#55554f", "rejilla": "#d4d4d0",
    "excluidos": "#9a9a95",
}
COLORES_COMPARAR = {False: ["#1baf7a", "#6250d6", "#c98500"], True: ["#199e70", "#9085e9", "#eda100"]}


def con_coma(texto: str) -> str:
    """3.142 ± 0.023 → 3,142 ± 0,023 (solo puntos entre cifras)."""
    return _RE_DECIMAL.sub(",", texto)


@dataclass
class OpcionesGrafica:
    titulo: str = ""
    etiqueta_x: str = ""  # vacío: nombre de la columna
    etiqueta_y: str = ""
    tam_fuente: float = 10.0
    leyenda: bool = True
    rejilla: bool = True
    cuadro_resultados: bool = True
    pos_cuadro: tuple[float, float] = (0.03, 0.04)  # esquina inferior izquierda, fracción de los ejes
    log_x: bool = False
    log_y: bool = False
    residuos: bool = True

    def a_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def desde_dict(cls, d: dict) -> "OpcionesGrafica":
        o = cls()
        for k, v in (d or {}).items():
            if hasattr(o, k):
                setattr(o, k, tuple(v) if k == "pos_cuadro" else v)
        return o


@dataclass
class Escena:
    """Qué hay que dibujar. ``filas[i]`` es la fila de la tabla del punto i de ``datos``."""

    datos: Datos | None = None
    filas: np.ndarray | None = None
    ajuste: ResultadoAjuste | None = None
    nivel_banda: float | None = 0.6827
    prediccion: bool = False
    interpolacion: Interpolacion | None = None
    interseccion: Interseccion | None = None
    previa: tuple[Modelo, np.ndarray] | None = None  # (modelo, p iniciales)
    comparar: list[ResultadoAjuste] = field(default_factory=list)
    rango: tuple[float, float] | None = None
    coma_decimal: bool = False


# ---------------------------------------------------------------------------
# Dibujo (sin Qt)
# ---------------------------------------------------------------------------
def _estilo_ejes(ax, c, o: OpcionesGrafica):
    ax.set_facecolor(c["ejes"])
    ax.tick_params(colors=c["texto"], labelsize=o.tam_fuente * 0.9)
    for lado in ax.spines.values():
        lado.set_color(c["rejilla"])
    if o.rejilla:
        ax.grid(True, color=c["rejilla"], linewidth=0.6, alpha=0.8)
    ax.xaxis.label.set_color(c["texto"])
    ax.yaxis.label.set_color(c["texto"])
    ax.xaxis.label.set_size(o.tam_fuente)
    ax.yaxis.label.set_size(o.tam_fuente)


def _malla(x: np.ndarray, log: bool, modelo=None, n: int = 600, extremos=None) -> np.ndarray:
    lo, hi = (float(np.min(x)), float(np.max(x))) if extremos is None else extremos
    if log and lo > 0:
        return np.geomspace(lo, hi, n)
    margen = 0.02 * (hi - lo)
    malla = np.linspace(lo - margen, hi + margen, n)
    if modelo is not None and not modelo.dominio_valido(malla):
        malla = np.linspace(lo, hi, n)
    return malla


def _texto_resultados(r: ResultadoAjuste, coma: bool) -> str:
    lineas = []
    try:
        from matplotlib.mathtext import MathTextParser

        ecuacion = f"$y = {r.modelo.original.latex}$"
        MathTextParser("path").parse(ecuacion)
        lineas.append(ecuacion)
    except Exception:  # LaTeX no representable: texto plano
        lineas.append(f"y = {r.modelo.expresion}")
    for n, v, e in zip(r.nombres, r.p, r.sigma_p):
        lineas.append(f"{n} = {formatear(v, e)}")
    for n, v in r.fijos.items():
        lineas.append(f"{n} = {v:g} (fijo)")
    if r.errores_absolutos and r.nu > 0:
        b = r.bondad()
        lineas.append(f"χ²/ν = {b.chi2_red:.3g}   p = {b.p_valor:.2g}")
    texto = "\n".join(lineas)
    return con_coma(texto) if coma else texto


def dibujar(fig: Figure, e: Escena, o: OpcionesGrafica, c: dict, oscuro: bool = False):
    """Dibuja la escena en ``fig``. Devuelve (ejes principales, ejes de residuos o None, cuadro de resultados)."""
    fig.clear()
    fig.set_facecolor(c["fondo"])
    con_residuos = o.residuos and e.ajuste is not None and e.interseccion is None
    if con_residuos:
        ax, axr = fig.subplots(2, 1, sharex=True, height_ratios=[3, 1])
    else:
        ax, axr = fig.subplots(1, 1), None
    for a in (ax, axr):
        if a is not None:
            _estilo_ejes(a, c, o)

    cuadro = None
    if e.interseccion is not None:
        _dibujar_interseccion(ax, e.interseccion, c, o)
    elif e.datos is not None:
        _dibujar_datos(ax, e, c)
        if e.rango is not None:
            _dibujar_rango(ax, e.rango, c)
        if e.previa is not None:
            modelo, p = e.previa
            xx = _malla(e.datos.x, o.log_x, modelo)
            with np.errstate(all="ignore"):
                yy = modelo(xx, *p)
            if np.any(np.isfinite(yy)):
                ax.plot(xx, yy, color=c["ajuste"], linewidth=1.6, linestyle=(0, (5, 3)), alpha=0.85,
                        label="Vista previa (valores iniciales)", zorder=4)
        for i, r in enumerate(e.comparar[:3]):
            xx = _malla(r.datos.x, o.log_x, r.modelo)
            ax.plot(xx, r.evaluar(xx), color=COLORES_COMPARAR[oscuro][i], linewidth=1.8,
                    linestyle=_ESTILOS_COMPARAR[i], label=r.modelo.nombre, zorder=4)
        if e.ajuste is not None:
            _dibujar_ajuste(ax, e.ajuste, e.nivel_banda, e.prediccion, c, o, oscuro)
            if axr is not None:
                _dibujar_residuos(ax, axr, e.ajuste, c)
            if o.cuadro_resultados:
                cuadro = ax.annotate(_texto_resultados(e.ajuste, e.coma_decimal), xy=o.pos_cuadro,
                                     xycoords="axes fraction", ha="left", va="bottom", fontsize=o.tam_fuente * 0.85,
                                     color=c["texto"], zorder=10,
                                     bbox=dict(boxstyle="round,pad=0.5", fc=c["ejes"], ec=c["rejilla"], alpha=0.92))
        if e.interpolacion is not None:
            _dibujar_interpolacion(ax, e.interpolacion, c, o)
    if o.titulo:
        ax.set_title(o.titulo, color=c["texto"], fontsize=o.tam_fuente * 1.15)
    if o.etiqueta_x:
        (axr or ax).set_xlabel(o.etiqueta_x)
    if o.etiqueta_y:
        ax.set_ylabel(o.etiqueta_y)

    xs = e.datos.x if e.datos is not None else None
    ys = e.datos.y if e.datos is not None else None
    if o.log_x and (xs is None or np.all(xs > 0)):
        ax.set_xscale("log")
    if o.log_y and (ys is None or np.all(ys > 0)):
        ax.set_yscale("log")
    handles, labels = ax.get_legend_handles_labels()
    if o.leyenda and len(handles) >= 2:
        ley = ax.legend(fontsize=o.tam_fuente * 0.85, framealpha=0.9, facecolor=c["ejes"], edgecolor=c["rejilla"],
                        loc="best")
        for t in ley.get_texts():
            t.set_color(c["texto"])
    return ax, axr, cuadro


def _dibujar_datos(ax, e: Escena, c, color=None, etiqueta="Datos"):
    d = e.datos
    color = color or c["datos"]
    m = d.incluidos
    dx = d.dx if d.tiene_dx else None
    dy = d.dy
    sel = (lambda arr, mask: None if arr is None else arr[mask])
    if np.any(m):
        ax.errorbar(d.x[m], d.y[m], xerr=sel(dx, m), yerr=sel(dy, m), fmt="o", ms=5, color=color,
                    ecolor=color, elinewidth=1, capsize=2, alpha=0.95, label=etiqueta, zorder=3)
    if np.any(~m):
        ax.errorbar(d.x[~m], d.y[~m], xerr=sel(dx, ~m), yerr=sel(dy, ~m), fmt="o", ms=6, mfc="none",
                    color=c["excluidos"], ecolor=c["excluidos"], elinewidth=0.8, capsize=2,
                    label="Excluidos / fuera de rango", zorder=2)
    ax.set_xlabel(d.nombre_x)
    ax.set_ylabel(d.nombre_y)


def _dibujar_rango(ax, rango, c):
    lo, hi = rango
    ax.axvline(lo, color=c["secundario"], linewidth=1, linestyle="--", zorder=1)
    ax.axvline(hi, color=c["secundario"], linewidth=1, linestyle="--", zorder=1)
    ax.axvspan(lo, hi, color=c["datos"], alpha=0.06, linewidth=0, zorder=0)


def _dibujar_ajuste(ax, r: ResultadoAjuste, nivel, prediccion, c, o, oscuro):
    color = c["ajuste"]
    xx = _malla(r.datos.x, o.log_x, r.modelo)
    if nivel:
        f, lo, hi = r.banda(xx, nivel=nivel, prediccion=prediccion)
        tipo = "Predicción" if prediccion else "Banda"
        ax.fill_between(xx, lo, hi, color=color, alpha=0.30 if oscuro else 0.20, linewidth=0,
                        label=f"{tipo} {nivel * 100:.0f} %", zorder=1)
    else:
        f = r.evaluar(xx)
    ax.plot(xx, f, color=color, linewidth=2, label=f"Ajuste: {r.modelo.nombre}", zorder=5)


def _dibujar_residuos(ax, axr, r: ResultadoAjuste, c):
    rn = r.residuos_norm
    axr.axhline(0, color=c["texto"], linewidth=0.8)
    for k in (-2, 2):
        axr.axhline(k, color=c["rejilla"], linewidth=0.8, linestyle="--")
    axr.plot(r.datos.x, rn, "o", ms=4, color=c["datos"])
    axr.set_ylabel("(y − f)/σ" if r.errores_absolutos else "(y − f)/s", fontsize=9)
    lim = max(3.0, float(np.nanmax(np.abs(rn))) * 1.15) if np.any(np.isfinite(rn)) else 3.0
    axr.set_ylim(-lim, lim)
    axr.set_xlabel(r.datos.nombre_x)
    ax.set_xlabel("")


def _dibujar_interpolacion(ax, f: Interpolacion, c, o):
    lo, hi = f.rango
    xx = np.geomspace(lo, hi, 800) if (o.log_x and lo > 0) else np.linspace(lo, hi, 800)
    ax.plot(xx, f(xx), color=c["interpolacion"], linewidth=2, label=METODOS[f.metodo], zorder=4)


def _dibujar_interseccion(ax, I: Interseccion, c, o):
    for r, color, n in ((I.ajuste1, c["datos"], 1), (I.ajuste2, c["ajuste"], 2)):
        d = r.datos
        ax.errorbar(d.x, d.y, xerr=d.dx if d.tiene_dx else None, yerr=d.dy, fmt="o", ms=5, color=color,
                    ecolor=color, elinewidth=1, capsize=2, label=f"Conjunto {n}", zorder=3)
        lo, hi = min(np.min(d.x), I.x), max(np.max(d.x), I.x)
        margen = 0.05 * (hi - lo)
        xx = np.linspace(lo - margen, hi + margen, 400)
        if r.modelo.dominio_valido(xx):
            ax.plot(xx, r.evaluar(xx), color=color, linewidth=2, label=f"Ajuste {n}: {r.modelo.nombre}", zorder=4)
        ax.set_xlabel(d.nombre_x)
        ax.set_ylabel(d.nombre_y)
    ancho, alto, ang = I.elipse(0.6827)
    ax.add_patch(Ellipse((I.x, I.y), ancho, alto, angle=ang, facecolor=c["interseccion"], alpha=0.3,
                         edgecolor=c["interseccion"], linewidth=1.5, zorder=5))
    ax.plot([I.x], [I.y], "D", ms=7, color=c["interseccion"], label="Intersección (región 68 %)", zorder=6)


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------
class BarraNavegacion(NavigationToolbar2QT):
    """Barra de matplotlib reducida a inicio/atrás/adelante/desplazar/zoom
    (guardar y personalizar tienen sus propios diálogos en ajustelab)."""

    toolitems = [t for t in NavigationToolbar2QT.toolitems if t[0] in ("Home", "Back", "Forward", "Pan", "Zoom")]


class Grafica(QWidget):
    puntoClicado = Signal(int)  # fila de la tabla
    regionSeleccionada = Signal(list)  # filas de la tabla dentro del rectángulo
    rangoSeleccionado = Signal(float, float)
    personalizar = Signal()
    opcionesCambiadas = Signal()

    def __init__(self, tema: GestorTema, parent=None):
        super().__init__(parent)
        self.tema = tema
        self.escena = Escena()
        self.opciones = OpcionesGrafica()
        self.figura = Figure(layout="constrained")
        self.lienzo = FigureCanvasQTAgg(self.figura)
        self.lienzo.setMinimumSize(QSize(200, 160))
        self.barra = BarraNavegacion(self.lienzo, self)
        self.barra.setIconSize(QSize(20, 20))

        def boton(nombre, texto, ayuda, alternable=False):
            b = QToolButton()
            b.setIcon(icono(nombre))
            b.setText(texto)
            b.setToolTip(ayuda)
            b.setCheckable(alternable)
            b.setAutoRaise(True)
            b.setIconSize(QSize(20, 20))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            return b

        self.b_region = boton("region", "Región", "Arrastra un rectángulo para excluir (o volver a incluir) "
                                                 "todos los puntos de dentro", True)
        self.b_rango = boton("rango", "Rango", "Arrastra en horizontal para elegir el rango de x del ajuste", True)
        self.b_personalizar = boton("personalizar", "Personalizar", "Título, etiquetas, tamaño de letra, leyenda…")
        self.b_region.toggled.connect(lambda on: self._activar_herramienta("region" if on else None))
        self.b_rango.toggled.connect(lambda on: self._activar_herramienta("rango" if on else None))
        self.b_personalizar.clicked.connect(self.personalizar)

        self.ver_residuos = QCheckBox("Residuos")
        self.log_x = QCheckBox("log x")
        self.log_y = QCheckBox("log y")
        self.ver_residuos.setChecked(True)
        for cb, attr in ((self.ver_residuos, "residuos"), (self.log_x, "log_x"), (self.log_y, "log_y")):
            cb.toggled.connect(lambda v, a=attr: self._cambiar_opcion(a, v))

        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(self.barra)
        for b in (self.b_region, self.b_rango, self.b_personalizar):
            fila.addWidget(b)
        fila.addStretch(1)
        for cb in (self.ver_residuos, self.log_x, self.log_y):
            fila.addWidget(cb)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(fila)
        capa.addWidget(self.lienzo, 1)

        self._ax = None
        self._axr = None
        self._cuadro = None
        self._puntos_px = None
        self._anotacion = None
        self._herramienta: str | None = None
        self._selector = None
        self.lienzo.mpl_connect("button_press_event", self._al_pulsar)
        self.lienzo.mpl_connect("button_release_event", self._al_soltar)
        self.lienzo.mpl_connect("motion_notify_event", self._al_mover)
        # Tras cada dibujado (zoom, pan, cambio de tamaño) se recalculan las
        # posiciones en pantalla de los puntos para el clic.
        self.lienzo.mpl_connect("draw_event", lambda _: self._actualizar_puntos_px())
        tema.cambiado.connect(self.redibujar)
        self.redibujar()

    # -- API ----------------------------------------------------------------
    def mostrar(self, escena: Escena) -> None:
        self.escena = escena
        self.redibujar()

    def fijar_opciones(self, o: OpcionesGrafica) -> None:
        self.opciones = o
        for cb, v in ((self.ver_residuos, o.residuos), (self.log_x, o.log_x), (self.log_y, o.log_y)):
            cb.blockSignals(True)
            cb.setChecked(v)
            cb.blockSignals(False)
        self.redibujar()

    def _cambiar_opcion(self, atributo: str, valor) -> None:
        setattr(self.opciones, atributo, valor)
        self.opcionesCambiadas.emit()
        self.redibujar()

    # -- dibujo -------------------------------------------------------------
    def redibujar(self) -> None:
        self._anotacion = None
        self._puntos_px = None
        e = self.escena
        if e.datos is None and e.interseccion is None:
            self.figura.clear()
            self.figura.set_facecolor(self.tema.colores()["fondo"])
            self._ax = self._axr = self._cuadro = None
            self.lienzo.draw_idle()
            return
        self._ax, self._axr, self._cuadro = dibujar(self.figura, e, self.opciones, self.tema.colores(),
                                                    self.tema.oscuro)
        if self._cuadro is not None:
            self._cuadro.draggable(True)
        if self._herramienta:
            self._crear_selector()
        self.lienzo.draw_idle()

    # -- herramientas de selección -----------------------------------------
    def _activar_herramienta(self, nombre: str | None) -> None:
        otro = self.b_rango if nombre == "region" else self.b_region
        if nombre and otro.isChecked():
            otro.blockSignals(True)
            otro.setChecked(False)
            otro.blockSignals(False)
        if nombre and self.barra.mode:  # desactiva zoom/pan de matplotlib
            (self.barra.zoom if "zoom" in str(self.barra.mode) else self.barra.pan)()
        self._herramienta = nombre
        self._crear_selector()

    def _desactivar_herramientas(self) -> None:
        for b in (self.b_region, self.b_rango):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self._herramienta = None
        self._crear_selector()

    def _crear_selector(self) -> None:
        if self._selector is not None:
            self._selector.set_active(False)
            self._selector = None
        if self._herramienta is None or self._ax is None:
            return
        c = self.tema.colores()
        if self._herramienta == "region":
            self._selector = RectangleSelector(self._ax, self._al_seleccionar_region, useblit=True, button=[1],
                                               minspanx=3, minspany=3, spancoords="pixels", interactive=False,
                                               props=dict(facecolor=c["datos"], edgecolor=c["datos"], alpha=0.18,
                                                          fill=True))
        else:
            self._selector = SpanSelector(self._ax, self._al_seleccionar_rango, "horizontal", useblit=True,
                                          button=[1], minspan=0, interactive=False,
                                          props=dict(facecolor=c["datos"], alpha=0.18))

    def _al_seleccionar_region(self, ini, fin) -> None:
        d = self.escena.datos
        if d is None or self.escena.filas is None:
            return
        x0, x1 = sorted((ini.xdata, fin.xdata))
        y0, y1 = sorted((ini.ydata, fin.ydata))
        dentro = (d.x >= x0) & (d.x <= x1) & (d.y >= y0) & (d.y <= y1)
        filas = [int(f) for f in self.escena.filas[dentro]]
        self._desactivar_herramientas()
        if filas:
            self.regionSeleccionada.emit(filas)

    def _al_seleccionar_rango(self, lo, hi) -> None:
        self._desactivar_herramientas()
        if hi > lo:
            self.rangoSeleccionado.emit(float(lo), float(hi))

    # -- interacción --------------------------------------------------------
    def _actualizar_puntos_px(self):
        d = self.escena.datos
        if d is None or self.escena.interseccion is not None or self._ax is None:
            self._puntos_px = None
            return
        self._puntos_px = self._ax.transData.transform(np.column_stack([d.x, d.y]))

    def _punto_cercano(self, evento) -> int | None:
        if self._puntos_px is None or evento.x is None:
            return None
        dist = np.hypot(self._puntos_px[:, 0] - evento.x, self._puntos_px[:, 1] - evento.y)
        i = int(np.argmin(dist))
        return i if dist[i] <= _RADIO_CLIC_PX * self.lienzo.device_pixel_ratio else None

    def _sobre_cuadro(self, evento) -> bool:
        return self._cuadro is not None and self._cuadro.contains(evento)[0]

    def _al_pulsar(self, evento):
        if (evento.button != 1 or self.barra.mode or self._herramienta or evento.inaxes is not self._ax
                or self._sobre_cuadro(evento)):
            return
        i = self._punto_cercano(evento)
        if i is not None and self.escena.filas is not None:
            self.puntoClicado.emit(int(self.escena.filas[i]))

    def _al_soltar(self, evento):
        # Si se ha arrastrado el cuadro de resultados, se recuerda su posición
        if self._cuadro is not None and self._ax is not None:
            pos = tuple(float(v) for v in self._cuadro.xyann)
            if pos != tuple(self.opciones.pos_cuadro):
                self.opciones.pos_cuadro = pos
                self.opcionesCambiadas.emit()

    def _al_mover(self, evento):
        if self.barra.mode or self._herramienta or self._puntos_px is None:
            return
        i = self._punto_cercano(evento) if evento.inaxes is self._ax else None
        if i is None:
            if self._anotacion is not None:
                self._anotacion.remove()
                self._anotacion = None
                self.lienzo.draw_idle()
            return
        d = self.escena.datos
        fila = int(self.escena.filas[i]) + 1 if self.escena.filas is not None else i + 1
        texto = f"fila {fila}\n{d.nombre_x} = {d.x[i]:.6g}" + (f" ± {d.dx[i]:.2g}" if d.tiene_dx else "")
        texto += f"\n{d.nombre_y} = {d.y[i]:.6g}" + (f" ± {d.dy[i]:.2g}" if d.dy is not None else "")
        texto += "\n(clic: " + ("excluir" if d.incluidos[i] else "incluir") + ")"
        if self.escena.coma_decimal:
            texto = con_coma(texto)
        c = self.tema.colores()
        if self._anotacion is not None:
            self._anotacion.remove()
        # La etiqueta se abre hacia el centro de los ejes para no salirse
        fx, fy = self._ax.transAxes.inverted().transform((evento.x, evento.y))
        desplaz = (-12 if fx > 0.6 else 12, -12 if fy > 0.6 else 12)
        self._anotacion = self._ax.annotate(
            texto, (d.x[i], d.y[i]), xytext=desplaz, textcoords="offset points", fontsize=8, color=c["texto"],
            ha="right" if fx > 0.6 else "left", va="top" if fy > 0.6 else "bottom",
            bbox=dict(boxstyle="round,pad=0.4", fc=c["ejes"], ec=c["rejilla"], alpha=0.95), zorder=20)
        self.lienzo.draw_idle()
