"""Widget de la gráfica en la ventana: matplotlib en Qt e interacción.

* Herramientas: clic en un punto → excluir/incluir; **Región** (rectángulo que
  excluye o incluye), **Rango** (rango de x del ajuste), **Cortar** (eje x partido),
  **Marcar** (punto, tramo, línea vertical u horizontal), zoom y desplazamiento.
* Arrastrar el título, la leyenda, las etiquetas de los ejes, los textos libres y
  el cuadro de resultados; doble clic para editarlos; clic derecho para añadir
  textos, flechas y marcas.
* Etiqueta al pasar el ratón por un punto (o una barra, un sector, una caja…).

El dibujo en sí está en :mod:`ajustelab.gui.grafica` (:func:`dibujar`).
"""
from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.transforms import IdentityTransform
from matplotlib.widgets import RectangleSelector, SpanSelector
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QInputDialog, QMenu, QToolButton, QVBoxLayout,
                               QWidget)

from .grafica import (_RADIO_CLIC_PX, COLOR_MARCA, Escena, OpcionesGrafica, SerieDibujo, con_coma, dibujar,
                      fuera_de_cortes)
from .iconos import icono
from .tema import GestorTema


class BarraNavegacion(NavigationToolbar2QT):
    """Barra de matplotlib reducida a inicio/atrás/adelante/desplazar/zoom
    (guardar y personalizar tienen sus propios diálogos en ajustelab)."""

    toolitems = [t for t in NavigationToolbar2QT.toolitems if t[0] in ("Home", "Back", "Forward", "Pan", "Zoom")]


class Grafica(QWidget):
    puntoClicado = Signal(int)  # fila de la tabla
    regionSeleccionada = Signal(list)  # filas de la tabla dentro del rectángulo
    rangoSeleccionado = Signal(float, float)
    corteSeleccionado = Signal(float, float)  # tramo de x que se quita (eje partido)
    personalizar = Signal()
    personalizarEn = Signal(str)  # abre «Personalizar» en una pestaña concreta
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
        self.b_cortar = boton("cortar", "Cortar", "Arrastra en horizontal sobre un tramo de x para quitarlo: "
                                                  "el eje se parte (//) y la gráfica se acorta", True)
        self.b_cortar.setVisible(False)  # solo en «Representar» (puntos x-y)
        self.b_personalizar = boton("personalizar", "Personalizar",
                                    "Título, ejes, leyenda, tamaños, colores, textos y plantillas de estilo.\n"
                                    "En la gráfica: arrastra el título, la leyenda, las etiquetas o los textos;\n"
                                    "doble clic para editarlos; clic derecho para añadir textos y flechas.")
        self._botones_herramienta = {"region": self.b_region, "rango": self.b_rango, "cortar": self.b_cortar}
        self.b_marcar = QToolButton()
        self.b_marcar.setIcon(icono("marcar"))
        self.b_marcar.setText("Marcar")
        self.b_marcar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_marcar.setAutoRaise(True)
        self.b_marcar.setPopupMode(QToolButton.InstantPopup)
        self.b_marcar.setToolTip("Señala un punto, un tramo de x o un valor con una marca personalizable")
        menu_marcar = QMenu(self)
        menu_marcar.addAction("Un punto: haz clic en él", lambda: self._activar_herramienta("marca_punto"))
        menu_marcar.addAction("Un tramo de x: arrastra en horizontal", lambda: self._activar_herramienta("marca_tramo"))
        menu_marcar.addAction("Una línea vertical: haz clic", lambda: self._activar_herramienta("marca_vertical"))
        menu_marcar.addAction("Una línea horizontal: haz clic",
                              lambda: self._activar_herramienta("marca_horizontal"))
        menu_marcar.addSeparator()
        menu_marcar.addAction("Editar las marcas…", lambda: self.personalizarEn.emit("marcas"))
        self.b_marcar.setMenu(menu_marcar)
        for nombre, b in self._botones_herramienta.items():
            b.toggled.connect(lambda on, n=nombre: self._activar_herramienta(n if on else None))
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
        for b in (self.b_region, self.b_rango, self.b_cortar, self.b_marcar, self.b_personalizar):
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
        self._puntos_serie = None
        self._anotacion = None
        self._herramienta: str | None = None
        self._selector = None
        self._selectores: list = []
        self._objetivos: list = []  # para la etiqueta al pasar el ratón en los otros tipos
        self._arrastre: dict | None = None  # elemento que se está moviendo con el ratón
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
        # Región, Rango y Residuos solo tienen sentido con un ajuste; Cortar, con
        # series x-y de «Representar»
        sin_ajuste = bool(escena.series) or escena.especial is not None
        modo_xy = bool(escena.series)
        h = self._herramienta
        if (h in ("region", "rango") and sin_ajuste) or (h == "cortar" and not modo_xy):
            self._desactivar_herramientas()
        for w in (self.b_region, self.b_rango, self.ver_residuos):
            w.setEnabled(not sin_ajuste)
        self.b_cortar.setVisible(modo_xy)
        log_x = getattr(escena.especial, "permite_log_x", escena.especial is None)
        log_y = getattr(escena.especial, "permite_log_y", escena.especial is None)
        self.log_x.setEnabled(log_x)
        self.log_y.setEnabled(log_y)
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
        self._objetivos = []
        self._arrastre = None
        e = self.escena
        if e.vacia:
            self.figura.clear()
            self.figura.set_facecolor(self.tema.colores()["fondo"])
            self._ax = self._axr = self._cuadro = None
            self.lienzo.draw_idle()
            return
        self._ax, self._axr, self._cuadro = dibujar(self.figura, e, self.opciones, self.tema.colores(),
                                                    self.tema.oscuro)
        self._objetivos = list(getattr(self.figura, "_ajustelab", {}).get("objetivos", []))
        if self._cuadro is not None:
            self._cuadro.draggable(True)
        if self._herramienta:
            self._crear_selector()
        self.lienzo.draw_idle()

    # -- herramientas de selección -----------------------------------------
    def _activar_herramienta(self, nombre: str | None) -> None:
        for otro_nombre, otro in self._botones_herramienta.items():
            if nombre and otro_nombre != nombre and otro.isChecked():
                otro.blockSignals(True)
                otro.setChecked(False)
                otro.blockSignals(False)
        if nombre and self.barra.mode:  # desactiva zoom/pan de matplotlib
            (self.barra.zoom if "zoom" in str(self.barra.mode) else self.barra.pan)()
        self._herramienta = nombre
        self._crear_selector()

    def _desactivar_herramientas(self) -> None:
        for b in self._botones_herramienta.values():
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        if self._herramienta and self._herramienta.startswith("marca_"):
            self.lienzo.unsetCursor()
        self._herramienta = None
        self._crear_selector()

    def _crear_selector(self) -> None:
        if self._selector is not None:
            self._selector.set_active(False)
            self._selector = None
        for sel in self._selectores:
            sel.set_active(False)
        self._selectores = []
        if self._herramienta is None or self._ax is None:
            return
        c = self.tema.colores()
        if self._herramienta == "cortar":  # un selector por tramo (y por panel)
            ejes = getattr(self.figura, "_ajustelab", {}).get("ejes", {})
            for ax in [*ejes.get("izq", []), *(ejes.get("der", []) if self.escena.apilados else [])]:
                self._selectores.append(SpanSelector(
                    ax, self._al_seleccionar_corte, "horizontal", useblit=True, button=[1], minspan=0,
                    interactive=False, props=dict(facecolor=c["secundario"], alpha=0.22)))
            self._selector = self._selectores[0] if self._selectores else None
            return
        if self._herramienta in ("marca_punto", "marca_vertical", "marca_horizontal"):
            self.lienzo.setCursor(Qt.CrossCursor)  # el siguiente clic pone la marca
            return
        if self._herramienta == "marca_tramo":
            ejes = getattr(self.figura, "_ajustelab", {}).get("ejes", {})
            for ax in (ejes.get("izq") or [self._ax]):
                self._selectores.append(SpanSelector(
                    ax, self._al_seleccionar_tramo_marcado, "horizontal", useblit=True, button=[1], minspan=0,
                    interactive=False, props=dict(facecolor=COLOR_MARCA[self.tema.oscuro], alpha=0.2)))
            self._selector = self._selectores[0]
            return
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

    def _al_seleccionar_corte(self, lo, hi) -> None:
        self._desactivar_herramientas()
        if hi > lo:
            self.corteSeleccionado.emit(float(lo), float(hi))

    # -- interacción --------------------------------------------------------
    def _ejes_de(self, serie: SerieDibujo, x: float | None = None):
        """Ejes en los que está dibujado el punto de abscisa ``x`` de la serie (con el
        eje partido, el del tramo correspondiente; None si x cae en un corte)."""
        info = getattr(self.figura, "_ajustelab", {})
        ejes = info.get("ejes")
        if not ejes:
            return self._axr if (serie.eje == "der" and self._axr is not None) else self._ax
        lista = ejes["der"] if (serie.eje == "der" and ejes.get("der")) else ejes["izq"]
        limites = info.get("limites") or []
        if x is None or len(lista) == 1 or not limites:
            if x is not None and info.get("cortes") and not fuera_de_cortes(np.array([x]), info["cortes"])[0]:
                return None
            return lista[0]
        for ax, (lo, hi) in zip(lista, limites):
            if lo <= x <= hi:
                return ax
        return None

    def _actualizar_puntos_px(self):
        e = self.escena
        self._puntos_serie = None
        if self._ax is None:
            self._puntos_px = None
            return
        if e.series:
            # Todos los puntos de todas las series, cada uno con su eje; se recuerda
            # de qué serie y qué punto es cada uno.
            info = getattr(self.figura, "_ajustelab", {})
            ejes, limites, cortes = info.get("ejes"), info.get("limites") or [], info.get("cortes") or []
            trozos, indices = [], []
            for k, serie in enumerate(e.series):  # vectorizado: miles de puntos sin bucles en Python
                px = np.full((serie.x.size, 2), np.nan)
                xy = np.column_stack([serie.x, serie.y])
                if not ejes:
                    px[:] = self._ejes_de(serie).transData.transform(xy)
                else:
                    lista = ejes["der"] if (serie.eje == "der" and ejes.get("der")) else ejes["izq"]
                    if len(lista) == 1 or not limites:
                        vis = fuera_de_cortes(serie.x, cortes) if cortes else np.ones(serie.x.size, bool)
                        px[vis] = lista[0].transData.transform(xy[vis])
                    else:
                        for ax, (lo, hi) in zip(lista, limites):
                            m = (serie.x >= lo) & (serie.x <= hi) & np.isnan(px[:, 0])
                            px[m] = ax.transData.transform(xy[m])
                trozos.append(px)
                indices.append(np.column_stack([np.full(serie.x.size, k), np.arange(serie.x.size)]))
            self._puntos_px = np.vstack(trozos) if trozos else None
            self._puntos_serie = np.vstack(indices) if indices else None
            return
        d = e.datos
        if d is None or e.interseccion is not None:
            self._puntos_px = None
            return
        self._puntos_px = self._ax.transData.transform(np.column_stack([d.x, d.y]))

    def _punto_cercano(self, evento) -> int | None:
        if self._puntos_px is None or evento.x is None or not len(self._puntos_px):
            return None
        dist = np.hypot(self._puntos_px[:, 0] - evento.x, self._puntos_px[:, 1] - evento.y)
        dist[~np.isfinite(dist)] = np.inf
        i = int(np.argmin(dist))
        return i if dist[i] <= _RADIO_CLIC_PX * self.lienzo.device_pixel_ratio else None

    def _dentro(self, evento) -> bool:
        return evento.inaxes is not None and evento.inaxes in self.figura.axes

    def _fila_de(self, i: int) -> int | None:
        """Fila de la tabla del punto i (de la lista de puntos en pantalla)."""
        if self._puntos_serie is not None:
            k, j = self._puntos_serie[i]
            filas = self.escena.series[k].filas
            return None if filas is None else int(filas[j])
        return None if self.escena.filas is None else int(self.escena.filas[i])

    def _sobre_cuadro(self, evento) -> bool:
        return self._cuadro is not None and self._cuadro.contains(evento)[0]

    def _al_pulsar(self, evento):
        if self._herramienta in ("marca_punto", "marca_vertical", "marca_horizontal"):
            if evento.button == 1 and evento.inaxes is not None:
                tipo = self._herramienta[6:]
                self._desactivar_herramientas()
                self.lienzo.unsetCursor()
                self.nueva_marca(tipo, evento)
            return
        if self.barra.mode or self._herramienta:
            return
        if evento.button == 3 and not self.escena.vacia:
            self._menu_contextual(evento).exec(QCursor.pos())
            return
        if evento.button != 1:
            return
        if evento.dblclick:
            i = self._marca_en(evento)
            if i is not None:
                self.editar_marca(i)
                return
        el = self._elemento_en(evento)
        if el is not None:  # título, leyenda, etiqueta o texto: se arrastra (doble clic: se edita)
            if evento.dblclick:
                self.editar_elemento(el)
            else:
                self._arrastre = {"el": el, "inicio": np.array([evento.x, evento.y], float),
                                  "px0": self._pixel_de(el), "movido": False}
            return
        if not self._dentro(evento) or self._sobre_cuadro(evento):
            return
        i = self._punto_cercano(evento)
        fila = None if i is None else self._fila_de(i)
        if fila is not None:
            self.puntoClicado.emit(fila)

    def _al_soltar(self, evento):
        if self._arrastre is not None:
            arrastre, self._arrastre = self._arrastre, None
            if arrastre["movido"]:
                self._guardar_posicion(arrastre["el"])
                self.opcionesCambiadas.emit()
                self.redibujar()
            return
        # Si se ha arrastrado el cuadro de resultados, se recuerda su posición
        if self._cuadro is not None and self._ax is not None:
            pos = tuple(float(v) for v in self._cuadro.xyann)
            if pos != tuple(self.opciones.pos_cuadro):
                self.opciones.pos_cuadro = pos
                self.opcionesCambiadas.emit()

    def _texto_punto(self, i: int):
        """(texto de la etiqueta, ejes, x, y) del punto i."""
        if self._puntos_serie is not None:
            k, j = (int(v) for v in self._puntos_serie[i])
            s = self.escena.series[k]
            fila = int(s.filas[j]) + 1 if s.filas is not None else j + 1
            texto = f"fila {fila}\n{self.escena.nombre_x} = {s.x[j]:.6g}"
            if s.dx is not None and self.escena.barras_error:
                texto += f" ± {s.dx[j]:.2g}"
            texto += f"\n{s.nombre} = {s.y[j]:.6g}"
            if s.dy is not None and self.escena.barras_error:
                texto += f" ± {s.dy[j]:.2g}"
            incluido = True if s.incluidos is None else bool(s.incluidos[j])
            texto += "\n(clic: " + ("excluir la fila" if incluido else "incluir la fila") + ")"
            return texto, self._ejes_de(s, float(s.x[j])) or self._ax, s.x[j], s.y[j]
        d = self.escena.datos
        fila = int(self.escena.filas[i]) + 1 if self.escena.filas is not None else i + 1
        texto = f"fila {fila}\n{d.nombre_x} = {d.x[i]:.6g}" + (f" ± {d.dx[i]:.2g}" if d.tiene_dx else "")
        texto += f"\n{d.nombre_y} = {d.y[i]:.6g}" + (f" ± {d.dy[i]:.2g}" if d.dy is not None else "")
        texto += "\n(clic: " + ("excluir" if d.incluidos[i] else "incluir") + ")"
        return texto, self._ax, d.x[i], d.y[i]

    def _al_mover(self, evento):
        if self._arrastre is not None:
            a = self._arrastre
            delta = np.array([evento.x, evento.y], float) - a["inicio"]
            if np.abs(delta).sum() > 2:
                a["movido"] = True
            if a["movido"]:
                self._mover_a(a["el"], a["px0"] + delta)
                self.lienzo.draw_idle()
            return
        if not (self.barra.mode or self._herramienta):
            if self._elemento_en(evento) is not None:
                self.lienzo.setCursor(Qt.SizeAllCursor)
            else:
                self.lienzo.unsetCursor()
        if self._objetivos and not (self.barra.mode or self._herramienta):
            self._etiqueta_especial(evento)
            return
        if self.barra.mode or self._herramienta or self._puntos_px is None:
            return
        i = self._punto_cercano(evento) if self._dentro(evento) else None
        if i is None:
            if self._anotacion is not None:
                self._anotacion.remove()
                self._anotacion = None
                self.lienzo.draw_idle()
            return
        texto, ejes, xp, yp = self._texto_punto(i)
        if self.escena.coma_decimal:
            texto = con_coma(texto)
        c = self.tema.colores()
        if self._anotacion is not None:
            self._anotacion.remove()
        # La etiqueta se abre hacia el centro de los ejes para no salirse
        fx, fy = ejes.transAxes.inverted().transform((evento.x, evento.y))
        desplaz = (-12 if fx > 0.6 else 12, -12 if fy > 0.6 else 12)
        self._anotacion = ejes.annotate(
            texto, (xp, yp), xytext=desplaz, textcoords="offset points", fontsize=8, color=c["texto"],
            ha="right" if fx > 0.6 else "left", va="top" if fy > 0.6 else "bottom",
            bbox=dict(boxstyle="round,pad=0.4", fc=c["ejes"], ec=c["rejilla"], alpha=0.95), zorder=20)
        self.lienzo.draw_idle()

    def _etiqueta_especial(self, evento) -> None:
        """Etiqueta al pasar el ratón por una barra, un sector, una caja… Cada objetivo
        es una función evento → texto (o None si el ratón no está encima)."""
        texto = None
        if evento.inaxes is not None:
            for objetivo in self._objetivos:
                texto = objetivo(evento)
                if texto:
                    break
        if texto is None and self._anotacion is None:
            return
        if self._anotacion is not None:
            self._anotacion.remove()
            self._anotacion = None
        if texto:
            if self.escena.coma_decimal:
                texto = con_coma(texto)
            c = self.tema.colores()
            ancho, alto = self.lienzo.get_width_height(physical=True)
            derecha, arriba = evento.x > 0.6 * ancho, evento.y > 0.6 * alto
            self._anotacion = self.figura.text(
                evento.x + (-14 if derecha else 14), evento.y + (-14 if arriba else 14), texto,
                transform=IdentityTransform(), fontsize=8, color=c["texto"], ha="right" if derecha else "left",
                va="top" if arriba else "bottom", zorder=50,
                bbox=dict(boxstyle="round,pad=0.4", fc=c["ejes"], ec=c["rejilla"], alpha=0.95))
        self.lienzo.draw_idle()

    # -- elementos que se mueven y se editan sobre la gráfica ------------------------
    def _movibles(self) -> list[dict]:
        return list(getattr(self.figura, "_ajustelab", {}).get("movibles", []))

    def _elemento_en(self, evento) -> dict | None:
        """Título, leyenda, etiqueta de eje o texto libre bajo el ratón (los textos y la
        leyenda primero, que están encima)."""
        orden = {"nota": 0, "leyenda": 1, "titulo": 2}
        for el in sorted(self._movibles(), key=lambda e: orden.get(e["clave"].split(":")[0], 3)):
            art = el["artista"]
            try:
                if art.get_visible() and (el["clave"] == "leyenda" or art.get_text()) and art.contains(evento)[0]:
                    return el
            except (AttributeError, TypeError, ValueError, RuntimeError):
                continue
        return None

    def _pixel_de(self, el: dict) -> np.ndarray:
        art = el["artista"]
        if el["clave"] == "leyenda":
            b = art.get_window_extent()
            return np.array([b.x0, b.y0], float)
        if el["clave"].startswith("nota:"):
            return np.asarray(self.figura.transFigure.transform(art.get_position()), float)
        return np.asarray(art.get_transform().transform(art.get_position()), float)

    def _mover_a(self, el: dict, px) -> None:
        clave, art, ax = el["clave"], el["artista"], el.get("ax")
        if clave == "leyenda":
            ref = ax.transAxes if ax is not None else self.figura.transFigure
            x, y = ref.inverted().transform(px)
            art.set_bbox_to_anchor(None)
            if hasattr(art, "_outside_loc"):  # ya no va «fuera»: el ajuste de la figura no la recoloca
                art._outside_loc = None
            art.set_loc((float(x), float(y)))
        elif clave.startswith("nota:"):
            art.set_position(tuple(self.figura.transFigure.inverted().transform(px)))
        elif el.get("eje") is not None:  # etiqueta de un eje
            el["eje"].set_label_coords(*ax.transAxes.inverted().transform(px))
        else:  # título (de unos ejes o de la figura) o etiqueta común
            art.set_position(tuple(art.get_transform().inverted().transform(px)))
            if clave == "titulo" and ax is not None:
                ax._autotitlepos = False
            if hasattr(art, "_autopos"):
                art._autopos = False

    def _guardar_posicion(self, el: dict) -> None:
        o = self.opciones
        clave, art, ax = el["clave"], el["artista"], el.get("ax")
        if clave == "leyenda":
            ref = ax.transAxes if ax is not None else self.figura.transFigure
            b = art.get_window_extent()
            x, y = ref.inverted().transform((b.x0, b.y0))
            o.pos_leyenda = (float(x), float(y), "ejes" if ax is not None else "figura")
        elif clave.startswith("nota:"):
            i = int(clave[5:])
            if i < len(o.anotaciones):
                x, y = art.get_position()
                o.anotaciones[i] = {**o.anotaciones[i], "x": float(x), "y": float(y)}
        elif el.get("eje") is not None:
            x, y = ax.transAxes.inverted().transform(self._pixel_de(el))
            setattr(o, "pos_" + clave, (float(x), float(y), "ejes"))
        else:
            x, y = art.get_position()
            setattr(o, "pos_" + clave, (float(x), float(y), "ejes" if ax is not None else "figura"))

    def editar_elemento(self, el: dict) -> None:
        """Doble clic: el título y las etiquetas se editan aquí mismo; la leyenda abre su
        pestaña de «Personalizar»; un texto libre, su texto."""
        clave = el["clave"]
        if clave == "leyenda":
            self.personalizarEn.emit("leyenda")
            return
        if clave.startswith("nota:"):
            self.editar_nota(int(clave[5:]))
            return
        atributo = clave  # «titulo», «etiqueta_x», «etiqueta_y» o «etiqueta_y2»
        nombres = {"titulo": "Título de la gráfica", "etiqueta_x": "Etiqueta del eje x",
                   "etiqueta_y": "Etiqueta del eje y", "etiqueta_y2": "Etiqueta del eje y derecho"}
        actual = getattr(self.opciones, atributo) or el["artista"].get_text()
        texto, ok = QInputDialog.getText(self, nombres.get(clave, "Texto"),
                                         nombres.get(clave, "Texto") + " (admite LaTeX entre $…$; vacío: automático):",
                                         text=actual)
        if ok:
            setattr(self.opciones, atributo, texto.strip())
            self.opcionesCambiadas.emit()
            self.redibujar()

    def _menu_contextual(self, evento) -> QMenu:
        menu = QMenu(self)
        el = self._elemento_en(evento)
        fx, fy = (float(v) for v in self.figura.transFigure.inverted().transform((evento.x, evento.y)))
        if el is not None and el["clave"].startswith("nota:"):
            i = int(el["clave"][5:])
            menu.addAction("Editar el texto…", lambda: self.editar_nota(i))
            menu.addAction(icono("quitar"), "Quitar el texto", lambda: self.quitar_nota(i))
            menu.addSeparator()
        elif el is not None:
            menu.addAction("Editar…", lambda: self.editar_elemento(el))
            menu.addAction("Devolver a su sitio", lambda: self._restablecer_posicion(el["clave"]))
            menu.addSeparator()
        i_marca = self._marca_en(evento)
        if i_marca is not None:
            menu.addAction("Editar la marca…", lambda: self.editar_marca(i_marca))
            menu.addAction(icono("quitar"), "Quitar la marca", lambda: self.quitar_marca(i_marca))
            menu.addSeparator()
        if evento.inaxes is not None:
            menu.addAction(icono("marcar"), "Marcar este punto…", lambda: self.nueva_marca("punto", evento))
            menu.addAction("Línea vertical aquí…", lambda: self.nueva_marca("vertical", evento))
            menu.addAction("Línea horizontal aquí…", lambda: self.nueva_marca("horizontal", evento))
            menu.addSeparator()
        menu.addAction("Añadir un texto aquí…", lambda: self.anadir_nota(fx, fy))
        if self._ax is not None and evento.inaxes is not None:
            xd, yd = (float(v) for v in self._ax.transData.inverted().transform((evento.x, evento.y)))
            menu.addAction("Añadir una flecha que señale aquí…",
                           lambda: self.anadir_nota(min(fx + 0.15, 0.92), min(fy + 0.15, 0.92), flecha=(xd, yd)))
        menu.addSeparator()
        menu.addAction("Restablecer las posiciones", self.restablecer_posiciones)
        menu.addAction(icono("personalizar"), "Personalizar…", self.personalizar.emit)
        return menu

    def anadir_nota(self, x: float, y: float, flecha=None, texto: str | None = None) -> bool:
        if texto is None:
            texto, ok = QInputDialog.getText(self, "Añadir texto", "Texto (admite LaTeX entre $…$):")
            if not ok:
                return False
        texto = texto.strip()
        if not texto:
            return False
        self.opciones.anotaciones.append({"texto": texto, "x": float(x), "y": float(y),
                                          "flecha": None if flecha is None else [float(v) for v in flecha],
                                          "tam": 0})
        self.opcionesCambiadas.emit()
        self.redibujar()
        return True

    def editar_nota(self, i: int) -> None:
        notas = self.opciones.anotaciones
        if not 0 <= i < len(notas):
            return
        texto, ok = QInputDialog.getText(self, "Editar texto", "Texto (vacío: se quita):", text=notas[i]["texto"])
        if not ok:
            return
        if texto.strip():
            notas[i] = {**notas[i], "texto": texto.strip()}
            self.opcionesCambiadas.emit()
            self.redibujar()
        else:
            self.quitar_nota(i)

    def quitar_nota(self, i: int) -> None:
        if 0 <= i < len(self.opciones.anotaciones):
            self.opciones.anotaciones.pop(i)
            self.opcionesCambiadas.emit()
            self.redibujar()

    def _restablecer_posicion(self, clave: str) -> None:
        if hasattr(self.opciones, "pos_" + clave):
            setattr(self.opciones, "pos_" + clave, None)
            self.opcionesCambiadas.emit()
            self.redibujar()

    def restablecer_posiciones(self) -> None:
        self.opciones.restablecer_posiciones()
        self.opcionesCambiadas.emit()
        self.redibujar()

    # -- marcas (puntos, tramos y líneas señalados) -------------------------------------
    def _marca_en(self, evento) -> int | None:
        for i, art in getattr(self.figura, "_ajustelab", {}).get("destacados", []):
            try:
                if art.contains(evento)[0]:
                    return i
            except (AttributeError, TypeError, ValueError, RuntimeError):
                continue
        return None

    def _coordenadas_marca(self, tipo: str, evento) -> dict:
        """Dónde va una marca nueva. Un punto se pega al dato más cercano (si el clic cae
        sobre uno); si no, va donde se ha hecho clic."""
        ax = evento.inaxes
        ejes = getattr(self.figura, "_ajustelab", {}).get("ejes", {})
        eje = "der" if ax in (ejes.get("der") or []) and not self.escena.apilados else "izq"
        x, y = (float(v) for v in ax.transData.inverted().transform((evento.x, evento.y)))
        if tipo == "punto":
            i = self._punto_cercano(evento)
            if i is not None:
                if self._puntos_serie is not None:
                    k, j = self._puntos_serie[i]
                    s = self.escena.series[int(k)]
                    x, y, eje = float(s.x[j]), float(s.y[j]), s.eje
                elif self.escena.datos is not None:
                    x, y = float(self.escena.datos.x[i]), float(self.escena.datos.y[i])
        return {"tipo": tipo, "x": x, "y": y, "x2": x, "eje": eje}

    def nueva_marca(self, tipo: str, evento=None, marca: dict | None = None) -> bool:
        """Crea una marca (en el sitio del clic) y abre su diálogo para darle texto,
        color, forma…; si se cancela, no se añade."""
        from .personalizar import DialogoMarca

        m = marca or self._coordenadas_marca(tipo, evento)
        doble = bool(getattr(self.figura, "_ajustelab", {}).get("ejes", {}).get("der"))
        dlg = DialogoMarca(m, self, "Marca nueva", doble_eje=doble)
        if dlg.exec() != QDialog.Accepted:
            return False
        self.opciones.destacados.append(dlg.marca())
        self.opcionesCambiadas.emit()
        self.redibujar()
        return True

    def _al_seleccionar_tramo_marcado(self, lo, hi) -> None:
        self._desactivar_herramientas()
        if hi > lo:
            self.nueva_marca("tramo", marca={"tipo": "tramo", "x": float(lo), "x2": float(hi), "y": None})

    def editar_marca(self, i: int) -> None:
        from .personalizar import DialogoMarca

        if not 0 <= i < len(self.opciones.destacados):
            return
        doble = bool(getattr(self.figura, "_ajustelab", {}).get("ejes", {}).get("der"))
        dlg = DialogoMarca(self.opciones.destacados[i], self, "Editar marca", doble_eje=doble)
        if dlg.exec() == QDialog.Accepted:
            self.opciones.destacados[i] = dlg.marca()
            self.opcionesCambiadas.emit()
            self.redibujar()

    def quitar_marca(self, i: int) -> None:
        if 0 <= i < len(self.opciones.destacados):
            self.opciones.destacados.pop(i)
            self.opcionesCambiadas.emit()
            self.redibujar()
