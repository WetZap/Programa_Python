"""Histogramas con estadística: elección de intervalos, errores de Poisson y
ajuste de distribuciones por máxima verosimilitud con test χ² de Pearson.

Resumen de criterios
--------------------
* Intervalos (bins) de igual anchura. Reglas: Freedman–Diaconis
  (h = 2·IQR·n^(−1/3), robusta frente a colas y valores atípicos; la de por defecto),
  Scott (h = 3.49·s·n^(−1/3), óptima para datos normales), Sturges
  (k = ⌈log₂ n⌉ + 1, solo razonable con n pequeño y datos normales) y √n.
  También número fijo de intervalos o anchura fija (bordes en múltiplos de la anchura).
* Datos enteros (cuentas): los intervalos se centran en los enteros (bordes en
  k ± ½) con anchura entera, para que cada valor caiga en un único intervalo.
* Error de cada intervalo: √N (Poisson). Con N = 0 el error es 0: la barra no
  significa «sin incertidumbre», sino que √N deja de ser buena aproximación.
* Ajustes por máxima verosimilitud sobre los datos sin agrupar (no sobre el
  histograma, que perdería información y depende de los intervalos):
  normal (μ, σ), Poisson (λ) y exponencial (τ = 1/λ).
* Test χ² de Pearson: los intervalos de los extremos se extienden hasta el
  final del soporte de la distribución y se agrupan intervalos vecinos hasta que
  cada uno espera al menos 5 entradas. ν = k − 1 − (parámetros estimados).
  Estimar los parámetros con los datos sin agrupar hace que el p-valor sea
  ligeramente optimista (Chernoff–Lehmann); con muchos intervalos la diferencia
  es pequeña.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy import stats

__all__ = [
    "REGLAS",
    "NORMALIZACIONES",
    "DISTRIBUCIONES",
    "ErrorHistograma",
    "Histograma",
    "AjusteHistograma",
    "Resumen",
    "bordes",
    "histograma",
    "ajustar_distribucion",
    "resumen",
]

REGLAS = {
    "fd": "Freedman–Diaconis",
    "scott": "Scott",
    "sturges": "Sturges",
    "raiz": "√n",
}
NORMALIZACIONES = {
    "cuentas": "Cuentas",
    "relativa": "Frecuencia relativa",
    "densidad": "Densidad de probabilidad",
}
DISTRIBUCIONES = {
    "normal": "Normal (gaussiana)",
    "poisson": "Poisson",
    "exponencial": "Exponencial",
}
MAX_INTERVALOS = 500
ESPERADAS_MIN = 5.0


class ErrorHistograma(ValueError):
    """Datos o parámetros que no permiten construir el histograma o el ajuste."""


def _limpiar(x) -> np.ndarray:
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]
    if x.size == 0:
        raise ErrorHistograma("No hay datos numéricos para el histograma.")
    return x


def _son_enteros(x: np.ndarray) -> bool:
    return bool(np.all(np.abs(x - np.round(x)) < 1e-9)) and np.ptp(x) <= 100_000


def bordes(
    x,
    regla: str = "fd",
    *,
    intervalos: int | None = None,
    ancho: float | None = None,
    rango: tuple[float, float] | None = None,
    enteros: bool | None = None,
) -> np.ndarray:
    """Bordes de los intervalos. ``intervalos`` o ``ancho`` mandan sobre ``regla``.

    ``enteros=None`` lo detecta: si todos los valores son enteros, los bordes van
    en k ± ½ y la anchura es entera.
    """
    x = _limpiar(x)
    if rango is not None:
        a, b = sorted(map(float, rango))
        x = x[(x >= a) & (x <= b)]
        if x.size == 0:
            raise ErrorHistograma("No hay datos dentro del rango indicado.")
    else:
        a, b = float(x.min()), float(x.max())
    if enteros is None:
        enteros = _son_enteros(x)
    r = b - a

    if ancho is not None:
        h = float(ancho)
        if not h > 0:
            raise ErrorHistograma("La anchura de los intervalos tiene que ser positiva.")
    elif intervalos is not None:
        k = int(intervalos)
        if k < 1:
            raise ErrorHistograma("Hace falta al menos un intervalo.")
        h = (r + (1 if enteros else 0)) / k if r > 0 or enteros else 1.0
    else:
        h = _ancho_regla(x, regla)

    if enteros:
        h = max(1.0, float(round(h)))
        inicio = math.floor(a) - 0.5
        k = max(1, math.ceil((b + 0.5 - inicio) / h - 1e-9))
    elif r == 0:
        h = h if (ancho is not None) else (abs(a) * 0.1 or 1.0)
        return np.array([a - h / 2, a + h / 2])
    elif ancho is not None:
        inicio = math.floor(a / h) * h
        k = max(1, math.ceil((b - inicio) / h - 1e-9))
        if inicio + k * h < b:
            k += 1
    else:
        k = max(1, math.ceil(r / h - 1e-9)) if intervalos is None else int(intervalos)
        h = r / k
        inicio = a
    if k > MAX_INTERVALOS:
        raise ErrorHistograma(
            f"Saldrían {k} intervalos (máximo {MAX_INTERVALOS}): usa una anchura mayor o menos intervalos."
        )
    return inicio + h * np.arange(k + 1)


def _ancho_regla(x: np.ndarray, regla: str) -> float:
    n, r = x.size, float(np.ptp(x))
    if regla not in REGLAS:
        raise ErrorHistograma(f"Regla desconocida '{regla}'. Opciones: {', '.join(REGLAS)}.")
    if regla == "sturges":
        return r / (math.ceil(math.log2(n)) + 1) if r > 0 else 1.0
    if regla == "raiz":
        return r / math.ceil(math.sqrt(n)) if r > 0 else 1.0
    if regla == "fd":
        q75, q25 = np.percentile(x, [75, 25])
        h = 2.0 * (q75 - q25) * n ** (-1 / 3)
    else:  # scott
        h = (24.0 * math.sqrt(math.pi) / n) ** (1 / 3) * float(np.std(x, ddof=1)) if n > 1 else 0.0
    if not h > 0:  # IQR nulo (muchos valores repetidos): Sturges
        return _ancho_regla(x, "sturges")
    # Con colas muy largas la regla puede pedir miles de intervalos: se limita
    return max(h, r / MAX_INTERVALOS)


@dataclass
class Histograma:
    bordes: np.ndarray
    cuentas: np.ndarray
    fuera: int = 0
    enteros: bool = False
    regla: str = ""

    @property
    def n(self) -> int:
        return int(self.cuentas.sum())

    @property
    def centros(self) -> np.ndarray:
        return 0.5 * (self.bordes[:-1] + self.bordes[1:])

    @property
    def anchos(self) -> np.ndarray:
        return np.diff(self.bordes)

    def valores(self, normalizacion: str = "cuentas") -> tuple[np.ndarray, np.ndarray]:
        """Altura de cada intervalo y su error (√N, Poisson) en la normalización pedida."""
        if normalizacion not in NORMALIZACIONES:
            raise ErrorHistograma(f"Normalización desconocida '{normalizacion}'.")
        c = self.cuentas.astype(float)
        escala = self._escala(normalizacion)
        return c * escala, np.sqrt(c) * escala

    def _escala(self, normalizacion: str) -> np.ndarray:
        n = max(self.n, 1)
        if normalizacion == "cuentas":
            return np.ones_like(self.anchos)
        if normalizacion == "relativa":
            return np.full_like(self.anchos, 1.0 / n)
        return 1.0 / (n * self.anchos)

    def etiqueta_y(self, normalizacion: str = "cuentas") -> str:
        if normalizacion == "cuentas":
            h = self.anchos[0] if self.anchos.size else 1
            return "Cuentas" if self.enteros and h == 1 else f"Cuentas por intervalo (ancho {h:.3g})"
        return NORMALIZACIONES[normalizacion]


def histograma(x, regla: str = "fd", *, con_bordes=None, **kw) -> Histograma:
    """Cuenta los datos en los intervalos de :func:`bordes` (mismos argumentos), o
    en ``con_bordes`` si se dan (para comparar varias columnas con los mismos)."""
    x = _limpiar(x)
    enteros = kw.get("enteros")
    if enteros is None:
        enteros = _son_enteros(x)
        kw["enteros"] = enteros
    b = np.asarray(con_bordes, float) if con_bordes is not None else bordes(x, regla, **kw)
    dentro = (x >= b[0]) & (x <= b[-1])
    cuentas, _ = np.histogram(x[dentro], bins=b)
    nombre = "anchura fija" if kw.get("ancho") is not None else (
        "número fijo" if kw.get("intervalos") is not None else REGLAS.get(regla, regla))
    return Histograma(b, cuentas.astype(int), int((~dentro).sum()), bool(enteros), nombre)


# --- ajuste de distribuciones -----------------------------------------------------
@dataclass
class AjusteHistograma:
    distribucion: str
    parametros: list[tuple[str, float, float]]  # (nombre, valor, error)
    n: int
    chi2: float
    ndof: int
    p: float
    intervalos_test: int
    discreta: bool
    _cdf: Callable = field(repr=False, default=None)
    _pdf: Callable = field(repr=False, default=None)
    avisos: list[str] = field(default_factory=list)

    @property
    def nombre(self) -> str:
        return DISTRIBUCIONES[self.distribucion]

    def esperadas(self, h: Histograma) -> np.ndarray:
        """Entradas esperadas en cada intervalo del histograma (sin extender colas)."""
        return self.n * np.diff(self._cdf(h.bordes))

    def curva(self, h: Histograma, normalizacion: str = "cuentas", puntos: int = 400):
        """(x, y) para dibujar la distribución ajustada sobre el histograma, en la
        misma normalización. Las discretas se dan en los enteros (para escalones)."""
        if self.discreta:  # entradas esperadas por intervalo, para dibujar en escalones
            return h.centros, self.esperadas(h) * h._escala(normalizacion)
        x = np.linspace(h.bordes[0], h.bordes[-1], puntos)
        dens = self._pdf(x)
        if normalizacion == "densidad":
            return x, dens * self.n / max(h.n, 1)
        if normalizacion == "relativa":
            return x, dens * h.anchos[0] * self.n / max(h.n, 1)
        return x, dens * h.anchos[0] * self.n

    def texto(self) -> str:
        from .estadistica import formatear

        lineas = [f"{self.nombre} (máxima verosimilitud, n = {self.n})"]
        for nombre, v, e in self.parametros:
            lineas.append(f"  {nombre} = {formatear(v, e)}")
        if self.ndof > 0:
            lineas.append(f"  χ² = {self.chi2:.4g}, ν = {self.ndof}, χ²/ν = {self.chi2 / self.ndof:.3g}, p = {self.p:.3g}")
        else:
            lineas.append("  χ²: pocos intervalos con ≥ 5 entradas esperadas para el test")
        lineas += [f"  ⚠ {a}" for a in self.avisos]
        return "\n".join(lineas)


def ajustar_distribucion(x, distribucion: str, h: Histograma | None = None) -> AjusteHistograma:
    """Ajusta ``distribucion`` a los datos por máxima verosimilitud y hace el test
    χ² de Pearson con los intervalos de ``h`` (si no se da, los de Freedman–Diaconis)."""
    x = _limpiar(x)
    n = x.size
    avisos: list[str] = []
    if distribucion == "normal":
        if n < 3:
            raise ErrorHistograma("El ajuste normal necesita al menos 3 datos.")
        mu, s = float(x.mean()), float(x.std(ddof=1))
        if not s > 0:
            raise ErrorHistograma("Todos los datos son iguales: σ = 0.")
        params = [("μ", mu, s / math.sqrt(n)), ("σ", s, s / math.sqrt(2 * (n - 1)))]
        dist, discreta, k_par = stats.norm(mu, s), False, 2
    elif distribucion == "poisson":
        if np.any(x < 0) or not _son_enteros(x):
            raise ErrorHistograma("Poisson necesita cuentas: números enteros ≥ 0.")
        lam = float(x.mean())
        if not lam > 0:
            raise ErrorHistograma("Todas las cuentas son 0: λ = 0.")
        params = [("λ", lam, math.sqrt(lam / n))]
        dist, discreta, k_par = stats.poisson(lam), True, 1
    elif distribucion == "exponencial":
        if np.any(x < 0):
            raise ErrorHistograma("La exponencial necesita datos ≥ 0 (tiempos, distancias…).")
        tau = float(x.mean())
        if not tau > 0:
            raise ErrorHistograma("Todos los datos son 0.")
        params = [("τ", tau, tau / math.sqrt(n)), ("λ = 1/τ", 1 / tau, 1 / (tau * math.sqrt(n)))]
        dist, discreta, k_par = stats.expon(scale=tau), False, 1
    else:
        raise ErrorHistograma(f"Distribución desconocida '{distribucion}'. Opciones: {', '.join(DISTRIBUCIONES)}.")
    if n < 20:
        avisos.append(f"Solo {n} datos: el test χ² es poco fiable.")

    if discreta:
        # P(X ≤ b) con b semientero: la CDF discreta evaluada en ⌊b⌋
        def cdf(b, d=dist):
            return d.cdf(np.floor(np.asarray(b, dtype=float)))

        pdf = dist.pmf
    else:
        cdf, pdf = dist.cdf, dist.pdf

    h = h if h is not None else histograma(x)
    if h.fuera:
        avisos.append(f"{h.fuera} datos fuera del rango del histograma no entran en el test.")
    obs = h.cuentas.astype(float)
    # Los intervalos de los extremos se extienden hasta el final del soporte
    b = h.bordes.astype(float).copy()
    b[0], b[-1] = -np.inf, np.inf
    prob = np.diff(cdf(b))
    esperadas = prob * obs.sum()
    o_g, e_g = _agrupar(obs, esperadas)
    ndof = len(o_g) - 1 - k_par
    if ndof > 0:
        chi2 = float(np.sum((o_g - e_g) ** 2 / e_g))
        p = float(stats.chi2.sf(chi2, ndof))
    else:
        chi2, p = float("nan"), float("nan")
    return AjusteHistograma(distribucion, params, n, chi2, ndof, p, len(o_g), discreta, cdf, pdf, avisos)


def _agrupar(obs: np.ndarray, esp: np.ndarray, minimo: float = ESPERADAS_MIN):
    """Une intervalos vecinos (de izquierda a derecha) hasta que cada grupo espera
    al menos ``minimo`` entradas; el resto final se une al último grupo."""
    o_g, e_g, o_acc, e_acc = [], [], 0.0, 0.0
    for o, e in zip(obs, esp):
        o_acc += o
        e_acc += e
        if e_acc >= minimo:
            o_g.append(o_acc)
            e_g.append(e_acc)
            o_acc = e_acc = 0.0
    if e_acc > 0 or o_acc > 0:
        if e_g:
            o_g[-1] += o_acc
            e_g[-1] += e_acc
        else:
            o_g.append(o_acc)
            e_g.append(e_acc)
    return np.array(o_g), np.array(e_g)


# --- resumen estadístico -------------------------------------------------------------
@dataclass
class Resumen:
    n: int
    media: float
    error_media: float
    desviacion: float
    mediana: float
    q1: float
    q3: float
    minimo: float
    maximo: float
    asimetria: float
    curtosis: float  # exceso (0 para la normal)

    def filas(self) -> list[tuple[str, str]]:
        from .estadistica import formatear

        return [
            ("n", f"{self.n}"),
            ("Media", formatear(self.media, self.error_media) if self.n > 1 else f"{self.media:.6g}"),
            ("Desviación típica s", f"{self.desviacion:.4g}"),
            ("Mediana", f"{self.mediana:.6g}"),
            ("Cuartiles Q1 – Q3", f"{self.q1:.4g} – {self.q3:.4g}"),
            ("Mínimo – máximo", f"{self.minimo:.6g} – {self.maximo:.6g}"),
            ("Asimetría", f"{self.asimetria:.3g}"),
            ("Curtosis (exceso)", f"{self.curtosis:.3g}"),
        ]


def resumen(x) -> Resumen:
    x = _limpiar(x)
    n = x.size
    s = float(x.std(ddof=1)) if n > 1 else 0.0
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    with np.errstate(all="ignore"):
        asim = float(stats.skew(x, bias=False)) if n > 2 and s > 0 else float("nan")
        curt = float(stats.kurtosis(x, bias=False)) if n > 3 and s > 0 else float("nan")
    return Resumen(n, float(x.mean()), s / math.sqrt(n) if n > 1 else float("nan"), s, float(med), float(q1),
                   float(q3), float(x.min()), float(x.max()), asim, curt)
