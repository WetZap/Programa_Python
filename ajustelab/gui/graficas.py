"""Otros tipos de gráfica de «Representar»: histograma, barras, sectores, cajas o
violín y polar.

Cada tipo es un objeto con ``dibujar(fig, opciones, colores, oscuro) -> ejes`` (sin
Qt: la exportación usa exactamente el mismo código) y ``tablas()``, los números
dibujados como tablas (para exportarlos en CSV). Al dibujarse deja en
``fig._ajustelab["objetivos"]`` funciones evento → texto, que la gráfica usa para
la etiqueta que sale al pasar el ratón por una barra, un sector o una caja.

Criterios de diseño
-------------------
* Un color por serie, no por categoría: en barras con una sola serie todas las
  barras son del mismo color (el color no codifica nada más).
* Los textos van en el color del texto, nunca en el de la serie.
* Sectores: ordenados de mayor a menor desde las 12 en sentido horario, los
  menores de un umbral se agrupan en «Otros» (gris) y como mucho 8 sectores.
  Comparar ángulos es más difícil que comparar longitudes: el panel ofrece verlos
  como barras ordenadas.
* Cajas: mediana, cuartiles y bigotes de Tukey (1.5·IQR); los puntos sueltos, si se
  enseñan, se dibujan todos (con un poco de dispersión horizontal) en lugar de solo
  los atípicos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure

from ..estadistica import formatear
from ..histograma import AjusteHistograma, ErrorHistograma, Histograma, ajustar_distribucion, bordes, histograma
from .grafica import PALETA_SERIES, OpcionesGrafica, SerieDibujo, _estilo_ejes, _leyenda

TIPOS = {
    "xy": "Puntos x-y",
    "histograma": "Histograma",
    "barras": "Barras",
    "circular": "Sectores (circular)",
    "cajas": "Cajas / violín",
    "polar": "Polar",
}
MAX_SECTORES = 8
_RE_UNIDAD = re.compile(r"\(([^()]*)\)\s*$")


class ErrorGrafica(ValueError):
    """Los datos no sirven para este tipo de gráfica (el mensaje explica por qué)."""


@dataclass(eq=False)
class Columna:
    """Valores de una columna con su nombre, su incertidumbre y su color."""

    nombre: str
    valores: np.ndarray
    errores: np.ndarray | None = None
    indice: int = 0
    color: str | None = None
    filas: np.ndarray | None = None

    def color_en(self, oscuro: bool) -> str:
        return self.color or PALETA_SERIES[oscuro][self.indice % len(PALETA_SERIES[oscuro])]


def _objetivos(fig: Figure) -> list:
    if not hasattr(fig, "_ajustelab"):
        fig._ajustelab = {}
    return fig._ajustelab.setdefault("objetivos", [])


def _titulo(ax, o: OpcionesGrafica, c: dict) -> None:
    if o.titulo:
        ax.set_title(o.titulo, color=c["texto"], fontsize=o.tam_fuente * 1.15)


def _rejilla_valores(ax, o: OpcionesGrafica, c: dict, eje: str) -> None:
    """Rejilla solo en el eje de los valores (la otra no aporta nada)."""
    ax.grid(False)
    if o.rejilla:
        ax.grid(True, axis=eje, color=c["rejilla"], linewidth=0.6, alpha=0.8)
        ax.set_axisbelow(True)


def _valor(v: float, e: float | None = None) -> str:
    if e is not None and np.isfinite(e) and e > 0:
        return formatear(v, e)
    return f"{v:.6g}"


# ---------------------------------------------------------------------------
# Aviso (cuando no se puede dibujar)
# ---------------------------------------------------------------------------
@dataclass(eq=False)
class Aviso:
    texto: str
    permite_log_x = False
    permite_log_y = False

    def dibujar(self, fig: Figure, o: OpcionesGrafica, c: dict, oscuro: bool = False):
        fig.text(0.5, 0.5, self.texto, ha="center", va="center", color=c["secundario"], fontsize=o.tam_fuente,
                 wrap=True)
        return None

    def tablas(self) -> dict[str, pd.DataFrame]:
        return {}


# ---------------------------------------------------------------------------
# Histograma
# ---------------------------------------------------------------------------
@dataclass(eq=False)
class HistoGrafica:
    columnas: list[Columna]
    histogramas: list[Histograma]
    ajustes: list[AjusteHistograma | None]
    normalizacion: str = "cuentas"
    errores: bool = True
    nombre_x: str = ""
    avisos: list[str] = field(default_factory=list)
    permite_log_x = False
    permite_log_y = True

    def dibujar(self, fig: Figure, o: OpcionesGrafica, c: dict, oscuro: bool = False):
        ax = fig.add_subplot()
        _estilo_ejes(ax, c, o)
        _rejilla_valores(ax, o, c, "y")
        una = len(self.columnas) == 1
        alturas = []
        for col, h, aj in zip(self.columnas, self.histogramas, self.ajustes):
            color = col.color_en(oscuro)
            y, dy = h.valores(self.normalizacion)
            alturas.append((y, dy))
            if una:
                ax.bar(h.bordes[:-1], y, width=h.anchos, align="edge", color=color, alpha=0.85, edgecolor=c["ejes"],
                       linewidth=0.6, label=col.nombre, zorder=2)
            else:
                ax.stairs(y, h.bordes, color=color, alpha=0.12, fill=True, zorder=2)
                ax.stairs(y, h.bordes, color=color, linewidth=1.8, label=col.nombre, zorder=3)
            if self.errores:
                ax.errorbar(h.centros, y, yerr=dy, fmt="none", ecolor=c["texto"] if una else color, elinewidth=1,
                            capsize=2, alpha=0.75, zorder=4)
            if aj is not None:
                cx, cy = aj.curva(h, self.normalizacion)
                trazo = c["texto"] if una else color
                etiqueta = (aj.nombre if una else f"{aj.nombre} ({col.nombre})") + "\n" + ", ".join(
                    f"{n} = {formatear(v, e)}" for n, v, e in aj.parametros[:2])
                if aj.ndof > 0:
                    etiqueta += f"\nχ²/ν = {aj.chi2 / aj.ndof:.3g}, p = {aj.p:.2g}"
                if aj.discreta:
                    ax.plot(cx, cy, "o", ms=4.5, color=trazo, mfc=c["ejes"], mew=1.5, label=etiqueta, zorder=5)
                else:
                    ax.plot(cx, cy, color=trazo, linewidth=2, linestyle="-" if una else "--", label=etiqueta,
                            zorder=5)
        h0 = self.histogramas[0]
        ax.set_xlabel(o.etiqueta_x or self.nombre_x)
        ax.set_ylabel(o.etiqueta_y or h0.etiqueta_y(self.normalizacion))
        if o.log_y:
            ax.set_yscale("log", nonpositive="clip")
        else:
            ax.set_ylim(bottom=0)
        _titulo(ax, o, c)
        handles, labels = ax.get_legend_handles_labels()
        if o.leyenda and len(handles) >= 2:
            _leyenda(ax, handles, labels, o, c)

        def etiqueta(evento):
            if evento.inaxes is not ax or evento.xdata is None:
                return None
            b = h0.bordes
            i = int(np.searchsorted(b, evento.xdata, side="right")) - 1
            if i == b.size - 1 and evento.xdata == b[-1]:
                i -= 1
            if not 0 <= i < b.size - 1:
                return None
            techo = max(float(y[i] + (dy[i] if self.errores else 0)) for y, dy in alturas)
            if not 0 <= evento.ydata <= techo * 1.03 + 1e-300:
                return None
            cierre = "]" if i == b.size - 2 else ")"
            lineas = [f"[{b[i]:.6g}, {b[i + 1]:.6g}{cierre}"]
            for col, h, aj, (y, dy) in zip(self.columnas, self.histogramas, self.ajustes, alturas):
                txt = f"{col.nombre}: N = {h.cuentas[i]} ± {np.sqrt(h.cuentas[i]):.2g}"
                if self.normalizacion != "cuentas":
                    txt += f"  ({y[i]:.4g} ± {dy[i]:.2g})"
                if aj is not None:
                    txt += f"; esperadas {aj.esperadas(h)[i]:.3g}"
                lineas.append(txt)
            return "\n".join(lineas)

        _objetivos(fig).append(etiqueta)
        return ax

    def tablas(self) -> dict[str, pd.DataFrame]:
        t = {}
        filas_ajuste = []
        for col, h, aj in zip(self.columnas, self.histogramas, self.ajustes):
            y, dy = h.valores(self.normalizacion)
            df = pd.DataFrame({"desde": h.bordes[:-1], "hasta": h.bordes[1:], "centro": h.centros,
                               "cuentas": h.cuentas, "error_cuentas": np.sqrt(h.cuentas)})
            if self.normalizacion != "cuentas":
                df[self.normalizacion] = y
                df[f"error_{self.normalizacion}"] = dy
            if aj is not None:
                df["esperadas"] = aj.esperadas(h)
                for n, v, e in aj.parametros:
                    filas_ajuste.append({"columna": col.nombre, "distribucion": aj.distribucion, "parametro": n,
                                         "valor": v, "error": e, "chi2": aj.chi2, "ndof": aj.ndof, "p": aj.p})
            t[f"histograma {col.nombre}"] = df
        if filas_ajuste:
            t["ajuste"] = pd.DataFrame(filas_ajuste)
        return t


def construir_histograma(columnas: list[Columna], regla: str = "fd", *, intervalos: int | None = None,
                         ancho: float | None = None, normalizacion: str = "cuentas", errores: bool = True,
                         distribucion: str | None = None, nombre_x: str = "") -> HistoGrafica:
    """Histogramas de una o varias columnas con los mismos intervalos (calculados
    con todos los datos juntos) y, si se pide, el ajuste de cada una."""
    columnas = [c for c in columnas if c.valores.size]
    if not columnas:
        raise ErrorGrafica("Elige al menos una columna con números para el histograma.")
    todos = np.concatenate([c.valores for c in columnas])
    try:
        b = bordes(todos, regla, intervalos=intervalos, ancho=ancho)
        hs = [histograma(c.valores, con_bordes=b) for c in columnas]
    except ErrorHistograma as exc:
        raise ErrorGrafica(str(exc)) from None
    ajustes, avisos = [], []
    for c, h in zip(columnas, hs):
        if not distribucion:
            ajustes.append(None)
            continue
        try:
            ajustes.append(ajustar_distribucion(c.valores, distribucion, h))
            avisos += [f"{c.nombre}: {a}" for a in ajustes[-1].avisos]
        except ErrorHistograma as exc:
            ajustes.append(None)
            avisos.append(f"{c.nombre}: {exc}")
    if not nombre_x:
        nombre_x = columnas[0].nombre if len(columnas) == 1 else "Valor"
        unidades = {m.group(1) if m else None for m in (_RE_UNIDAD.search(c.nombre) for c in columnas)}
        if len(columnas) > 1 and len(unidades) == 1 and None not in unidades:  # «T A (s)», «T B (s)» → «Valor (s)»
            nombre_x = f"Valor ({unidades.pop()})"
    return HistoGrafica(columnas, hs, ajustes, normalizacion, errores, nombre_x, avisos)


# ---------------------------------------------------------------------------
# Barras
# ---------------------------------------------------------------------------
@dataclass(eq=False)
class BarrasGrafica:
    categorias: list[str]
    series: list[Columna]
    horizontal: bool = False
    valores_visibles: bool = False
    nombre_categorias: str = ""
    permite_log_x = False
    permite_log_y = True

    def dibujar(self, fig: Figure, o: OpcionesGrafica, c: dict, oscuro: bool = False):
        ax = fig.add_subplot()
        _estilo_ejes(ax, c, o)
        _rejilla_valores(ax, o, c, "x" if self.horizontal else "y")
        n = len(self.series)
        pos = np.arange(len(self.categorias), dtype=float)
        ancho = 0.8 / max(n, 1)
        error_kw = dict(ecolor=c["texto"], elinewidth=1, capsize=3, alpha=0.8)
        objetivos = _objetivos(fig)
        for k, s in enumerate(self.series):
            color = s.color_en(oscuro)
            desplaz = (k - (n - 1) / 2) * ancho
            if self.horizontal:
                cont = ax.barh(pos + desplaz, s.valores, height=ancho * 0.92, xerr=s.errores, color=color,
                               label=s.nombre, error_kw=error_kw, zorder=3)
            else:
                cont = ax.bar(pos + desplaz, s.valores, width=ancho * 0.92, yerr=s.errores, color=color,
                              label=s.nombre, error_kw=error_kw, zorder=3)
            if self.valores_visibles:
                ax.bar_label(cont, fmt="%.3g", padding=2, color=c["texto"], fontsize=o.tam_fuente * 0.8)
            for i, rect in enumerate(cont.patches):
                e = None if s.errores is None else float(s.errores[i])
                texto = f"{self.categorias[i]}\n{s.nombre} = {_valor(float(s.valores[i]), e)}"
                objetivos.append(lambda ev, r=rect, t=texto: t if r.contains(ev)[0] else None)
        cero = ax.axvline if self.horizontal else ax.axhline
        cero(0, color=c["secundario"], linewidth=0.8, zorder=2)
        largo = sum(len(t) for t in self.categorias)
        if self.horizontal:
            ax.set_yticks(pos, self.categorias)
            ax.invert_yaxis()  # la primera categoría arriba
            ax.tick_params(axis="y", length=0)
        else:
            girar = largo > 60 or len(self.categorias) > 12
            ax.set_xticks(pos, self.categorias, rotation=45 if girar else 0, ha="right" if girar else "center",
                          rotation_mode="anchor")
            ax.tick_params(axis="x", length=0)
        etiqueta_valores = o.etiqueta_y or (self.series[0].nombre if n == 1 else "")
        etiqueta_cat = o.etiqueta_x or self.nombre_categorias
        (ax.set_xlabel if self.horizontal else ax.set_ylabel)(etiqueta_valores)
        (ax.set_ylabel if self.horizontal else ax.set_xlabel)(etiqueta_cat)
        if o.log_y and all(np.all(s.valores[np.isfinite(s.valores)] > 0) for s in self.series):
            (ax.set_xscale if self.horizontal else ax.set_yscale)("log")
        _titulo(ax, o, c)
        handles, labels = ax.get_legend_handles_labels()
        if o.leyenda and len(handles) >= 2:
            _leyenda(ax, handles, labels, o, c)
        return ax

    def tablas(self) -> dict[str, pd.DataFrame]:
        df = pd.DataFrame({self.nombre_categorias or "categoria": self.categorias})
        for s in self.series:
            df[s.nombre] = s.valores
            if s.errores is not None:
                df[f"error {s.nombre}"] = s.errores
        return {"barras": df}


def ordenar_categorias(categorias: list[str], series: list[Columna], orden: str = "tabla"):
    """Reordena las categorías según la primera serie: «desc», «asc» o «tabla»."""
    if orden == "tabla" or not series:
        return categorias, series
    v = series[0].valores.astype(float)
    clave = np.where(np.isfinite(v), v, -np.inf if orden == "desc" else np.inf)
    idx = np.argsort(-clave if orden == "desc" else clave, kind="stable")
    nuevas = [Columna(s.nombre, s.valores[idx], None if s.errores is None else s.errores[idx], s.indice, s.color,
                      None if s.filas is None else s.filas[idx]) for s in series]
    return [categorias[i] for i in idx], nuevas


# ---------------------------------------------------------------------------
# Sectores
# ---------------------------------------------------------------------------
@dataclass(eq=False)
class CircularGrafica:
    etiquetas: list[str]
    valores: np.ndarray
    indice_otros: int = -1
    anillo: bool = True
    porcentajes: bool = True
    nombre: str = ""
    permite_log_x = False
    permite_log_y = False

    def dibujar(self, fig: Figure, o: OpcionesGrafica, c: dict, oscuro: bool = False):
        ax = fig.add_subplot()
        ax.set_facecolor(c["fondo"])
        paleta = PALETA_SERIES[oscuro]
        colores = [c["excluidos"] if i == self.indice_otros else paleta[i % len(paleta)]
                   for i in range(len(self.valores))]
        total = float(np.sum(self.valores))
        pct = 100 * self.valores / total
        textos = [f"{e}\n{p:.1f} %" if self.porcentajes else e for e, p in zip(self.etiquetas, pct)]
        cunas, _ = ax.pie(self.valores, colors=colores, startangle=90, counterclock=False,
                          wedgeprops=dict(width=0.42 if self.anillo else 1, edgecolor=c["ejes"], linewidth=1.5))
        _etiquetas_sectores(ax, cunas, textos, c, o.tam_fuente * 0.85)
        if self.anillo:
            ax.text(0, 0, f"{o.etiqueta_y or self.nombre or 'Total'}\n{total:.4g}", ha="center", va="center",
                    color=c["texto"], fontsize=o.tam_fuente)
        ax.set_aspect("equal")
        _titulo(ax, o, c)
        objetivos = _objetivos(fig)
        for cuna, e, v, p in zip(cunas, self.etiquetas, self.valores, pct):
            texto = f"{e}\n{v:.6g} ({p:.1f} %)"
            objetivos.append(lambda ev, w=cuna, t=texto: t if w.contains(ev)[0] else None)
        return ax

    def tablas(self) -> dict[str, pd.DataFrame]:
        total = float(np.sum(self.valores))
        return {"sectores": pd.DataFrame({"categoria": self.etiquetas, self.nombre or "valor": self.valores,
                                          "porcentaje": 100 * self.valores / total})}


def _etiquetas_sectores(ax, cunas, textos, c: dict, tam: float) -> None:
    """Etiquetas fuera de los sectores, con una línea hasta su sector. En cada lado
    se separan en vertical para que no se monten (los sectores pequeños seguidos)."""
    lineas_texto = max(t.count("\n") + 1 for t in textos)
    # Puntos por unidad de radio (los ejes ocupan ~85 % del alto y van de −1.45 a 1.45)
    pt_por_unidad = ax.figure.get_figheight() * 72 * 0.85 / 2.9
    separacion = 1.3 * lineas_texto * tam / pt_por_unidad
    lados = {1: [], -1: []}
    for cuna, texto in zip(cunas, textos):
        ang = np.radians((cuna.theta1 + cuna.theta2) / 2)
        x, y = np.cos(ang), np.sin(ang)
        lados[1 if x >= 0 else -1].append([y * 1.25, x, y, texto])
    for lado, items in lados.items():
        items.sort(key=lambda it: -it[0])  # de arriba abajo
        for i in range(1, len(items)):  # empuja hacia abajo las que se montan
            items[i][0] = min(items[i][0], items[i - 1][0] - separacion)
        exceso = (-1.35) - items[-1][0] if items else 0
        if exceso > 0:  # si se salen por abajo, sube todo el bloque
            for it in items:
                it[0] += exceso
        for ty, x, y, texto in items:
            tx = lado * max(1.2, np.sqrt(max(1.25 ** 2 - ty ** 2, 0)) + 0.05)
            ax.annotate(texto, xy=(x, y), xytext=(tx, ty), ha="left" if lado > 0 else "right", va="center",
                        color=c["texto"], fontsize=tam,
                        arrowprops=dict(arrowstyle="-", color=c["secundario"], linewidth=0.8,
                                        shrinkA=0, shrinkB=0, connectionstyle="arc3,rad=0"))
    ax.set_xlim(-1.75, 1.75)
    ax.set_ylim(-1.45, 1.45)


def preparar_sectores(etiquetas: list[str], valores, minimo_pct: float = 3.0, ordenar: bool = True,
                      maximo: int = MAX_SECTORES):
    """Quita vacíos y ceros, ordena de mayor a menor y agrupa en «Otros» los sectores
    de menos de ``minimo_pct`` % (y los que pasen de ``maximo``).
    Devuelve (etiquetas, valores, índice de «Otros» o −1)."""
    v = np.asarray(valores, float)
    validos = np.isfinite(v)
    if np.any(v[validos] < 0):
        raise ErrorGrafica("Los sectores necesitan valores ≥ 0: con negativos, usa barras.")
    pares = [(e, float(x)) for e, x, ok in zip(etiquetas, v, validos) if ok and x > 0]
    if not pares:
        raise ErrorGrafica("No hay valores positivos para los sectores.")
    if ordenar:
        pares.sort(key=lambda p: -p[1])
    total = sum(x for _, x in pares)
    pequeno = [100 * x / total < minimo_pct for _, x in pares]
    if sum(pequeno) == 1 and len(pares) <= maximo:  # un «Otros» de un solo sector no agrupa nada
        pequeno = [False] * len(pares)
    grandes = [i for i, p in enumerate(pequeno) if not p]
    if len(grandes) + (1 if any(pequeno) else 0) > maximo:  # demasiados: los menores, a «Otros»
        quedan = set(sorted(grandes, key=lambda i: -pares[i][1])[: maximo - 1])
        pequeno = [i not in quedan for i in range(len(pares))]
    grandes = [pares[i] for i, p in enumerate(pequeno) if not p]
    pequenos = [pares[i] for i, p in enumerate(pequeno) if p]
    etq = [e for e, _ in grandes]
    vals = [x for _, x in grandes]
    otros = -1
    if pequenos:
        otros = len(etq)
        etq.append(f"Otros ({len(pequenos)})")
        vals.append(sum(x for _, x in pequenos))
    return etq, np.array(vals), otros


# ---------------------------------------------------------------------------
# Cajas y violín
# ---------------------------------------------------------------------------
def _estadisticos(v: np.ndarray) -> str:
    q1, med, q3 = np.percentile(v, [25, 50, 75])
    iqr = q3 - q1
    dentro = v[(v >= q1 - 1.5 * iqr) & (v <= q3 + 1.5 * iqr)]
    atipicos = v.size - dentro.size
    media = float(v.mean())
    error = float(v.std(ddof=1) / np.sqrt(v.size)) if v.size > 1 else None
    return (f"n = {v.size}\nmedia = {_valor(media, error)}\nmediana = {med:.6g}\n"
            f"Q1 – Q3 = {q1:.4g} – {q3:.4g}\nbigotes = {dentro.min():.4g} – {dentro.max():.4g}"
            + (f"\natípicos: {atipicos}" if atipicos else ""))


@dataclass(eq=False)
class CajasGrafica:
    grupos: list[Columna]
    modo: str = "cajas"  # «cajas», «violin» o «ambos»
    puntos: bool = True
    media: bool = True
    permite_log_x = False
    permite_log_y = True

    def dibujar(self, fig: Figure, o: OpcionesGrafica, c: dict, oscuro: bool = False):
        ax = fig.add_subplot()
        _estilo_ejes(ax, c, o)
        _rejilla_valores(ax, o, c, "y")
        datos = [g.valores for g in self.grupos]
        pos = np.arange(1, len(datos) + 1, dtype=float)
        colores = [g.color_en(oscuro) for g in self.grupos]
        objetivos = _objetivos(fig)
        if self.modo in ("violin", "ambos"):
            validos = [i for i, d in enumerate(datos) if d.size >= 2 and np.ptp(d) > 0]
            if validos:
                vp = ax.violinplot([datos[i] for i in validos], positions=pos[validos], widths=0.8,
                                   showextrema=False)
                for cuerpo, i in zip(vp["bodies"], validos):
                    cuerpo.set_facecolor(colores[i])
                    cuerpo.set_edgecolor(colores[i])
                    cuerpo.set_alpha(0.28 if self.modo == "ambos" else 0.45)
                    cuerpo.set_zorder(2)
                    texto = f"{self.grupos[i].nombre}\n{_estadisticos(datos[i])}"
                    objetivos.append(lambda ev, b=cuerpo, t=texto: t if b.contains(ev)[0] else None)
        if self.modo in ("cajas", "ambos"):
            bp = ax.boxplot(datos, positions=pos, widths=0.22 if self.modo == "ambos" else 0.5, patch_artist=True,
                            showfliers=not self.puntos, whis=1.5, manage_ticks=False,
                            medianprops=dict(color=c["texto"], linewidth=1.6),
                            whiskerprops=dict(color=c["secundario"], linewidth=1.1),
                            capprops=dict(color=c["secundario"], linewidth=1.1),
                            flierprops=dict(marker="o", ms=4, mfc="none", mec=c["secundario"]))
            for caja, color, g, d in zip(bp["boxes"], colores, self.grupos, datos):
                caja.set_facecolor(to_rgba(color, 0.35))
                caja.set_edgecolor(color)
                caja.set_linewidth(1.4)
                caja.set_zorder(3)
                texto = f"{g.nombre}\n{_estadisticos(d)}"
                objetivos.insert(0, lambda ev, b=caja, t=texto: t if b.contains(ev)[0] else None)
        if self.puntos:
            rng = np.random.default_rng(0)  # misma dispersión en cada dibujo
            amplitud = 0.12 if self.modo == "violin" else 0.07
            for p, d, color in zip(pos, datos, colores):
                ax.plot(p + rng.uniform(-amplitud, amplitud, d.size), d, "o", ms=3, color=color, alpha=0.55,
                        linestyle="none", zorder=4)
        if self.media:
            medias = [float(d.mean()) for d in datos]
            ax.plot(pos, medias, "D", ms=6, mfc=c["ejes"], mec=c["texto"], mew=1.3, linestyle="none", zorder=5)
        ax.set_xticks(pos, [g.nombre for g in self.grupos])
        ax.tick_params(axis="x", length=0)
        ax.set_xlim(0.4, len(datos) + 0.6)
        ax.set_ylabel(o.etiqueta_y or (self.grupos[0].nombre if len(self.grupos) == 1 else ""))
        if o.etiqueta_x:
            ax.set_xlabel(o.etiqueta_x)
        if o.log_y and all(np.all(d > 0) for d in datos):
            ax.set_yscale("log")
        _titulo(ax, o, c)
        return ax

    def tablas(self) -> dict[str, pd.DataFrame]:
        filas = []
        for g in self.grupos:
            v = g.valores
            q1, med, q3 = np.percentile(v, [25, 50, 75])
            iqr = q3 - q1
            dentro = v[(v >= q1 - 1.5 * iqr) & (v <= q3 + 1.5 * iqr)]
            filas.append({"columna": g.nombre, "n": v.size, "media": v.mean(),
                          "desviacion": v.std(ddof=1) if v.size > 1 else np.nan, "mediana": med, "q1": q1, "q3": q3,
                          "bigote_inf": dentro.min(), "bigote_sup": dentro.max(),
                          "atipicos": int(v.size - dentro.size)})
        return {"cajas": pd.DataFrame(filas)}


# ---------------------------------------------------------------------------
# Polar
# ---------------------------------------------------------------------------
_PI = ["0", "π/4", "π/2", "3π/4", "π", "5π/4", "3π/2", "7π/4"]


def _posicion_etiquetas_r(ax, series) -> None:
    """Pone los números del eje r en la dirección con radios más pequeños, para que
    no caigan encima de la curva."""
    th = np.concatenate([s.x for s in series]) if series else np.array([])
    r = np.concatenate([s.y for s in series]) if series else np.array([])
    ok = np.isfinite(th) & np.isfinite(r)
    if not ok.any():
        return
    sectores = 16
    k = (np.mod(th[ok], 2 * np.pi) / (2 * np.pi) * sectores).astype(int) % sectores
    maximo = np.full(sectores, -np.inf)
    np.maximum.at(maximo, k, np.abs(r[ok]))
    maximo[~np.isfinite(maximo)] = -1  # sector sin datos: el mejor sitio
    mejor = int(np.argmin(maximo))
    ax.set_rlabel_position((mejor + 0.5) * 360 / sectores)


@dataclass(eq=False)
class PolarGrafica:
    series: list[SerieDibujo]  # x = θ en radianes, y = r
    nombre_theta: str = "θ"
    grados: bool = True
    horario: bool = False  # True: 0 arriba y sentido horario (brújula); False: 0 a la derecha, antihorario
    barras_error: bool = True
    permite_log_x = False
    permite_log_y = False

    def dibujar(self, fig: Figure, o: OpcionesGrafica, c: dict, oscuro: bool = False):
        ax = fig.add_subplot(projection="polar")
        ax.set_facecolor(c["ejes"])
        if self.horario:
            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
        ax.tick_params(colors=c["texto"], labelsize=o.tam_fuente * 0.85)
        ax.grid(o.rejilla, color=c["rejilla"], linewidth=0.6)
        ax.spines["polar"].set_color(c["rejilla"])
        if not self.grados:
            ax.set_xticks(np.arange(8) * np.pi / 4, _PI)
        _posicion_etiquetas_r(ax, self.series)
        objetivos = _objetivos(fig)
        for s in self.series:
            color = s.color_en(oscuro)
            m = np.ones(s.x.size, bool) if s.incluidos is None else s.incluidos
            linea = "-" if s.estilo in ("linea", "puntos_linea") else "none"
            marcador = s.marcador if s.estilo in ("puntos", "puntos_linea") else "none"
            dy = s.dy if self.barras_error else None
            etiqueta = f"r: {s.nombre}"
            if dy is not None:
                cont = ax.errorbar(s.x[m], s.y[m], yerr=dy[m], color=color, ecolor=color, linestyle=linea,
                                   marker=marcador, ms=5, linewidth=1.6, elinewidth=1, capsize=0, label=etiqueta,
                                   zorder=3)
                linea2d = cont.lines[0]
            else:
                (linea2d,) = ax.plot(s.x[m], s.y[m], color=color, linestyle=linea, marker=marcador, ms=5,
                                     linewidth=1.6, label=etiqueta, zorder=3)
            if np.any(~m) and marcador != "none":
                ax.plot(s.x[~m], s.y[~m], linestyle="none", marker=marcador, ms=6, mfc="none", mec=color, alpha=0.5,
                        zorder=2)
            indices = np.flatnonzero(m)

            def etiqueta_punto(ev, ln=linea2d, s=s, idx=indices):
                dentro, info = ln.contains(ev)
                if not dentro or not len(info.get("ind", [])):
                    return None
                j = int(idx[info["ind"][0]])
                th = np.degrees(s.x[j]) if self.grados else s.x[j]
                fila = int(s.filas[j]) + 1 if s.filas is not None else j + 1
                r = _valor(float(s.y[j]), None if s.dy is None else float(s.dy[j]))
                return f"fila {fila}\n{self.nombre_theta} = {th:.6g}{'°' if self.grados else ' rad'}\n{s.nombre} = {r}"

            objetivos.append(etiqueta_punto)
        _titulo(ax, o, c)
        handles, labels = ax.get_legend_handles_labels()
        if o.leyenda and handles:  # en polar no hay etiqueta del eje r: la leyenda dice qué es r
            ley = ax.legend(handles, labels, fontsize=o.tam_fuente * 0.85, framealpha=0.9, facecolor=c["ejes"],
                            edgecolor=c["rejilla"], loc="upper left", bbox_to_anchor=(1.04, 1.0))
            for t in ley.get_texts():
                t.set_color(c["texto"])
        return ax

    def tablas(self) -> dict[str, pd.DataFrame]:
        t = {}
        for s in self.series:
            th = np.degrees(s.x) if self.grados else s.x
            df = pd.DataFrame({f"{self.nombre_theta} ({'grados' if self.grados else 'rad'})": th, s.nombre: s.y})
            if s.dy is not None:
                df[f"error {s.nombre}"] = s.dy
            if s.filas is not None:
                df.insert(0, "fila", s.filas.astype(int) + 1)
            t[f"polar {s.nombre}"] = df
        return t
