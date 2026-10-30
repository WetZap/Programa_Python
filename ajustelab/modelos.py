"""Modelos de ajuste definidos a partir de expresiones simbólicas (SymPy).

Cada :class:`Modelo` se construye desde un texto como ``"A*exp(-x/tau) + C"``:

* los parámetros se detectan solos (``A``, ``tau``, ``C``, en orden de aparición);
* SymPy calcula **analíticamente** ∂f/∂x (para la varianza efectiva cuando hay
  errores en x) y el jacobiano ∂f/∂p (para el ajuste y las bandas de confianza);
* se detecta si el modelo es **lineal en los parámetros** (polinomios, a/x + b...),
  en cuyo caso el ajuste se resuelve de forma exacta, sin valores iniciales;
* se genera el LaTeX para la leyenda.

Sintaxis admitida: ``+ - * / ** ^``, paréntesis, números y las funciones
``exp log ln log10 sqrt sin cos tan asin acos atan sinh cosh tanh abs erf``
y las constantes ``pi`` y ``e``. Cualquier otro nombre es un parámetro, salvo la
variable independiente (``x`` por defecto). Nombres como ``gamma``, ``beta``,
``E`` o ``I`` son parámetros normales (no las funciones/constantes de SymPy).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import sympy as sp
from scipy import special
from sympy.parsing.sympy_parser import convert_xor, parse_expr, standard_transformations

__all__ = ["Modelo", "ErrorModelo", "desde_expresion", "polinomio", "CATALOGO", "obtener", "clave_de"]


class ErrorModelo(ValueError):
    """Expresión de modelo no válida."""


_FUNCIONES: dict[str, object] = {
    "exp": sp.exp, "log": sp.log, "ln": sp.log, "log10": lambda z: sp.log(z, 10),
    "sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "arcsin": sp.asin, "arccos": sp.acos, "arctan": sp.atan,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "abs": sp.Abs, "erf": sp.erf, "pi": sp.pi, "e": sp.E,
}
_RE_IDENT = re.compile(r"[^\W\d]\w*")
_RE_PERMITIDOS = re.compile(r"^[\w\s.+\-*/^(),]*$")
_TRANSFORMACIONES = standard_transformations + (convert_xor,)
_MODULOS_NUMPY = [{"erf": special.erf}, "numpy"]


def _difunde(valor, x: np.ndarray) -> np.ndarray:
    """lambdify devuelve un escalar si la expresión no depende de x."""
    return np.broadcast_to(np.asarray(valor, dtype=float), x.shape).astype(float, copy=True)


@dataclass(eq=False)
class Modelo:
    """Modelo y = f(x; p). Se crea con :func:`desde_expresion`."""

    nombre: str
    expresion: str
    parametros: tuple[str, ...]
    variable: str
    simbolica: sp.Expr = field(repr=False)
    latex: str = field(repr=False)
    lineal: bool = False
    descripcion: str = ""
    estimador_p0: Callable[[np.ndarray, np.ndarray], dict | np.ndarray] | None = field(default=None, repr=False)
    dominio: Callable[[np.ndarray], np.ndarray] | None = field(default=None, repr=False)
    plausibilidad: Callable[[dict, np.ndarray], str | None] | None = field(default=None, repr=False)
    fijos: dict[str, float] = field(default_factory=dict)  # parámetros fijados (ver fijar)
    base: "Modelo | None" = field(default=None, repr=False)  # modelo original si hay fijos
    _f: Callable = field(default=None, repr=False)
    _dfdx: Callable = field(default=None, repr=False)
    _dfdp: tuple[Callable, ...] = field(default=(), repr=False)

    # -- evaluación ---------------------------------------------------------
    @property
    def k(self) -> int:
        """Número de parámetros libres."""
        return len(self.parametros)

    def __call__(self, x, *p) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        with np.errstate(all="ignore"):
            return _difunde(self._f(x, *p), x)

    def derivada_x(self, x, p) -> np.ndarray:
        """∂f/∂x evaluada en x."""
        x = np.asarray(x, dtype=float)
        with np.errstate(all="ignore"):
            return _difunde(self._dfdx(x, *p), x)

    def jacobiano(self, x, p) -> np.ndarray:
        """Matriz (n, k) con ∂f/∂p_j en cada x_i."""
        x = np.asarray(x, dtype=float)
        if self.k == 0:
            return np.empty((x.size, 0))
        with np.errstate(all="ignore"):
            return np.column_stack([_difunde(d(x, *p), x).ravel() for d in self._dfdp])

    # -- utilidades para el ajuste -----------------------------------------
    def p0(self, x, y) -> np.ndarray:
        """Valores iniciales: estimador propio del modelo (dict nombre→valor o
        array en el orden de ``parametros``) o, si falla, unos."""
        if self.estimador_p0 is not None:
            try:
                with np.errstate(all="ignore"):
                    est = self.estimador_p0(np.asarray(x, float), np.asarray(y, float))
                if isinstance(est, dict):
                    est = [est[n] for n in self.parametros]
                p = np.asarray(est, dtype=float)
                if p.shape == (self.k,) and np.all(np.isfinite(p)):
                    return p
            except (ValueError, KeyError, IndexError, FloatingPointError, np.linalg.LinAlgError):
                pass
        return np.ones(self.k)

    def comprobar_plausibilidad(self, p, x) -> str | None:
        """Motivo por el que unos parámetros no tienen sentido físico con estos x
        (pico fuera del rango, frecuencia por encima de Nyquist...) o None."""
        if self.plausibilidad is None:
            return None
        return self.plausibilidad(dict(zip(self.parametros, np.asarray(p, float))), np.asarray(x, float))

    @property
    def texto_dominio(self) -> str:
        return getattr(self.dominio, "texto", "dominio restringido") if self.dominio else ""

    def dominio_valido(self, x) -> bool:
        if self.dominio is None:
            return True
        return bool(np.all(self.dominio(np.asarray(x, dtype=float))))

    def latex_ecuacion(self, y: str = "y") -> str:
        return f"{y} = {self.latex}"

    @property
    def original(self) -> "Modelo":
        """El modelo sin parámetros fijados."""
        return self.base if self.base is not None else self

    def fijar(self, valores: dict[str, float] | None) -> "Modelo":
        """Nuevo modelo con algunos parámetros fijados a un valor conocido.

        Se sustituyen en la expresión simbólica, de modo que derivadas, linealidad
        y LaTeX se recalculan solos. El estimador de p0, el dominio y la
        plausibilidad del modelo original se conservan.

        >>> m = obtener("exponencial_fondo").fijar({"C": 0})
        >>> m.parametros
        ('A', 'tau')
        """
        valores = {k: float(v) for k, v in (valores or {}).items()}
        if not valores:
            return self
        desconocidos = set(valores) - set(self.parametros)
        if desconocidos:
            raise ErrorModelo(f"{sorted(desconocidos)} no son parámetros de '{self.nombre}'.")
        if len(valores) == self.k:
            raise ErrorModelo("No se pueden fijar todos los parámetros: no quedaría nada que ajustar.")
        simbolos = {s.name: s for s in self.simbolica.free_symbols}
        expr = self.simbolica.subs({simbolos[k]: v for k, v in valores.items()})
        libres = tuple(n for n in self.parametros if n not in valores)
        xs = simbolos.get(self.variable, sp.Symbol(self.variable, real=True))

        original, nombres, comprobar = self.estimador_p0, self.parametros, self.plausibilidad
        todos = {**self.fijos, **valores}

        def _estimador(x, y):
            r = original(x, y)
            if isinstance(r, dict):
                return {k: r[k] for k in libres}
            return np.asarray(r, dtype=float)[[nombres.index(k) for k in libres]]

        def _plausibilidad(p, x):
            return comprobar({**p, **todos}, x)

        estimador = _estimador if original is not None else None
        plausibilidad = _plausibilidad if comprobar is not None else None

        base = self.original
        fijos = {**self.fijos, **valores}
        texto = ", ".join(f"{k} = {v:g}" for k, v in fijos.items())
        m = _construir(expr, xs, [simbolos[n] for n in libres], nombre=f"{base.nombre} ({texto})",
                       expresion=base.expresion, variable=self.variable, descripcion=base.descripcion,
                       p0=estimador, dominio=self.dominio, plausibilidad=plausibilidad)
        m.fijos = fijos
        m.base = base
        return m

    def __repr__(self) -> str:
        tipo = "lineal en p" if self.lineal else "no lineal"
        return f"Modelo('{self.nombre}': y = {self.expresion}; parámetros {self.parametros}; {tipo})"


def desde_expresion(
    expresion: str,
    nombre: str | None = None,
    *,
    variable: str = "x",
    parametros: tuple[str, ...] | list[str] | None = None,
    p0: Callable[[np.ndarray, np.ndarray], dict | np.ndarray] | None = None,
    dominio: Callable[[np.ndarray], np.ndarray] | None = None,
    plausibilidad: Callable[[dict, np.ndarray], str | None] | None = None,
    descripcion: str = "",
) -> Modelo:
    """Crea un :class:`Modelo` a partir de un texto.

    >>> m = desde_expresion("A*exp(-x/tau) + C")
    >>> m.parametros
    ('A', 'tau', 'C')
    """
    texto = expresion.strip()
    if not texto:
        raise ErrorModelo("La expresión está vacía.")
    if not _RE_PERMITIDOS.match(texto) or "__" in texto or re.search(r"\.\s*[^\W\d]", texto):
        raise ErrorModelo("La expresión contiene caracteres no permitidos.")

    nombres = list(dict.fromkeys(_RE_IDENT.findall(texto)))  # orden de aparición, sin repetir
    simbolos = {n: sp.Symbol(n, real=True) for n in nombres if n not in _FUNCIONES}
    if variable not in simbolos:
        simbolos[variable] = sp.Symbol(variable, real=True)
    try:
        expr = parse_expr(texto, local_dict={**_FUNCIONES, **simbolos}, transformations=_TRANSFORMACIONES)
    except Exception as e:  # SyntaxError, TokenError, TypeError...
        raise ErrorModelo(f"No se puede interpretar '{texto}': {e}") from e
    if not isinstance(expr, sp.Expr):
        raise ErrorModelo(f"'{texto}' no es una expresión matemática.")

    xs = simbolos[variable]
    detectados = tuple(n for n in nombres if n in simbolos and n != variable and simbolos[n] in expr.free_symbols)
    if parametros is None:
        parametros = detectados
    else:
        parametros = tuple(parametros)
        if set(parametros) != set(detectados):
            raise ErrorModelo(f"Parámetros indicados {parametros} ≠ detectados {detectados}.")
    ps = [simbolos[n] for n in parametros]
    sobrantes = expr.free_symbols - set(ps) - {xs}
    if sobrantes:
        raise ErrorModelo(f"Símbolos sin asignar: {sobrantes}.")

    return _construir(expr, xs, ps, nombre=nombre or "Personalizado", expresion=texto, variable=variable,
                      descripcion=descripcion, p0=p0, dominio=dominio, plausibilidad=plausibilidad)


def _construir(expr, xs, ps, *, nombre, expresion, variable, descripcion="", p0=None, dominio=None,
               plausibilidad=None) -> Modelo:
    """Modelo a partir de una expresión SymPy ya interpretada."""
    derivadas = [sp.diff(expr, p) for p in ps]
    # Lineal en p ⇔ todas las segundas derivadas respecto a los parámetros son 0
    # (expand basta para los casos reales y es mucho más rápido que simplify).
    lineal = all(sp.expand(sp.diff(d, q)) == 0 for d in derivadas for q in ps)
    args = [xs, *ps]
    return Modelo(
        nombre=nombre,
        expresion=expresion,
        parametros=tuple(p.name for p in ps),
        variable=variable,
        simbolica=expr,
        latex=sp.latex(expr),
        lineal=lineal,
        descripcion=descripcion,
        estimador_p0=p0,
        dominio=dominio,
        plausibilidad=plausibilidad,
        _f=sp.lambdify(args, expr, modules=_MODULOS_NUMPY),
        _dfdx=sp.lambdify(args, sp.diff(expr, xs), modules=_MODULOS_NUMPY),
        _dfdp=tuple(sp.lambdify(args, d, modules=_MODULOS_NUMPY) for d in derivadas),
    )




# ---------------------------------------------------------------------------
# Estimadores de valores iniciales
# ---------------------------------------------------------------------------
# Casi todos los modelos del catálogo son lineales en todos sus parámetros salvo
# uno o dos (τ, ω, b...). Para ellos se usa "proyección variable": se recorre una
# rejilla del parámetro no lineal θ y, para cada θ, los lineales se obtienen por
# mínimos cuadrados exactos; se queda el θ con menor RSS y se refina la rejilla.
# Así el p0 está casi siempre en la cuenca del mínimo global.

def _ordenados(x, y):
    o = np.argsort(x, kind="stable")
    return x[o], y[o]


def _escanear(y, base, thetas):
    """Mejor θ de la rejilla para y ≈ base(θ) @ c. Devuelve (θ, c) refinado."""
    def evaluar(th):
        B = base(th)
        if not np.all(np.isfinite(B)):
            return np.inf, None
        c, *_ = np.linalg.lstsq(B, y, rcond=None)
        return float(np.sum((B @ c - y) ** 2)), c

    thetas = list(thetas)
    rss = [evaluar(th)[0] for th in thetas]
    i = int(np.argmin(rss))
    if not np.isfinite(rss[i]):
        raise ValueError("Escaneo sin solución finita.")
    a = thetas[max(i - 1, 0)]
    b = thetas[min(i + 1, len(thetas) - 1)]
    finos = np.linspace(a, b, 41) if np.ndim(a) == 0 else [thetas[i]]
    mejor = min(((evaluar(th), th) for th in finos), key=lambda t: t[0][0])
    (_, c), th = mejor
    return th, c


def _tasas(x):
    """Rejilla de tasas r (1/τ) con r·Δx entre 0.05 y 30, ambos signos."""
    dx = np.ptp(x) or 1.0
    r = np.geomspace(0.05, 30, 45) / dx
    return np.concatenate([-r[::-1], r])


def _signo_dominante(y):
    return 1.0 if np.sum(y > 0) >= np.sum(y < 0) else -1.0


def _p0_exponencial(x, y):
    """A·exp(b·x): ajuste lineal de ln|y| frente a x."""
    s = _signo_dominante(y)
    m = s * y > 0
    if m.sum() < 2 or np.ptp(x[m]) == 0:
        return {"A": np.mean(y), "b": 0.0}
    b, lnA = np.polyfit(x[m], np.log(s * y[m]), 1)
    return {"A": s * np.exp(lnA), "b": b}


def _p0_exponencial_fondo(x, y):
    """A·exp(−x/τ) + C por escaneo de r = 1/τ."""
    x, y = _ordenados(x, y)
    x0 = x[0]
    r, (a, C) = _escanear(y, lambda r: np.column_stack([np.exp(-r * (x - x0)), np.ones_like(x)]), _tasas(x))
    return {"A": a * np.exp(r * x0), "tau": 1 / r, "C": C}


def _p0_carga(x, y):
    """A·(1 − exp(−x/τ)) + C = (A + C) − A·exp(−x/τ)."""
    p = _p0_exponencial_fondo(x, y)
    return {"A": -p["A"], "tau": p["tau"], "C": p["C"] + p["A"]}


def _p0_doble_exponencial(x, y):
    x, y = _ordenados(x, y)
    x0 = x[0]
    r = np.geomspace(0.05, 30, 22) / (np.ptp(x) or 1.0)
    pares = [(r1, r2) for i, r1 in enumerate(r) for r2 in r[i + 1:] if r2 / r1 > 1.5]
    (r1, r2), (a1, a2, C) = _escanear(
        y, lambda t: np.column_stack([np.exp(-t[0] * (x - x0)), np.exp(-t[1] * (x - x0)), np.ones_like(x)]), pares)
    # Convenio: t1 es el tiempo rápido (r2 > r1 ⇒ 1/r2 < 1/r1)
    return {"A1": a2 * np.exp(r2 * x0), "t1": 1 / r2, "A2": a1 * np.exp(r1 * x0), "t2": 1 / r1, "C": C}


def _p0_potencia(x, y):
    """A·x^b: ajuste lineal de ln|y| frente a ln x."""
    s = _signo_dominante(y)
    m = (x > 0) & (s * y > 0)
    if m.sum() < 2 or np.ptp(x[m]) == 0:
        return {"A": np.mean(y), "b": 1.0}
    b, lnA = np.polyfit(np.log(x[m]), np.log(s * y[m]), 1)
    return {"A": s * np.exp(lnA), "b": b}


def _p0_potencia_fondo(x, y):
    bs = np.concatenate([np.linspace(-4, -0.05, 40), np.linspace(0.05, 4, 40)])
    b, (A, C) = _escanear(y, lambda b: np.column_stack([x**b, np.ones_like(x)]), bs)
    return {"A": A, "b": b, "C": C}


def _p0_arrhenius(x, y):
    """A·exp(−b/x): ln|y| = ln A − b·(1/x)."""
    s = _signo_dominante(y)
    m = (x != 0) & (s * y > 0)
    pend, lnA = np.polyfit(1 / x[m], np.log(s * y[m]), 1)
    return {"A": s * np.exp(lnA), "b": -pend}


def _pico(x, y):
    """(fondo, altura con signo, centro, FWHM) de un pico o valle."""
    x, y = _ordenados(x, y)
    borde = max(2, x.size // 5)
    C = float(np.median(np.concatenate([y[:borde], y[-borde:]])))
    dev = y - C
    i = int(np.argmax(np.abs(dev)))
    A = float(dev[i])
    dentro = np.sign(A) * dev >= abs(A) / 2
    izq, der = i, i
    while izq > 0 and dentro[izq - 1]:
        izq -= 1
    while der < x.size - 1 and dentro[der + 1]:
        der += 1
    paso = float(np.min(np.diff(x))) if x.size > 1 else 1.0
    fwhm = max(float(x[der] - x[izq]), paso)
    return C, A, float(x[i]), fwhm


def _p0_gaussiana(x, y):
    C, A, mu, fwhm = _pico(x, y)
    return {"A": A, "mu": mu, "s": fwhm / 2.3548, "C": C}


def _p0_lorentziana(x, y):
    C, A, x0, fwhm = _pico(x, y)
    return {"A": A, "g": fwhm / 2, "x0": x0, "C": C}


def _omegas(x):
    """Rejilla de ω entre medio periodo en el rango y el límite de Nyquist."""
    x = np.sort(x)
    rango = np.ptp(x) or 1.0
    paso = np.median(np.diff(x)) if x.size > 1 else rango
    return np.geomspace(np.pi / rango, np.pi / paso, 300)


def _p0_seno(x, y):
    """A·sin(ωx + φ) + C:  a·sin(ωx) + b·cos(ωx) + C con A cosφ = a, A sinφ = b."""
    w, (a, b, C) = _escanear(y, lambda w: np.column_stack([np.sin(w * x), np.cos(w * x), np.ones_like(x)]), _omegas(x))
    return {"A": np.hypot(a, b), "w": w, "phi": np.arctan2(b, a), "C": C}


def _p0_seno_amortiguado(x, y):
    w = _p0_seno(x, y)["w"]
    x0 = np.min(x)
    gs = np.concatenate([[0.0], np.geomspace(0.01, 10, 40) / (np.ptp(x) or 1.0)])

    def base(g):
        e = np.exp(-g * (x - x0))
        return np.column_stack([e * np.sin(w * x), e * np.cos(w * x), np.ones_like(x)])

    g, (a, b, C) = _escanear(y, base, gs)
    return {"A": np.hypot(a, b) * np.exp(g * x0), "g": g, "w": w, "phi": np.arctan2(b, a), "C": C}


def _p0_logistica(x, y):
    """L/(1 + exp(−k(x − x0))) + C: x0 donde y cruza la mitad, k por escaneo."""
    xs, ys = _ordenados(x, y)
    borde = max(2, xs.size // 5)
    ini, fin = np.mean(ys[:borde]), np.mean(ys[-borde:])
    medio = (ini + fin) / 2
    cruces = np.flatnonzero(np.diff(np.sign(ys - medio)) != 0)
    x0 = float(xs[cruces[0]]) if cruces.size else float(np.median(xs))
    ks = np.geomspace(0.5, 60, 50) / (np.ptp(xs) or 1.0)
    k, (L, C) = _escanear(ys, lambda k: np.column_stack([1 / (1 + np.exp(-k * (xs - x0))), np.ones_like(xs)]), ks)
    return {"L": L, "k": k, "x0": x0, "C": C}


def _p0_malus(grados: bool):
    def estimar(x, y):
        xr = np.deg2rad(x) if grados else x
        # I0·cos²(x − t0) + C = (C + I0/2) + (I0/2)·cos(2x − 2t0)
        B = np.column_stack([np.cos(2 * xr), np.sin(2 * xr), np.ones_like(xr)])
        (a, b, c), *_ = np.linalg.lstsq(B, y, rcond=None)
        mitad = np.hypot(a, b)
        t0 = np.arctan2(b, a) / 2
        return {"I0": 2 * mitad, "t0": np.rad2deg(t0) if grados else t0, "C": c - mitad}
    return estimar


# ---------------------------------------------------------------------------
# Plausibilidad física de los parámetros ajustados
# ---------------------------------------------------------------------------
def _dominio(texto: str, condicion):
    condicion.texto = texto
    return condicion


_x_positivo = _dominio("requiere x > 0", lambda x: x > 0)
_x_no_negativo = _dominio("requiere x ≥ 0", lambda x: x >= 0)
_x_no_nulo = _dominio("requiere x ≠ 0", lambda x: x != 0)


def _plaus_pico(centro: str, ancho: str, factor: float):
    def comprobar(p, x):
        lo, hi = np.min(x), np.max(x)
        w = abs(p[ancho]) * factor  # FWHM
        if not lo <= p[centro] <= hi:
            return f"centro del pico ({centro} = {p[centro]:.4g}) fuera del rango de x"
        if w > 2 * (hi - lo):
            return "pico más ancho que el doble del rango de x (no se ve el pico)"
        paso = np.min(np.diff(np.unique(x))) if np.unique(x).size > 1 else 0
        if w < paso:
            return "pico más estrecho que la separación entre puntos"
        return None
    return comprobar


def _plaus_oscilacion(p, x):
    xs = np.unique(x)
    w = abs(p["w"])
    if w * np.ptp(xs) < np.pi:
        return "menos de medio periodo dentro del rango: no hay oscilación observable"
    if xs.size > 1 and w > np.pi / np.min(np.diff(xs)):
        return "frecuencia por encima del límite de Nyquist del muestreo"
    return None


def _plaus_logistica(p, x):
    lo, hi = np.min(x), np.max(x)
    if not lo <= p["x0"] <= hi:
        return "punto medio de la sigmoide fuera del rango de x"
    if abs(p["k"]) * (hi - lo) < 4:
        return "transición demasiado suave: la sigmoide no se completa en el rango"
    return None


def _plaus_doble_exp(p, x):
    if p["t1"] <= 0 or p["t2"] <= 0:
        return "tiempos característicos no positivos"
    if p["t1"] > p["t2"]:
        return "t1 > t2 (por convenio t1 es el tiempo rápido; intercambia las etiquetas)"
    if max(p["t1"], p["t2"]) / min(p["t1"], p["t2"]) < 1.2:
        return "los dos tiempos característicos son prácticamente iguales"
    return None


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def polinomio(grado: int) -> Modelo:
    """Polinomio c0 + c1·x + ... + cn·x^n."""
    if grado < 0:
        raise ErrorModelo("El grado debe ser ≥ 0.")
    terminos = " + ".join(["c0"] + [f"c{i}*x**{i}" if i > 1 else "c1*x" for i in range(1, grado + 1)])
    return desde_expresion(terminos, f"Polinomio de grado {grado}", descripcion="Lineal en los parámetros.")


# (clave, expresión, nombre, opciones)
_DEFINICIONES = [
    # --- lineales en los parámetros (solución exacta) ---
    ("constante", "c", "Constante", dict(descripcion="Sin dependencia con x.")),
    ("proporcional", "a*x", "Proporcional", dict(descripcion="Recta por el origen.")),
    ("lineal", "a*x + b", "Lineal", dict(descripcion="Recta con ordenada en el origen.")),
    ("cuadratico", "a*x**2 + b*x + c", "Cuadrático", {}),
    ("inversa", "a/x + b", "Inversa", dict(dominio=_x_no_nulo)),
    ("inversa_cuadrado", "a/x**2 + b", "Inversa del cuadrado", dict(dominio=_x_no_nulo)),
    ("raiz", "a*sqrt(x) + b", "Raíz cuadrada", dict(dominio=_x_no_negativo)),
    ("logaritmica", "a*log(x) + b", "Logarítmica", dict(dominio=_x_positivo)),
    # --- exponenciales ---
    ("exponencial", "A*exp(b*x)", "Exponencial",
     dict(p0=_p0_exponencial, descripcion="Crecimiento (b > 0) o decaimiento (b < 0) sin fondo.")),
    ("exponencial_fondo", "A*exp(-x/tau) + C", "Exponencial con fondo",
     dict(p0=_p0_exponencial_fondo, descripcion="Decaimiento con asíntota C (τ < 0: crecimiento).")),
    ("carga", "A*(1 - exp(-x/tau)) + C", "Carga (1 − e^{−x/τ})",
     dict(p0=_p0_carga, descripcion="Carga de un condensador. Equivale a la exponencial con fondo.")),
    ("doble_exponencial", "A1*exp(-x/t1) + A2*exp(-x/t2) + C", "Doble exponencial",
     dict(p0=_p0_doble_exponencial, plausibilidad=_plaus_doble_exp,
          descripcion="Dos tiempos característicos; convenio t1 < t2.")),
    ("arrhenius", "A*exp(-b/x)", "Arrhenius",
     dict(p0=_p0_arrhenius, dominio=_x_no_nulo, descripcion="A·exp(−b/x), p. ej. b = Eₐ/k_B con x = T.")),
    # --- potencias ---
    ("potencia", "A*x**b", "Potencia", dict(p0=_p0_potencia, dominio=_x_positivo)),
    ("potencia_fondo", "A*x**b + C", "Potencia con fondo",
     dict(p0=_p0_potencia_fondo, dominio=_x_positivo)),
    # --- picos ---
    ("gaussiana", "A*exp(-(x - mu)**2/(2*s**2)) + C", "Gaussiana",
     dict(p0=_p0_gaussiana, plausibilidad=_plaus_pico("mu", "s", 2.3548),
          descripcion="A altura, μ centro, s desviación típica (FWHM = 2.355 s), C fondo.")),
    ("lorentziana", "A*g**2/((x - x0)**2 + g**2) + C", "Lorentziana",
     dict(p0=_p0_lorentziana, plausibilidad=_plaus_pico("x0", "g", 2.0),
          descripcion="Resonancia: A altura, x0 centro, g semianchura (FWHM = 2g), C fondo.")),
    # --- sigmoide y oscilaciones ---
    ("logistica", "L/(1 + exp(-k*(x - x0))) + C", "Logística (sigmoide)",
     dict(p0=_p0_logistica, plausibilidad=_plaus_logistica, descripcion="Transición de C a C + L centrada en x0.")),
    ("seno", "A*sin(w*x + phi) + C", "Sinusoidal",
     dict(p0=_p0_seno, plausibilidad=_plaus_oscilacion, descripcion="ω en rad por unidad de x.")),
    ("seno_amortiguado", "A*exp(-g*x)*sin(w*x + phi) + C", "Oscilación amortiguada",
     dict(p0=_p0_seno_amortiguado, plausibilidad=_plaus_oscilacion, descripcion="g tasa de amortiguamiento.")),
    ("malus", "I0*cos(x - t0)**2 + C", "Ley de Malus (rad)",
     dict(p0=_p0_malus(False), descripcion="Polarizadores, ángulo en radianes.")),
    ("malus_grados", "I0*cos(pi*(x - t0)/180)**2 + C", "Ley de Malus (grados)",
     dict(p0=_p0_malus(True), descripcion="Polarizadores, ángulo en grados.")),
]


def _construir_catalogo() -> dict[str, Modelo]:
    catalogo = {clave: desde_expresion(expr, nombre, **opciones) for clave, expr, nombre, opciones in _DEFINICIONES}
    catalogo["cubico"] = polinomio(3)
    return catalogo


CATALOGO: dict[str, Modelo] = _construir_catalogo()


def obtener(clave_o_expresion: str) -> Modelo:
    """Devuelve un modelo del catálogo por clave, o lo crea desde una expresión."""
    clave = clave_o_expresion.strip().lower()
    if clave in CATALOGO:
        return CATALOGO[clave]
    m = re.fullmatch(r"polinomio_?(\d+)", clave)
    if m:
        return polinomio(int(m.group(1)))
    return desde_expresion(clave_o_expresion)


def clave_de(modelo: Modelo) -> str | None:
    """Clave del catálogo de un modelo (o None si es personalizado)."""
    return next((k for k, m in CATALOGO.items() if m is modelo), None)
