"""Dibujo de las gráficas (matplotlib puro, sin Qt).

* :func:`dibujar` pinta una :class:`Escena` con unas :class:`OpcionesGrafica` en
  cualquier ``Figure``: el widget de la ventana (:mod:`ajustelab.gui.lienzo`) y la
  exportación (otro tamaño, estilo de publicación) usan exactamente este código.
* Ajuste: datos con barras de error, curva, banda de confianza o predicción,
  residuos, cuadro de resultados, vista previa y comparación de modelos.
* «Representar» (sin ajuste): varias series frente a una misma x, en el eje
  izquierdo o en el derecho (o en dos paneles apilados), y el eje x partido
  (cortes «//»). Los demás tipos (histograma, barras, sectores, cajas, polar)
  están en :mod:`ajustelab.gui.graficas` y llegan en ``Escena.especial``.
* Personalización (``OpcionesGrafica``): textos y su posición, leyenda, ejes
  (límites, marcas, notación), tamaños y colores, textos libres, marcas de puntos
  y tramos, y plantillas de estilo. Los elementos que el usuario puede arrastrar o
  señalar se apuntan en ``fig._ajustelab`` para el widget.
* Con decenas de miles de puntos, las barras de error se dibujan como una sola
  línea (:func:`_errorbar`): matplotlib crearía un objeto por barra.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse

from ..ajuste import ResultadoAjuste
from ..datos import Datos
from ..estadistica import formatear
from ..interpolacion import METODOS, Interpolacion
from ..interseccion import Interseccion
from ..modelos import Modelo


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

# Marcas para señalar puntos, tramos o valores en la gráfica (OpcionesGrafica.destacados)
TIPOS_MARCA = {"punto": "Punto", "tramo": "Tramo de x", "vertical": "Línea vertical",
               "horizontal": "Línea horizontal"}
FORMAS_MARCA = {"o": "Círculo", "s": "Cuadrado", "D": "Rombo", "^": "Triángulo", "v": "Triángulo hacia abajo",
                "*": "Estrella", "P": "Cruz", "X": "Aspa"}
ESTILOS_LINEA = {"--": "Discontinua", "-": "Continua", ":": "Punteada", "-.": "Raya y punto"}
MARCA_DEFECTO = {"tipo": "punto", "x": 0.0, "y": 0.0, "x2": 1.0, "texto": "", "color": "", "forma": "o",
                 "tam": 14.0, "relleno": False, "estilo": "--", "grosor": 1.5, "alfa": 0.15, "leyenda": False,
                 "eje": "izq"}
COLOR_MARCA = {False: "#d6336c", True: "#ff6b9a"}  # por defecto (claro, oscuro): destaca sobre la paleta

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
    # Marcas en coordenadas de los datos (punto, tramo de x, línea vertical u horizontal): ver MARCA_DEFECTO
    destacados: list = field(default_factory=list)

    def a_dict(self) -> dict:
        d = dict(self.__dict__)
        d["anotaciones"] = [dict(a) for a in self.anotaciones]
        d["destacados"] = [dict(m) for m in self.destacados]
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
            elif k == "destacados":
                v = [{**MARCA_DEFECTO, **m} for m in (v or []) if isinstance(m, dict) and m.get("tipo") in TIPOS_MARCA]
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
        self.destacados = []

    def escalada(self, tam_fuente: float) -> "OpcionesGrafica":
        """Copia con otro tamaño de letra; los tamaños propios (título, leyenda,
        anotaciones) cambian en la misma proporción."""
        f = tam_fuente / self.tam_fuente if self.tam_fuente else 1.0
        o = replace(self, tam_fuente=tam_fuente, tam_titulo=self.tam_titulo * f, tam_leyenda=self.tam_leyenda * f)
        o.anotaciones = [{**a, "tam": (a.get("tam") or 0) * f} for a in self.anotaciones]
        o.destacados = [dict(m) for m in self.destacados]
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


def _destacados(fig: Figure, o: OpcionesGrafica, c: dict, oscuro: bool, izq: list, der: list | None = None,
                solo_puntos: bool = False) -> None:
    """Marcas del usuario (puntos, tramos de x y líneas) en coordenadas de los datos.
    ``izq``/``der``: ejes donde se dibujan (con el eje partido, uno por tramo); el
    texto de un punto solo sale en los ejes que lo contienen."""
    if not o.destacados or not izq:
        return
    lista = fig._ajustelab.setdefault("destacados", [])
    for i, bruto in enumerate(o.destacados):
        m = {**MARCA_DEFECTO, **bruto}
        tipo = m["tipo"]
        if solo_puntos and tipo != "punto":
            continue
        color = m["color"] or c.get("destacado") or COLOR_MARCA[oscuro]
        texto = str(m["texto"] or "").strip()
        en_leyenda = bool(m["leyenda"] and texto)
        destinos = der if (m["eje"] == "der" and der) else izq
        try:
            x, y, x2 = float(m["x"]), (None if m["y"] is None else float(m["y"])), float(m["x2"])
        except (TypeError, ValueError):
            continue
        for j, ax in enumerate(destinos):
            etiqueta = texto if (en_leyenda and j == 0) else "_nolegend_"
            kw_texto = dict(color=c["texto"], fontsize=o.tam_fuente * 0.9, zorder=7, clip_on=True)
            if tipo == "punto" and y is not None:
                (art,) = ax.plot([x], [y], linestyle="none", marker=m["forma"], ms=m["tam"], mew=2,
                                 mfc=color if m["relleno"] else "none", mec=color, label=etiqueta, zorder=6)
                art.set_pickradius(m["tam"] * 0.5 + 3)  # se coge haciendo clic en todo el aro
                if texto and not en_leyenda:
                    ax.annotate(texto, (x, y), xytext=(m["tam"] * 0.6 + 2, m["tam"] * 0.6 + 2),
                                textcoords="offset points", **kw_texto)
            elif tipo == "tramo":
                art = ax.axvspan(min(x, x2), max(x, x2), color=color, alpha=m["alfa"], linewidth=0, label=etiqueta,
                                 zorder=0.5)
                if texto and not en_leyenda:
                    ax.text((x + x2) / 2, 0.98, texto, transform=ax.get_xaxis_transform(), ha="center", va="top",
                            **kw_texto)
            elif tipo == "vertical":
                art = ax.axvline(x, color=color, linestyle=m["estilo"], linewidth=m["grosor"], label=etiqueta,
                                 zorder=4)
                if texto and not en_leyenda:
                    ax.text(x, 0.98, f" {texto}", transform=ax.get_xaxis_transform(), ha="left", va="top",
                            **kw_texto)
            elif tipo == "horizontal" and y is not None:
                art = ax.axhline(y, color=color, linestyle=m["estilo"], linewidth=m["grosor"], label=etiqueta,
                                 zorder=4)
                if texto and not en_leyenda:
                    ax.text(0.99, y, texto, transform=ax.get_yaxis_transform(), ha="right", va="bottom", **kw_texto)
            else:
                continue
            lista.append((i, art))


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
            if ax.name == "polar" or numericos:  # en sectores no hay coordenadas que señalar
                _destacados(fig, o, c, oscuro, [ax], solo_puntos=ax.name == "polar")
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
    _destacados(fig, o, c, oscuro, [ax])
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
                _errorbar(destino, s.x[m], s.y[m], xerr=sel(dx, m), yerr=sel(dy, m), color=color, ecolor=color,
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
    _destacados(fig, o, c, oscuro, destinos["izq"], destinos["der"])
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


MUCHOS_PUNTOS = 3000  # a partir de aquí, barras de error rápidas (sin topes)


def _errorbar(ax, x, y, xerr=None, yerr=None, *, fmt=None, color=None, ecolor=None, linestyle=None, marker=None,
              ms=5.0, linewidth=1.6, elinewidth=1.0, capsize=2.0, label=None, zorder=3, alpha=None, mfc=None):
    """``ax.errorbar`` con pocos puntos. Con muchos (decenas de miles), matplotlib crea
    un objeto por barra y tarda segundos; aquí todas las barras son una sola línea
    con cortes (NaN) y los topes se omiten (con tantos puntos no se distinguirían)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.size <= MUCHOS_PUNTOS:
        kw = dict(color=color, ecolor=ecolor, ms=ms, linewidth=linewidth, elinewidth=elinewidth, capsize=capsize,
                  label=label, zorder=zorder, alpha=alpha)
        if fmt is not None:
            kw["fmt"] = fmt
        else:
            kw.update(linestyle=linestyle, marker=marker)
        if mfc is not None:
            kw["mfc"] = mfc
        return ax.errorbar(x, y, xerr=xerr, yerr=yerr, **kw)
    if fmt == "o":
        marker, linestyle = "o", "none"
    nan = np.full(x.size, np.nan)
    for err, vertical in ((yerr, True), (xerr, False)):
        if err is None:
            continue
        e = np.broadcast_to(np.abs(np.asarray(err, float)), x.shape)
        if vertical:
            xs, ys = np.column_stack([x, x, nan]).ravel(), np.column_stack([y - e, y + e, nan]).ravel()
        else:
            xs, ys = np.column_stack([x - e, x + e, nan]).ravel(), np.column_stack([y, y, nan]).ravel()
        ax.plot(xs, ys, color=ecolor or color, linewidth=elinewidth, alpha=alpha, zorder=zorder - 0.1,
                label="_nolegend_")
    kw = {} if mfc is None else {"mfc": mfc}
    (linea,) = ax.plot(x, y, color=color, linestyle=linestyle or "none", marker=marker or "none", ms=ms,
                       linewidth=linewidth, label=label, zorder=zorder, alpha=alpha, **kw)
    return linea


def _dibujar_datos(ax, e: Escena, c, o: OpcionesGrafica, color=None, etiqueta="Datos"):
    d = e.datos
    color = color or c["datos"]
    m = d.incluidos
    dx = d.dx if d.tiene_dx else None
    dy = d.dy
    sel = (lambda arr, mask: None if arr is None else arr[mask])
    if np.any(m):
        _errorbar(ax, d.x[m], d.y[m], xerr=sel(dx, m), yerr=sel(dy, m), fmt="o", ms=o.tam_marcador, color=color,
                  ecolor=color, elinewidth=o.grosor_error, capsize=o.tam_tapa, alpha=0.95, label=etiqueta, zorder=3)
    if np.any(~m):
        _errorbar(ax, d.x[~m], d.y[~m], xerr=sel(dx, ~m), yerr=sel(dy, ~m), fmt="o", ms=o.tam_marcador + 1,
                  mfc="none", color=c["excluidos"], ecolor=c["excluidos"], elinewidth=o.grosor_error * 0.8,
                  capsize=o.tam_tapa, label="Excluidos / fuera de rango", zorder=2)
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
        _errorbar(ax, d.x, d.y, xerr=d.dx if d.tiene_dx else None, yerr=d.dy, fmt="o", ms=o.tam_marcador,
                  color=color, ecolor=color, elinewidth=o.grosor_error, capsize=o.tam_tapa, label=f"Conjunto {n}",
                  zorder=3)
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


def __getattr__(nombre: str):
    """Compatibilidad: el widget ``Grafica`` vive ahora en :mod:`ajustelab.gui.lienzo`."""
    if nombre in ("Grafica", "BarraNavegacion"):
        from . import lienzo

        return getattr(lienzo, nombre)
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
