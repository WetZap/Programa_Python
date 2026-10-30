"""Intersección de dos curvas ajustadas con su incertidumbre.

Sirve para cualquier par de modelos (no solo rectas). El punto de corte x*
cumple g(x*; p₁, p₂) = f₁(x*; p₁) − f₂(x*; p₂) = 0. Por el teorema de la
función implícita, con g' = f₁'(x*) − f₂'(x*):

    ∂x*/∂p₁ = −(∂f₁/∂p₁)/g'          ∂x*/∂p₂ = +(∂f₂/∂p₂)/g'
    ∂y*/∂p₁ = ∂f₁/∂p₁ + f₁'·∂x*/∂p₁   ∂y*/∂p₂ = f₁'·∂x*/∂p₂

y la covarianza de (x*, y*) es  G·diag(C₁, C₂)·Gᵀ  (G es 2 × (k₁+k₂)).
Se supone que los dos ajustes provienen de **conjuntos de datos independientes**.
x* e y* salen correlacionados: por eso se da la matriz 2×2 y la elipse, no solo
dos barras de error.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats
from scipy.optimize import brentq, newton

from .ajuste import ResultadoAjuste, ajustar
from .datos import Datos
from .estadistica import formatear
from .modelos import Modelo

__all__ = ["Interseccion", "ErrorInterseccion", "intersecar", "intersecar_datos", "dividir"]


class ErrorInterseccion(ValueError):
    """No se encuentra el corte o no está bien definido."""


@dataclass
class Interseccion:
    x: float
    y: float
    cov: np.ndarray
    ajuste1: ResultadoAjuste = field(repr=False)
    ajuste2: ResultadoAjuste = field(repr=False)
    avisos: list[str] = field(default_factory=list)

    @property
    def sigma_x(self) -> float:
        return float(np.sqrt(self.cov[0, 0]))

    @property
    def sigma_y(self) -> float:
        return float(np.sqrt(self.cov[1, 1]))

    @property
    def rho(self) -> float:
        return float(self.cov[0, 1] / (self.sigma_x * self.sigma_y)) if self.sigma_x * self.sigma_y > 0 else 0.0

    def elipse(self, nivel: float = 0.6827) -> tuple[float, float, float]:
        """(ancho, alto, ángulo en grados) de la región de confianza conjunta.

        Para dos variables, el 68.27 % corresponde a Δχ² = 2.30, no a 1σ en cada
        eje (la elipse 'de 1σ', Δχ² = 1, solo contiene el 39.3 %).
        """
        valores, vectores = np.linalg.eigh(self.cov)
        k = np.sqrt(stats.chi2.ppf(nivel, 2))
        ancho, alto = 2 * k * np.sqrt(np.clip(valores[::-1], 0, None))
        angulo = np.degrees(np.arctan2(vectores[1, 1], vectores[0, 1]))
        return float(ancho), float(alto), float(angulo)

    def resumen(self) -> str:
        n1, n2 = self.ajuste1.modelo.nombre, self.ajuste2.modelo.nombre
        lineas = [f"Intersección de '{n1}' y '{n2}':",
                  f"  x* = {formatear(self.x, self.sigma_x)}    ({self.x:.10g} ± {self.sigma_x:.4g})",
                  f"  y* = {formatear(self.y, self.sigma_y)}    ({self.y:.10g} ± {self.sigma_y:.4g})",
                  f"  correlación ρ(x*, y*) = {self.rho:+.3f}"]
        if self.avisos:
            lineas += ["Avisos:"] + [f"  - {a}" for a in self.avisos]
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.resumen()


def _raices(g, a: float, b: float, n: int = 4000) -> list[float]:
    xs = np.linspace(a, b, n)
    with np.errstate(all="ignore"):
        gs = g(xs)
    raices = []
    for i in range(n - 1):
        g0, g1 = gs[i], gs[i + 1]
        if not (np.isfinite(g0) and np.isfinite(g1)):
            continue
        if g0 == 0:
            raices.append(float(xs[i]))
        elif g0 * g1 < 0:
            raices.append(brentq(lambda t: float(g(np.array([t]))[0]), xs[i], xs[i + 1], xtol=1e-14, rtol=1e-14))
    return raices


def _punto(r1: ResultadoAjuste, r2: ResultadoAjuste, x: float) -> Interseccion:
    m1, m2 = r1.modelo, r2.modelo
    xa = np.array([x])
    J1 = m1.jacobiano(xa, r1.p)[0]
    J2 = m2.jacobiano(xa, r2.p)[0]
    d1 = float(m1.derivada_x(xa, r1.p)[0])
    d2 = float(m2.derivada_x(xa, r2.p)[0])
    gp = d1 - d2
    escala = max(abs(d1), abs(d2), 1e-300)
    if abs(gp) < 1e-10 * escala:
        raise ErrorInterseccion("Las curvas son tangentes o paralelas en el corte: x* no está determinado.")
    dx1, dx2 = -J1 / gp, J2 / gp
    G = np.vstack([np.concatenate([dx1, dx2]), np.concatenate([J1 + d1 * dx1, d1 * dx2])])
    C = np.zeros((m1.k + m2.k,) * 2)
    C[: m1.k, : m1.k] = r1.cov
    C[m1.k:, m1.k:] = r2.cov
    cov = G @ C @ G.T
    y = float(r1.evaluar(xa)[0])

    avisos = []
    for nombre, r in (("1", r1), ("2", r2)):
        lo, hi = np.min(r.datos.x), np.max(r.datos.x)
        if not lo <= x <= hi:
            avisos.append(f"x* está fuera del rango de datos del ajuste {nombre} [{lo:.4g}, {hi:.4g}]: es una "
                          "extrapolación.")
        b = r.bondad()
        if not r.convergido or (np.isfinite(b.p_valor) and b.p_valor < 0.01):
            avisos.append(f"El ajuste {nombre} no es fiable (no converge o p < 0.01); la incertidumbre de x* "
                          "también será poco fiable.")
    if r1.datos.n == r2.datos.n and np.array_equal(r1.datos.x, r2.datos.x) and np.array_equal(r1.datos.y, r2.datos.y):
        avisos.append("Los dos ajustes usan los mismos datos: sus parámetros están correlacionados y la "
                      "incertidumbre calculada (que los supone independientes) no es válida.")
    return Interseccion(x=float(x), y=y, cov=cov, ajuste1=r1, ajuste2=r2, avisos=avisos)


def intersecar(
    r1: ResultadoAjuste,
    r2: ResultadoAjuste,
    *,
    intervalo: tuple[float, float] | None = None,
    x0: float | None = None,
    todas: bool = False,
) -> Interseccion | list[Interseccion]:
    """Punto(s) de corte de dos ajustes.

    intervalo : dónde buscar. Por defecto, la unión de los rangos de x de ambos
        ajustes ampliada una vez su anchura a cada lado.
    x0 : estimación inicial (alternativa a ``intervalo``; usa Newton).
    todas : devuelve una lista con todos los cortes del intervalo; si no, el
        más cercano al centro de los datos.
    """
    def g(x):
        return r1.evaluar(x) - r2.evaluar(x)

    if x0 is not None:
        try:
            raices = [float(newton(lambda t: float(g(np.array([t]))[0]), x0, tol=1e-14, maxiter=200))]
        except RuntimeError as e:
            raise ErrorInterseccion(f"Newton no converge desde x0 = {x0}: {e}") from e
    else:
        xs = np.concatenate([r1.datos.x, r2.datos.x])
        lo, hi = float(np.min(xs)), float(np.max(xs))
        if intervalo is None:
            ancho = hi - lo or 1.0
            intervalo = (lo - ancho, hi + ancho)
        raices = _raices(g, *intervalo)
        if not raices:
            raise ErrorInterseccion(f"Las curvas no se cortan en [{intervalo[0]:.4g}, {intervalo[1]:.4g}]. "
                                    "Indica otro intervalo o un x0.")
    puntos = [_punto(r1, r2, x) for x in raices]
    if todas:
        return puntos
    centro = float(np.mean(np.concatenate([r1.datos.x, r2.datos.x])))
    elegido = min(puntos, key=lambda p: abs(p.x - centro))
    if len(puntos) > 1:
        elegido.avisos.append(f"Hay {len(puntos)} cortes en el intervalo; se devuelve el más cercano al centro "
                              "de los datos (usa todas=True para verlos).")
    return elegido


def intersecar_datos(d1: Datos, d2: Datos, modelo1: str | Modelo = "lineal", modelo2: str | Modelo = "lineal",
                     **kw) -> Interseccion:
    """Ajusta cada conjunto con su modelo y devuelve la intersección (la antigua opción 4)."""
    return intersecar(ajustar(d1, modelo1), ajustar(d2, modelo2), **kw)


def dividir(datos: Datos, n: int) -> tuple[Datos, Datos]:
    """Separa un conjunto en los n primeros puntos y el resto (como el script antiguo)."""
    if not 0 < n < datos.n_total:
        raise ValueError(f"n debe estar entre 1 y {datos.n_total - 1}.")

    def parte(s):
        return Datos(datos.x[s], datos.y[s], None if datos.dx is None else datos.dx[s],
                     None if datos.dy is None else datos.dy[s], datos.nombre_x, datos.nombre_y,
                     incluidos=datos.incluidos[s], origen=datos.origen)

    return parte(slice(0, n)), parte(slice(n, None))
