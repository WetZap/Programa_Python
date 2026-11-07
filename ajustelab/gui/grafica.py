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
* Personalización: el título, la leyenda, las etiquetas de los ejes y los textos
  libres se arrastran (``fig._ajustelab["movibles"]``) y sus posiciones, junto con
  límites, marcas, tamaños, colores y plantillas de estilo, van en ``OpcionesGrafica``.
* Modo «Representar» (sin ajuste): varias series frente a una misma x, en el eje
  izquierdo o en el derecho (o en dos paneles apilados), con o sin barras de error,
  y con el eje x partido (cortes «//») para saltarse tramos sin datos.
  Los demás tipos (histograma, barras, sectores, cajas, polar) están en
  :mod:`ajustelab.gui.graficas` y se dibujan con ``Escena.especial``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse
from matplotlib.transforms import IdentityTransform
from matplotlib.widgets import RectangleSelector, SpanSelector
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QInputDialog, QMenu, QToolButton, QVBoxLayout, QWidget

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
# Paleta categórica en orden fijo (azul, naranja, aguamarina, amarillo, magenta, verde,
# violeta, rojo), con su versión para fondo oscuro. Las tres primeras se distinguen
# entre sí también con daltonismo; a partir de la cuarta, el marcador cambia con la
# serie para que la identidad no dependa solo del color (y se lea en blanco y negro).
PALETA_SERIES = {
    False: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    True: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
}
MARCADORES = ["o", "s", "^", "D", "v", "P", "X", "*"]
ESTILOS_SERIE = {"puntos": "Puntos", "puntos_linea": "Puntos y línea", "linea": "Línea"}


def con_coma(texto: str) -> str:
    """3.142 ± 0.023 → 3,142 ± 0,023 (solo puntos entre cifras)."""
    return _RE_DECIMAL.sub(",", texto)


LOC_LEYENDA = {
    "auto": "Automática",
    "upper right": "Arriba a la derecha",
    "upper left": "Arriba a la izquierda",
    "lower right": "Abajo a la derecha",
    "lower left": "Abajo a la izquierda",
    "upper center": "Arriba, en el centro",
    "lower center": "Abajo, en el centro",
    "center right": "A la derecha, en el centro",
    "center left": "A la izquierda, en el centro",
    "center": "En el centro",
    "outside right upper": "Fuera, a la derecha",
    "outside upper center": "Fuera, encima",
    "outside lower center": "Fuera, debajo",
}
MARCAS = {"fuera": "Hacia fuera", "dentro": "Hacia dentro", "ambas": "A los dos lados"}
NOTACION = {"auto": "Automática", "cientifica": "Científica (×10ⁿ)", "normal": "Sin exponente"}
BORDES = {"completos": "Los cuatro lados", "abiertos": "Solo abajo y a la izquierda"}

# Opciones que forman el «estilo» (se guardan en las plantillas). El resto
# (textos, posiciones, límites, anotaciones) depende de cada gráfica.
CLAVES_ESTILO = (
    "tam_fuente", "tam_titulo", "titulo_negrita", "alin_titulo", "leyenda", "loc_leyenda", "leyenda_columnas",
    "leyenda_marco", "tam_leyenda", "rejilla", "rejilla_menor", "marcas", "marcas_espejo", "marcas_menores",
    "bordes", "notacion", "tam_marcador", "grosor_linea", "grosor_ajuste", "grosor_error", "tam_tapa",
    "color_datos", "color_ajuste", "cuadro_resultados",
)
_POSICIONES = ("pos_titulo", "pos_etiqueta_x", "pos_etiqueta_y", "pos_etiqueta_y2", "pos_leyenda")


@dataclass
class OpcionesGrafica:
    # Textos (admiten LaTeX entre $…$)
    titulo: str = ""
    etiqueta_x: str = ""  # vacío: nombre de la columna
    etiqueta_y: str = ""
    etiqueta_y2: str = ""  # eje y derecho (o panel inferior) en «Representar»
    tam_fuente: float = 10.0
    tam_titulo: float = 0.0  # 0: 1.15 × tam_fuente
    titulo_negrita: bool = False
    alin_titulo: str = "center"  # left, center, right
    # Posiciones arrastradas: (x, y, sistema), con sistema «ejes» (fracción de los
    # ejes) o «figura» (fracción de la figura). None: la automática.
    pos_titulo: tuple | None = None
    pos_etiqueta_x: tuple | None = None
    pos_etiqueta_y: tuple | None = None
    pos_etiqueta_y2: tuple | None = None
    # Leyenda
    leyenda: bool = True
    loc_leyenda: str = "auto"  # ver LOC_LEYENDA
    pos_leyenda: tuple | None = None  # esquina inferior izquierda (x, y, sistema)
    leyenda_columnas: int = 1
    leyenda_marco: bool = True
    tam_leyenda: float = 0.0  # 0: 0.85 × tam_fuente
    titulo_leyenda: str = ""
    # Ejes
    rejilla: bool = True
    rejilla_menor: bool = False
    marcas: str = "fuera"  # ver MARCAS
    marcas_espejo: bool = False  # marcas también arriba y a la derecha
    marcas_menores: bool = False
    bordes: str = "completos"  # ver BORDES
    notacion: str = "auto"  # ver NOTACION
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    y2_min: float | None = None
    y2_max: float | None = None
    log_x: bool = False
    log_y: bool = False
    log_y2: bool = False
    residuos: bool = True
    # Datos y curvas
    tam_marcador: float = 5.0
    grosor_linea: float = 1.6  # series de «Representar»
    grosor_ajuste: float = 2.0  # curvas ajustadas e interpolantes
    grosor_error: float = 1.0
    tam_tapa: float = 2.0  # tope de las barras de error
    color_datos: str = ""  # vacío: el del tema
    color_ajuste: str = ""
    # Cuadro de resultados y anotaciones
    cuadro_resultados: bool = True
    pos_cuadro: tuple[float, float] = (0.03, 0.04)  # esquina inferior izquierda, fracción de los ejes
    # Textos libres: {"texto", "x", "y" (fracción de la figura), "flecha": [x, y] en datos o None, "tam"}
    anotaciones: list = field(default_factory=list)

    def a_dict(self) -> dict:
        d = dict(self.__dict__)
        d["anotaciones"] = [dict(a) for a in self.anotaciones]
        return d

    @classmethod
    def desde_dict(cls, d: dict) -> "OpcionesGrafica":
        o = cls()
        for k, v in (d or {}).items():
            if not hasattr(o, k):
                continue
            if k in ("pos_cuadro", *_POSICIONES) and v is not None:
                v = tuple(v)
            elif k == "anotaciones":
                v = [dict(a) for a in (v or []) if isinstance(a, dict) and "texto" in a]
            setattr(o, k, v)
        return o

    def estilo(self) -> dict:
        return {k: getattr(self, k) for k in CLAVES_ESTILO}

    def aplicar_estilo(self, estilo: dict) -> None:
        """Pone el estilo por defecto y encima el de ``estilo`` (una plantilla)."""
        base = OpcionesGrafica()
        for k in CLAVES_ESTILO:
            setattr(self, k, estilo.get(k, getattr(base, k)))

    def restablecer_posiciones(self) -> None:
        for k in _POSICIONES:
            setattr(self, k, None)
        self.pos_cuadro = OpcionesGrafica.pos_cuadro

    def reiniciar_contenido(self) -> None:
        """Al cargar otros datos: fuera textos, límites y anotaciones (dependen de los
        datos); el estilo y las posiciones se quedan."""
        base = OpcionesGrafica()
        for k in ("titulo", "etiqueta_x", "etiqueta_y", "etiqueta_y2", "x_min", "x_max", "y_min", "y_max",
                  "y2_min", "y2_max", "titulo_leyenda"):
            setattr(self, k, getattr(base, k))
        self.anotaciones = []

    def escalada(self, tam_fuente: float) -> "OpcionesGrafica":
        """Copia con otro tamaño de letra; los tamaños propios (título, leyenda,
        anotaciones) cambian en la misma proporción."""
        f = tam_fuente / self.tam_fuente if self.tam_fuente else 1.0
        o = replace(self, tam_fuente=tam_fuente, tam_titulo=self.tam_titulo * f, tam_leyenda=self.tam_leyenda * f)
        o.anotaciones = [{**a, "tam": (a.get("tam") or 0) * f} for a in self.anotaciones]
        return o

    @property
    def titulo_tam(self) -> float:
        return self.tam_titulo or self.tam_fuente * 1.15

    @property
    def leyenda_tam(self) -> float:
        return self.tam_leyenda or self.tam_fuente * 0.85


@dataclass(eq=False)  # se comparan por identidad (llevan arrays)
class SerieDibujo:
    """Una serie del modo «Representar». ``filas[i]`` es la fila de la tabla del punto i."""

    nombre: str
    x: np.ndarray
    y: np.ndarray
    dx: np.ndarray | None = None
    dy: np.ndarray | None = None
    incluidos: np.ndarray | None = None
    filas: np.ndarray | None = None
    eje: str = "izq"  # «izq» o «der»
    estilo: str = "puntos"  # ver ESTILOS_SERIE
    color: str | None = None  # None: el de la paleta según ``indice``
    indice: int = 0  # posición en la paleta y en MARCADORES

    def color_en(self, oscuro: bool) -> str:
        return self.color or PALETA_SERIES[oscuro][self.indice % len(PALETA_SERIES[oscuro])]

    @property
    def marcador(self) -> str:
        return MARCADORES[self.indice % len(MARCADORES)]


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
    # Modo «Representar»
    series: list[SerieDibujo] = field(default_factory=list)
    nombre_x: str = ""
    apilados: bool = False  # True: dos paneles con la misma x en vez de dos ejes y
    barras_error: bool = True
    cortes: list[tuple[float, float]] = field(default_factory=list)  # tramos de x que se quitan
    # Otros tipos de gráfica (histograma, barras…): objeto con dibujar(fig, o, c, oscuro)
    especial: object | None = None

    @property
    def vacia(self) -> bool:
        return self.datos is None and self.interseccion is None and not self.series and self.especial is None


# ---------------------------------------------------------------------------
# Eje x partido
# ---------------------------------------------------------------------------
def fusionar_cortes(cortes) -> list[tuple[float, float]]:
    """Ordena los cortes (a, b) y une los que se solapan."""
    limpios = sorted((min(a, b), max(a, b)) for a, b in cortes if np.isfinite(a) and np.isfinite(b) and a != b)
    salida: list[tuple[float, float]] = []
    for a, b in limpios:
        if salida and a <= salida[-1][1]:
            salida[-1] = (salida[-1][0], max(b, salida[-1][1]))
        else:
            salida.append((a, b))
    return salida


def fuera_de_cortes(x: np.ndarray, cortes) -> np.ndarray:
    """True en los puntos que no caen dentro de ningún corte (a < x < b)."""
    x = np.asarray(x, float)
    m = np.ones(x.shape, bool)
    for a, b in cortes:
        m &= ~((x > a) & (x < b))
    return m


def tramos_x(x: np.ndarray, cortes) -> list[tuple[float, float]]:
    """(mínimo, máximo) de los datos de cada tramo que queda entre los cortes."""
    x = np.sort(np.asarray(x, float)[np.isfinite(x)])
    tramos, desde = [], -np.inf
    for a, b in [*fusionar_cortes(cortes), (np.inf, np.inf)]:
        dentro = x[(x >= desde) & (x <= a)]
        if dentro.size:
            tramos.append((float(dentro[0]), float(dentro[-1])))
        desde = b
    return tramos


def detectar_huecos(x, factor: float = 6.0, fraccion: float = 0.12) -> list[tuple[float, float]]:
    """Huecos grandes entre datos consecutivos (más de ``factor`` veces el paso típico
    y más de ``fraccion`` del rango): son los cortes que propone «Cortar huecos»."""
    u = np.unique(np.asarray(x, float)[np.isfinite(x)])
    if u.size < 4:
        return []
    d = np.diff(u)
    paso = float(np.median(d))
    rango = float(u[-1] - u[0])
    return [(float(u[i]), float(u[i + 1])) for i in np.flatnonzero((d > factor * paso) & (d > fraccion * rango))]


def _limites_tramos(tramos, log: bool) -> list[tuple[float, float]]:
    """Límites de cada tramo con el mismo margen en todos, para que la escala del
    eje sea la misma a los dos lados de cada corte."""
    f = np.log10 if log else (lambda v: v)
    g = (lambda v: 10 ** v) if log else (lambda v: v)
    t = [(float(f(a)), float(f(b))) for a, b in tramos]
    total = sum(b - a for a, b in t)
    margen = 0.03 * total if total > 0 else 0.5
    return [(float(g(a - margen)), float(g(b + margen))) for a, b in t]


def _marcas_corte(izq, der, c) -> None:
    """Marcas «//» a los dos lados del hueco, arriba y abajo del eje."""
    from matplotlib.lines import Line2D

    estilo = dict(marker=[(-0.5, -1), (0.5, 1)], markersize=9, linestyle="none", color=c["secundario"],
                  mec=c["secundario"], mew=1.2, clip_on=False, zorder=30)
    for ax, xa in ((izq, 1), (der, 0)):  # add_artist: no cambia los límites de los datos
        ax.add_artist(Line2D([xa, xa], [0, 1], transform=ax.transAxes, **estilo))


# ---------------------------------------------------------------------------
# Dibujo (sin Qt)
# ---------------------------------------------------------------------------
def _estilo_ejes(ax, c, o: OpcionesGrafica):
    """Fondo, marcas, bordes, rejilla y notación de unos ejes cartesianos."""
    ax.set_facecolor(c["ejes"])
    abiertos = o.bordes == "abiertos"
    espejo = o.marcas_espejo and not abiertos
    ax.tick_params(which="both", colors=c["texto"], direction=_DIRECCION.get(o.marcas, "out"),
                   labelsize=o.tam_fuente * 0.9, top=espejo, right=espejo)
    for nombre, lado in ax.spines.items():
        lado.set_color(c["rejilla"])
        if abiertos and nombre in ("top", "right"):
            lado.set_visible(False)
    if o.marcas_menores or o.rejilla_menor:
        ax.minorticks_on()
        if not o.marcas_menores:  # solo la rejilla secundaria, sin marcas
            ax.tick_params(which="minor", length=0)
    if o.rejilla:
        ax.grid(True, which="major", color=c["rejilla"], linewidth=0.6, alpha=0.8)
    if o.rejilla_menor:
        ax.grid(True, which="minor", color=c["rejilla"], linewidth=0.4, alpha=0.45)
    _notacion(ax, o)
    for eje in (ax.xaxis, ax.yaxis):
        eje.label.set_color(c["texto"])
        eje.label.set_size(o.tam_fuente)
        eje.offsetText.set_color(c["texto"])
        eje.offsetText.set_size(o.tam_fuente * 0.85)


_DIRECCION = {"fuera": "out", "dentro": "in", "ambas": "inout"}


def _estilo_gemelo(t, c, o: OpcionesGrafica) -> None:
    """Eje y derecho (twinx): marcas como las del izquierdo y una sola rejilla."""
    t.grid(False)
    t.tick_params(which="both", colors=c["texto"], direction=_DIRECCION.get(o.marcas, "out"),
                  labelsize=o.tam_fuente * 0.9)
    if o.marcas_menores:
        t.minorticks_on()
    _notacion(t, o, ejes=("y",))
    t.yaxis.label.set_color(c["texto"])
    t.yaxis.label.set_size(o.tam_fuente)
    t.yaxis.offsetText.set_color(c["texto"])


def _notacion(ax, o: OpcionesGrafica, ejes=("x", "y")) -> None:
    if o.notacion == "auto":
        return
    for eje in ejes:
        try:
            if o.notacion == "cientifica":
                ax.ticklabel_format(axis=eje, style="sci", scilimits=(0, 0), useMathText=True)
            else:
                ax.ticklabel_format(axis=eje, style="plain", useOffset=False)
        except (AttributeError, TypeError, ValueError):  # escala logarítmica o categorías
            pass


def _registrar(fig: Figure, clave: str, artista, ax=None, **extra) -> None:
    """Apunta un elemento que se puede arrastrar (título, etiqueta, leyenda, texto)."""
    if not hasattr(fig, "_ajustelab"):
        fig._ajustelab = {}
    fig._ajustelab.setdefault("movibles", []).append({"clave": clave, "artista": artista, "ax": ax, **extra})


def _poner_titulo(fig: Figure, ax, o: OpcionesGrafica, c: dict, en_figura: bool = False):
    """Título con su tamaño, peso, alineación y, si se ha arrastrado, su posición.
    ``en_figura``: sobre toda la figura (varios paneles), no sobre unos ejes."""
    if not o.titulo or (ax is None and not en_figura):
        return None
    alin = o.alin_titulo if o.alin_titulo in ("left", "center", "right") else "center"
    kw = dict(color=c["texto"], fontsize=o.titulo_tam, fontweight="bold" if o.titulo_negrita else "normal")
    pos = o.pos_titulo
    if en_figura:
        if pos is not None and pos[2] == "figura":
            t = fig.suptitle(o.titulo, x=pos[0], y=pos[1], ha=alin, **kw)
        else:
            t = fig.suptitle(o.titulo, x={"left": 0.02, "center": 0.5, "right": 0.98}[alin], ha=alin, **kw)
        _registrar(fig, "titulo", t, None)
        return t
    if pos is not None and pos[2] == "ejes":
        t = ax.set_title(o.titulo, loc=alin, y=pos[1], **kw)
        t.set_x(pos[0])
    else:
        t = ax.set_title(o.titulo, loc=alin, **kw)
    _registrar(fig, "titulo", t, ax)
    return t


def _decorar_etiquetas(fig: Figure, o: OpcionesGrafica, ax_x=None, ax_y=None, ax_y2=None, sup_x=None) -> None:
    """Coloca las etiquetas de los ejes donde se arrastraron y las deja movibles."""
    for clave, ax, eje in (("etiqueta_x", ax_x, "xaxis"), ("etiqueta_y", ax_y, "yaxis"),
                           ("etiqueta_y2", ax_y2, "yaxis")):
        if ax is None:
            continue
        objeto = getattr(ax, eje)
        pos = getattr(o, "pos_" + clave)
        if pos is not None and pos[2] == "ejes":
            objeto.set_label_coords(pos[0], pos[1])
        _registrar(fig, clave, objeto.label, ax, eje=objeto)
    if sup_x is not None:  # etiqueta común a varios paneles (eje partido)
        pos = o.pos_etiqueta_x
        if pos is not None and pos[2] == "figura":
            sup_x.set_position(pos[:2])
            sup_x._autopos = False
        _registrar(fig, "etiqueta_x", sup_x, None)


def _limites(ax, o: OpcionesGrafica, x: bool = True, y: bool = True, ax_y2=None) -> None:
    """Límites fijados a mano (None: automático). En escala log se ignoran los ≤ 0."""
    def poner(funcion, lo, hi, log):
        if log:
            lo = lo if lo is None or lo > 0 else None
            hi = hi if hi is None or hi > 0 else None
        if lo is None and hi is None or (lo is not None and hi is not None and lo >= hi):
            return
        funcion(lo, hi)

    if ax is None:
        return
    if x:
        poner(ax.set_xlim, o.x_min, o.x_max, ax.get_xscale() == "log")
    if y:
        poner(ax.set_ylim, o.y_min, o.y_max, ax.get_yscale() == "log")
    if ax_y2 is not None:
        poner(ax_y2.set_ylim, o.y2_min, o.y2_max, ax_y2.get_yscale() == "log")


def _anotaciones(fig: Figure, ax, o: OpcionesGrafica, c: dict) -> None:
    """Textos libres (posición en fracción de la figura), con flecha opcional hacia
    un punto en coordenadas de los datos. No mueven el resto de la gráfica."""
    for i, a in enumerate(o.anotaciones):
        texto = str(a.get("texto", "")).strip()
        if not texto:
            continue
        pos = (float(a.get("x", 0.5)), float(a.get("y", 0.5)))
        kw = dict(fontsize=a.get("tam") or o.tam_fuente, color=c["texto"], ha="center", va="center", zorder=25)
        flecha = a.get("flecha")
        if ax is not None and flecha is not None:
            nota = ax.annotate(texto, xy=tuple(flecha), xycoords="data", xytext=pos, textcoords="figure fraction",
                               annotation_clip=False,
                               arrowprops=dict(arrowstyle="->", color=c["texto"], linewidth=1, shrinkA=4, shrinkB=2),
                               **kw)
        else:
            nota = fig.text(*pos, texto, **kw)
        nota.set_in_layout(False)
        _registrar(fig, f"nota:{i}", nota, ax)


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
    """Dibuja la escena en ``fig``. Devuelve (ejes principales, ejes secundarios o None, cuadro de resultados).

    Los ejes secundarios son los de residuos, o en «Representar» el eje y derecho
    (o el panel inferior)."""
    fig.clear()
    fig.set_facecolor(c["fondo"])
    fig._ajustelab = {}
    c = dict(c)
    if o.color_datos:
        c["datos"] = o.color_datos
    if o.color_ajuste:
        c["ajuste"] = o.color_ajuste
    if e.especial is not None:
        ax = e.especial.dibujar(fig, o, c, oscuro)
        if ax is not None:
            numericos = getattr(e.especial, "ejes_numericos", ())
            _limites(ax, o, x="x" in numericos, y="y" in numericos)
            _poner_titulo(fig, ax, o, c)
            if ax.name != "polar":
                _decorar_etiquetas(fig, o, ax, ax)
        _anotaciones(fig, ax, o, c)
        return ax, None, None
    if e.series:
        ax, ax2 = _dibujar_series(fig, e, o, c, oscuro)
        _anotaciones(fig, ax, o, c)
        return ax, ax2, None
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
        _dibujar_datos(ax, e, c, o)
        if e.rango is not None:
            _dibujar_rango(ax, e.rango, c)
        if e.previa is not None:
            modelo, p = e.previa
            xx = _malla(e.datos.x, o.log_x, modelo)
            with np.errstate(all="ignore"):
                yy = modelo(xx, *p)
            if np.any(np.isfinite(yy)):
                ax.plot(xx, yy, color=c["ajuste"], linewidth=o.grosor_ajuste * 0.8, linestyle=(0, (5, 3)), alpha=0.85,
                        label="Vista previa (valores iniciales)", zorder=4)
        for i, r in enumerate(e.comparar[:3]):
            xx = _malla(r.datos.x, o.log_x, r.modelo)
            ax.plot(xx, r.evaluar(xx), color=COLORES_COMPARAR[oscuro][i], linewidth=o.grosor_ajuste * 0.9,
                    linestyle=_ESTILOS_COMPARAR[i], label=r.modelo.nombre, zorder=4)
        if e.ajuste is not None:
            _dibujar_ajuste(ax, e.ajuste, e.nivel_banda, e.prediccion, c, o, oscuro)
            if axr is not None:
                _dibujar_residuos(ax, axr, e.ajuste, c, o)
            if o.cuadro_resultados:
                cuadro = ax.annotate(_texto_resultados(e.ajuste, e.coma_decimal), xy=o.pos_cuadro,
                                     xycoords="axes fraction", ha="left", va="bottom", fontsize=o.tam_fuente * 0.85,
                                     color=c["texto"], zorder=10,
                                     bbox=dict(boxstyle="round,pad=0.5", fc=c["ejes"], ec=c["rejilla"], alpha=0.92))
        if e.interpolacion is not None:
            _dibujar_interpolacion(ax, e.interpolacion, c, o)
    _poner_titulo(fig, ax, o, c)
    if o.etiqueta_x:
        (axr or ax).set_xlabel(o.etiqueta_x)
    if o.etiqueta_y:
        ax.set_ylabel(o.etiqueta_y)
    _decorar_etiquetas(fig, o, axr or ax, ax)

    xs = e.datos.x if e.datos is not None else None
    ys = e.datos.y if e.datos is not None else None
    if o.log_x and (xs is None or np.all(xs > 0)):
        ax.set_xscale("log")
    if o.log_y and (ys is None or np.all(ys > 0)):
        ax.set_yscale("log")
    _limites(ax, o)
    handles, labels = ax.get_legend_handles_labels()
    if o.leyenda and len(handles) >= 2:
        _leyenda(ax, handles, labels, o, c)
    _anotaciones(fig, ax, o, c)
    return ax, axr, cuadro


def _leyenda(ax, handles, labels, o: OpcionesGrafica, c, defecto: str = "best"):
    """Leyenda con las opciones (posición, columnas, marco, tamaño y título). Si se
    ha arrastrado, va donde se dejó. Las posiciones «outside …» son de la figura."""
    fig = ax.figure
    automatica = o.loc_leyenda not in LOC_LEYENDA or o.loc_leyenda == "auto"
    loc = defecto if automatica else o.loc_leyenda
    columnas = max(1, int(o.leyenda_columnas))
    marco = o.leyenda_marco
    if automatica and defecto == "outside upper center":  # una fila encima de la gráfica
        columnas = max(columnas, min(4, len(handles)))
        marco = False
    kw = dict(fontsize=o.leyenda_tam, ncols=columnas, frameon=marco, framealpha=0.9, facecolor=c["ejes"],
              edgecolor=c["rejilla"], title=o.titulo_leyenda or None, title_fontsize=o.leyenda_tam)
    pos = o.pos_leyenda
    if pos is not None and len(pos) == 3:
        duenno = fig if pos[2] == "figura" else ax
        ley = duenno.legend(handles, labels, loc=(float(pos[0]), float(pos[1])), **kw)
    elif loc.startswith("outside"):
        duenno = fig
        ley = fig.legend(handles, labels, loc=loc, **kw)
    else:
        duenno = ax
        ley = ax.legend(handles, labels, loc=loc, **kw)
    ley.set_zorder(20)
    for t in ley.get_texts():
        t.set_color(c["texto"])
    ley.get_title().set_color(c["texto"])
    _registrar(fig, "leyenda", ley, None if duenno is fig else ax)
    return ley


def _dibujar_series(fig: Figure, e: Escena, o: OpcionesGrafica, c: dict, oscuro: bool):
    """Series frente a la misma x: eje y izquierdo y derecho, o dos paneles apilados.
    Con cortes, el eje x se parte en tramos (misma escala en todos) separados por «//»."""
    izq = [s for s in e.series if s.eje != "der"]
    der = [s for s in e.series if s.eje == "der"]
    if der and not izq:  # todas en el derecho: no hace falta un segundo eje
        izq, der = der, []
    apilados = e.apilados and bool(der)
    doble_eje = bool(der) and not apilados
    todas_x = np.concatenate([s.x for s in e.series])
    log_x = bool(o.log_x and todas_x.size and np.all(todas_x > 0))
    cortes = fusionar_cortes(e.cortes)
    tramos = tramos_x(todas_x, cortes) if cortes else []
    limites = _limites_tramos(tramos, log_x) if tramos else []
    k = max(1, len(tramos))
    filas = 2 if apilados else 1
    if k > 1:
        f = np.log10 if log_x else (lambda v: v)
        anchos = [float(f(b) - f(a)) for a, b in limites]
        axs = fig.subplots(filas, k, sharex="col", sharey="row", squeeze=False, width_ratios=anchos)
        motor = fig.get_layout_engine()
        if hasattr(motor, "set"):
            motor.set(w_pad=0.02, wspace=0.015)
    else:
        axs = fig.subplots(filas, 1, sharex=True, squeeze=False)
    for a in axs.flat:
        _estilo_ejes(a, c, o)
    gemelos: list = []
    if doble_eje:
        for j in range(k):
            t = axs[0, j].twinx()
            if gemelos:
                t.sharey(gemelos[0])
            _estilo_gemelo(t, c, o)  # una sola rejilla, la del eje izquierdo
            t.spines["top"].set_visible(False)  # ya están las del eje izquierdo
            t.spines["bottom"].set_visible(False)
            axs[0, j].tick_params(axis="y", which="both", right=False)  # el derecho es del otro eje
            gemelos.append(t)
    destinos = {"izq": list(axs[0]), "der": gemelos or (list(axs[1]) if apilados else [])}

    for s in izq + der:
        lado = "der" if s in der else "izq"
        color = s.color_en(oscuro)
        visibles = fuera_de_cortes(s.x, cortes) if cortes else np.ones(s.x.size, bool)
        incl = np.ones(s.x.size, bool) if s.incluidos is None else s.incluidos
        m, m_ex = incl & visibles, ~incl & visibles
        linea = "-" if s.estilo in ("linea", "puntos_linea") else "none"
        marcador = s.marcador if s.estilo in ("puntos", "puntos_linea") else "none"
        etiqueta = s.nombre + ((" (eje dcho.)" if lado == "der" else " (eje izq.)") if doble_eje else "")
        dx = s.dx if e.barras_error else None
        dy = s.dy if e.barras_error else None
        sel = (lambda arr, mask: None if arr is None else arr[mask])
        for j, destino in enumerate(destinos[lado]):
            nombre = etiqueta if j == 0 else "_nolegend_"
            if dx is not None or dy is not None:
                destino.errorbar(s.x[m], s.y[m], xerr=sel(dx, m), yerr=sel(dy, m), color=color, ecolor=color,
                                 linestyle=linea, marker=marcador, ms=o.tam_marcador, linewidth=o.grosor_linea,
                                 elinewidth=o.grosor_error, capsize=o.tam_tapa, label=nombre, zorder=3)
            else:
                destino.plot(s.x[m], s.y[m], color=color, linestyle=linea, marker=marcador, ms=o.tam_marcador,
                             linewidth=o.grosor_linea, label=nombre, zorder=3)
            if np.any(m_ex) and marcador != "none":
                destino.plot(s.x[m_ex], s.y[m_ex], linestyle="none", marker=marcador, ms=o.tam_marcador + 1,
                             mfc="none", mec=color, alpha=0.5, zorder=2)

    def etiqueta_eje(series, propia):
        if propia:
            return propia
        return ", ".join(s.nombre for s in series) if len(series) <= 2 else ""

    ax = axs[0, 0]
    ax2 = gemelos[-1] if gemelos else (axs[1, 0] if apilados else None)
    ax.set_ylabel(etiqueta_eje(izq, o.etiqueta_y))
    if ax2 is not None:
        ax2.set_ylabel(etiqueta_eje(der, o.etiqueta_y2))
    texto_x = o.etiqueta_x or e.nombre_x
    sup_x = None
    if k > 1:
        sup_x = fig.supxlabel(texto_x, color=c["texto"], fontsize=o.tam_fuente)
    else:
        axs[-1, 0].set_xlabel(texto_x)
    if doble_eje:
        # Cada eje y lleva el color de sus series en la línea y las marcas (no en el
        # texto), para que se vea a qué eje pertenece cada una.
        for lado, series, a in (("left", izq, ax), ("right", der, ax2)):
            colores = {s.color_en(oscuro) for s in series}
            if len(colores) == 1:
                color = colores.pop()
                a.spines[lado].set_color(color)
                a.spines[lado].set_linewidth(1.6)
                a.tick_params(axis="y", which="both", color=color, width=1.2)
        for j in range(k):
            gemelos[j].spines["left"].set_visible(False)
            axs[0, j].spines["right"].set_visible(False)

    if log_x:
        for a in axs.flat:
            a.set_xscale("log")
    for j, (lo, hi) in enumerate(limites):
        axs[0, j].set_xlim(lo, hi)
    for grupo, series, log in ((list(axs[0]), izq, o.log_y), (destinos["der"], der, o.log_y2)):
        if grupo and log and series and all(np.all(s.y > 0) for s in series):
            for a in grupo:
                a.set_yscale("log")
    if k > 1:  # tramos: sin líneas ni marcas en los lados interiores
        for j in range(k):
            for r in range(filas):
                a = axs[r, j]
                if j > 0:
                    a.spines["left"].set_visible(False)
                    a.tick_params(axis="y", which="both", left=False, labelleft=False)
                if j < k - 1:
                    a.spines["right"].set_visible(False)
                    a.tick_params(axis="y", which="both", right=False)
            if gemelos and j < k - 1:
                gemelos[j].spines["right"].set_visible(False)
                gemelos[j].tick_params(axis="y", which="both", right=False, labelright=False)
        for r in range(filas):
            for j in range(k - 1):
                _marcas_corte(axs[r, j], axs[r, j + 1], c)
    _poner_titulo(fig, ax, o, c, en_figura=k > 1)
    if k == 1:
        _limites(axs[-1, 0], o, x=True, y=False)
    _limites(ax, o, x=False, y=True, ax_y2=destinos["der"][0] if destinos["der"] else None)
    _decorar_etiquetas(fig, o, axs[-1, 0] if k == 1 else None, ax, ax2, sup_x=sup_x)
    if o.leyenda:
        if doble_eje:
            # «best» solo mira las series de un eje: la leyenda iría encima de las del
            # otro. Por defecto va fuera, sobre la gráfica, en una fila.
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = gemelos[0].get_legend_handles_labels()
            if len(h1) + len(h2) >= 2:
                _leyenda(ax, h1 + h2, l1 + l2, o, c, defecto="outside upper center")
        else:
            for r in range(filas):
                h, l = axs[r, 0].get_legend_handles_labels()
                if len(h) >= 2:
                    _leyenda(axs[r, 0], h, l, o, c)
    fig._ajustelab.update({"ejes": destinos, "limites": limites, "cortes": cortes})
    return ax, ax2


def _dibujar_datos(ax, e: Escena, c, o: OpcionesGrafica, color=None, etiqueta="Datos"):
    d = e.datos
    color = color or c["datos"]
    m = d.incluidos
    dx = d.dx if d.tiene_dx else None
    dy = d.dy
    sel = (lambda arr, mask: None if arr is None else arr[mask])
    if np.any(m):
        ax.errorbar(d.x[m], d.y[m], xerr=sel(dx, m), yerr=sel(dy, m), fmt="o", ms=o.tam_marcador, color=color,
                    ecolor=color, elinewidth=o.grosor_error, capsize=o.tam_tapa, alpha=0.95, label=etiqueta, zorder=3)
    if np.any(~m):
        ax.errorbar(d.x[~m], d.y[~m], xerr=sel(dx, ~m), yerr=sel(dy, ~m), fmt="o", ms=o.tam_marcador + 1,
                    mfc="none", color=c["excluidos"], ecolor=c["excluidos"], elinewidth=o.grosor_error * 0.8,
                    capsize=o.tam_tapa,
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
    ax.plot(xx, f, color=color, linewidth=o.grosor_ajuste, label=f"Ajuste: {r.modelo.nombre}", zorder=5)


def _dibujar_residuos(ax, axr, r: ResultadoAjuste, c, o: OpcionesGrafica):
    rn = r.residuos_norm
    axr.axhline(0, color=c["texto"], linewidth=0.8)
    for k in (-2, 2):
        axr.axhline(k, color=c["rejilla"], linewidth=0.8, linestyle="--")
    axr.plot(r.datos.x, rn, "o", ms=o.tam_marcador * 0.8, color=c["datos"])
    axr.set_ylabel("(y − f)/σ" if r.errores_absolutos else "(y − f)/s", fontsize=o.tam_fuente * 0.9)
    lim = max(3.0, float(np.nanmax(np.abs(rn))) * 1.15) if np.any(np.isfinite(rn)) else 3.0
    axr.set_ylim(-lim, lim)
    axr.set_xlabel(r.datos.nombre_x)
    ax.set_xlabel("")


def _dibujar_interpolacion(ax, f: Interpolacion, c, o):
    lo, hi = f.rango
    xx = np.geomspace(lo, hi, 800) if (o.log_x and lo > 0) else np.linspace(lo, hi, 800)
    ax.plot(xx, f(xx), color=c["interpolacion"], linewidth=o.grosor_ajuste, label=METODOS[f.metodo], zorder=4)


def _dibujar_interseccion(ax, I: Interseccion, c, o):
    for r, color, n in ((I.ajuste1, c["datos"], 1), (I.ajuste2, c["ajuste"], 2)):
        d = r.datos
        ax.errorbar(d.x, d.y, xerr=d.dx if d.tiene_dx else None, yerr=d.dy, fmt="o", ms=o.tam_marcador, color=color,
                    ecolor=color, elinewidth=o.grosor_error, capsize=o.tam_tapa, label=f"Conjunto {n}", zorder=3)
        lo, hi = min(np.min(d.x), I.x), max(np.max(d.x), I.x)
        margen = 0.05 * (hi - lo)
        xx = np.linspace(lo - margen, hi + margen, 400)
        if r.modelo.dominio_valido(xx):
            ax.plot(xx, r.evaluar(xx), color=color, linewidth=o.grosor_ajuste, label=f"Ajuste {n}: {r.modelo.nombre}",
                    zorder=4)
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
        for b in (self.b_region, self.b_rango, self.b_cortar, self.b_personalizar):
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
        if self._herramienta and (sin_ajuste != (self._herramienta == "cortar") or (
                self._herramienta == "cortar" and not modo_xy)):
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
            trozos, indices = [], []
            for k, serie in enumerate(e.series):
                px = np.full((serie.x.size, 2), np.nan)
                for j, (xv, yv) in enumerate(zip(serie.x, serie.y)):
                    ax = self._ejes_de(serie, float(xv))
                    if ax is not None:
                        px[j] = ax.transData.transform((xv, yv))
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
        if self.barra.mode or self._herramienta:
            return
        if evento.button == 3 and not self.escena.vacia:
            self._menu_contextual(evento).exec(QCursor.pos())
            return
        if evento.button != 1:
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
