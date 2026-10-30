"""Gráfica integrada (matplotlib en Qt): datos, ajuste, banda, residuos,
interpolación e intersección. Clic sobre un punto → se excluye/incluye.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

from ..ajuste import ResultadoAjuste
from ..datos import Datos
from ..interpolacion import METODOS, Interpolacion
from ..interseccion import Interseccion
from .tema import GestorTema

_RADIO_CLIC_PX = 9


@dataclass
class Escena:
    """Qué hay que dibujar. ``filas[i]`` es la fila de la tabla del punto i de ``datos``."""

    datos: Datos | None = None
    filas: np.ndarray | None = None
    ajuste: ResultadoAjuste | None = None
    nivel_banda: float | None = 0.6827
    interpolacion: Interpolacion | None = None
    interseccion: Interseccion | None = None


class Grafica(QWidget):
    puntoClicado = Signal(int)  # fila de la tabla

    def __init__(self, tema: GestorTema, parent=None):
        super().__init__(parent)
        self.tema = tema
        self.escena = Escena()
        self.figura = Figure(layout="constrained")
        self.lienzo = FigureCanvasQTAgg(self.figura)
        self.barra = NavigationToolbar2QT(self.lienzo, self)
        self.log_x = QCheckBox("log x")
        self.log_y = QCheckBox("log y")
        self.ver_residuos = QCheckBox("Residuos")
        self.ver_residuos.setChecked(True)
        for c in (self.log_x, self.log_y, self.ver_residuos):
            c.toggled.connect(self.redibujar)

        fila = QHBoxLayout()
        fila.addWidget(self.barra, 1)
        for c in (self.ver_residuos, self.log_x, self.log_y):
            fila.addWidget(c)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(fila)
        capa.addWidget(self.lienzo, 1)

        self._puntos_px = None  # (x, y) en coordenadas de pantalla para el clic
        self._anotacion = None
        self.lienzo.mpl_connect("button_press_event", self._al_pulsar)
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

    def guardar(self, ruta: str, dpi: int = 300) -> None:
        self.figura.savefig(ruta, dpi=dpi)

    # -- dibujo -------------------------------------------------------------
    def _estilo_ejes(self, ax, c):
        ax.set_facecolor(c["ejes"])
        ax.tick_params(colors=c["texto"], labelsize=9)
        for lado in ax.spines.values():
            lado.set_color(c["rejilla"])
        ax.grid(True, color=c["rejilla"], linewidth=0.6, alpha=0.7)
        ax.xaxis.label.set_color(c["texto"])
        ax.yaxis.label.set_color(c["texto"])

    def redibujar(self) -> None:
        c = self.tema.colores()
        e = self.escena
        fig = self.figura
        fig.clear()
        fig.set_facecolor(c["fondo"])
        self._anotacion = None
        self._puntos_px = None

        con_residuos = (self.ver_residuos.isChecked() and e.ajuste is not None and e.interseccion is None)
        if con_residuos:
            ax, axr = fig.subplots(2, 1, sharex=True, height_ratios=[3, 1])
        else:
            ax, axr = fig.subplots(1, 1), None
        self._ax = ax
        for a in (ax, axr):
            if a is not None:
                self._estilo_ejes(a, c)

        if e.interseccion is not None:
            self._dibujar_interseccion(ax, e.interseccion, c)
        elif e.datos is not None:
            self._dibujar_datos(ax, e.datos, c)
            if e.ajuste is not None:
                self._dibujar_ajuste(ax, e.ajuste, e.nivel_banda, c)
                if axr is not None:
                    self._dibujar_residuos(axr, e.ajuste, c)
            if e.interpolacion is not None:
                self._dibujar_interpolacion(ax, e.interpolacion, c)
        else:
            ax.text(0.5, 0.5, "Abre un fichero, arrástralo aquí o pega datos (Ctrl+Mayús+V)",
                    ha="center", va="center", color=c["secundario"], transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])

        self._aplicar_escalas(ax)
        if axr is not None and self.log_x.isChecked() and ax.get_xscale() == "log":
            axr.set_xscale("log")
        handles, labels = ax.get_legend_handles_labels()
        if len(handles) >= 2:
            ley = ax.legend(fontsize=9, framealpha=0.85, facecolor=c["ejes"], edgecolor=c["rejilla"])
            for t in ley.get_texts():
                t.set_color(c["texto"])
        self.lienzo.draw_idle()

    def _aplicar_escalas(self, ax):
        e = self.escena
        xs = ys = None
        if e.datos is not None:
            xs, ys = e.datos.x, e.datos.y
        if self.log_x.isChecked() and (xs is None or np.all(xs > 0)):
            ax.set_xscale("log")
        if self.log_y.isChecked() and (ys is None or np.all(ys > 0)):
            ax.set_yscale("log")

    def _dibujar_datos(self, ax, d: Datos, c, color=None, etiqueta="Datos"):
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
                        label="Excluidos", zorder=2)
        ax.set_xlabel(d.nombre_x)
        ax.set_ylabel(d.nombre_y)

    def _malla_x(self, x: np.ndarray, modelo=None, n: int = 600) -> np.ndarray:
        lo, hi = float(np.min(x)), float(np.max(x))
        if self.log_x.isChecked() and lo > 0:
            return np.geomspace(lo, hi, n)
        margen = 0.02 * (hi - lo)
        malla = np.linspace(lo - margen, hi + margen, n)
        if modelo is not None and not modelo.dominio_valido(malla):
            malla = np.linspace(lo, hi, n)
        return malla

    def _dibujar_ajuste(self, ax, r: ResultadoAjuste, nivel, c, color=None, etiqueta=None):
        color = color or c["ajuste"]
        xx = self._malla_x(r.datos.x, r.modelo)
        if nivel:
            f, lo, hi = r.banda(xx, nivel=nivel)
            ax.fill_between(xx, lo, hi, color=color, alpha=0.32 if self.tema.oscuro else 0.22, linewidth=0,
                            label=f"Banda {nivel * 100:.0f} %" if etiqueta is None else None, zorder=1)
        else:
            f = r.evaluar(xx)
        ax.plot(xx, f, color=color, linewidth=2, label=etiqueta or f"Ajuste: {r.modelo.nombre}", zorder=4)

    def _dibujar_residuos(self, axr, r: ResultadoAjuste, c):
        rn = r.residuos_norm
        axr.axhline(0, color=c["texto"], linewidth=0.8)
        for k in (-2, 2):
            axr.axhline(k, color=c["rejilla"], linewidth=0.8, linestyle="--")
        axr.plot(r.datos.x, rn, "o", ms=4, color=c["datos"])
        axr.set_ylabel("(y − f)/σ" if r.errores_absolutos else "(y − f)/s", fontsize=9)
        lim = max(3.0, float(np.nanmax(np.abs(rn))) * 1.15) if np.any(np.isfinite(rn)) else 3.0
        axr.set_ylim(-lim, lim)
        axr.set_xlabel(r.datos.nombre_x)
        self._ax.set_xlabel("")

    def _dibujar_interpolacion(self, ax, f: Interpolacion, c):
        lo, hi = f.rango
        xx = np.geomspace(lo, hi, 800) if (self.log_x.isChecked() and lo > 0) else np.linspace(lo, hi, 800)
        ax.plot(xx, f(xx), color=c["interpolacion"], linewidth=2, label=METODOS[f.metodo], zorder=4)

    def _dibujar_interseccion(self, ax, I: Interseccion, c):
        for r, color, n in ((I.ajuste1, c["datos"], 1), (I.ajuste2, c["ajuste"], 2)):
            d = r.datos
            ax.errorbar(d.x, d.y, xerr=d.dx if d.tiene_dx else None, yerr=d.dy, fmt="o", ms=5, color=color,
                        ecolor=color, elinewidth=1, capsize=2, label=f"Conjunto {n}", zorder=3)
            lo = min(np.min(d.x), I.x)
            hi = max(np.max(d.x), I.x)
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

    # -- interacción --------------------------------------------------------
    def _actualizar_puntos_px(self):
        d = self.escena.datos
        if d is None or self.escena.interseccion is not None:
            self._puntos_px = None
            return
        self._puntos_px = self._ax.transData.transform(np.column_stack([d.x, d.y]))

    def _punto_cercano(self, evento) -> int | None:
        if self._puntos_px is None or evento.x is None:
            return None
        dist = np.hypot(self._puntos_px[:, 0] - evento.x, self._puntos_px[:, 1] - evento.y)
        i = int(np.argmin(dist))
        return i if dist[i] <= _RADIO_CLIC_PX * self.lienzo.device_pixel_ratio else None

    def _al_pulsar(self, evento):
        if evento.button != 1 or self.barra.mode or evento.inaxes is not self._ax:
            return
        i = self._punto_cercano(evento)
        if i is not None and self.escena.filas is not None:
            self.puntoClicado.emit(int(self.escena.filas[i]))

    def _al_mover(self, evento):
        if self.barra.mode or self._puntos_px is None:
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
        c = self.tema.colores()
        if self._anotacion is not None:
            self._anotacion.remove()
        self._anotacion = self._ax.annotate(
            texto, (d.x[i], d.y[i]), xytext=(12, 12), textcoords="offset points", fontsize=8, color=c["texto"],
            bbox=dict(boxstyle="round,pad=0.4", fc=c["ejes"], ec=c["rejilla"], alpha=0.95), zorder=10)
        self.lienzo.draw_idle()
