"""Motor de ajuste por mínimos cuadrados.

Se elige el método según las incertidumbres disponibles:

=====================  ==========================================  ====================
Incertidumbres         Método                                      Covarianza
=====================  ==========================================  ====================
σ_y                    Mínimos cuadrados ponderados (WLS)          absoluta
σ_x (y opcional σ_y)   Varianza efectiva (Orear 1982), iterada:    absoluta
                       σ_eff² = σ_y² + (∂f/∂x · σ_x)²
ninguna                Mínimos cuadrados ordinarios (OLS)          escalada por χ²/ν
=====================  ==========================================  ====================

* Modelos lineales en los parámetros → solución exacta por SVD (sin p0).
* Modelos no lineales → ``scipy.optimize.least_squares`` con jacobiano
  analítico y arranque múltiple (multi-start) para evitar mínimos locales.

Referencia: J. Orear, "Least squares when both variables have uncertainties",
Am. J. Phys. 50, 912 (1982).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy.optimize import least_squares

from .datos import Datos
from .modelos import Modelo, obtener

__all__ = ["ResultadoAjuste", "ErrorAjuste", "ajustar"]

METODO_WLS = "Mínimos cuadrados ponderados (σ_y)"
METODO_VE = "Varianza efectiva (σ_x y σ_y)"
METODO_OLS = "Mínimos cuadrados ordinarios (sin incertidumbres)"


class ErrorAjuste(RuntimeError):
    """El ajuste no se puede realizar."""


@dataclass
class ResultadoAjuste:
    """Resultado de un ajuste. Las magnitudes estadísticas derivadas están en
    :mod:`ajustelab.estadistica` y se exponen aquí como atajos."""

    modelo: Modelo
    datos: Datos  # solo los puntos usados (activos)
    p: np.ndarray
    cov: np.ndarray
    sigma: np.ndarray  # incertidumbre usada en cada punto (σ_y, σ_eff o 1 en OLS)
    chi2: float  # Σ((y - f)/σ)²  (en OLS es la suma de residuos al cuadrado)
    nu: int
    metodo: str
    errores_absolutos: bool
    convergido: bool
    mensaje: str = ""
    iteraciones_ve: int = 0
    avisos: list[str] = field(default_factory=list)

    # -- atajos -------------------------------------------------------------
    @property
    def nombres(self) -> tuple[str, ...]:
        return self.modelo.parametros

    @property
    def sigma_p(self) -> np.ndarray:
        return np.sqrt(np.clip(np.diag(self.cov), 0, None))

    @property
    def chi2_red(self) -> float:
        return self.chi2 / self.nu if self.nu > 0 else np.nan

    @property
    def residuos(self) -> np.ndarray:
        return self.datos.y - self.evaluar(self.datos.x)

    @property
    def residuos_norm(self) -> np.ndarray:
        """(y - f)/σ. En OLS se divide por s = √(RSS/ν)."""
        if self.errores_absolutos:
            return self.residuos / self.sigma
        s = np.sqrt(self.chi2_red) if self.nu > 0 else np.nan
        return self.residuos / s

    @property
    def parametros(self) -> dict[str, tuple[float, float]]:
        return {n: (float(v), float(e)) for n, v, e in zip(self.nombres, self.p, self.sigma_p)}

    @property
    def fijos(self) -> dict[str, float]:
        """Parámetros que se mantuvieron fijos durante el ajuste."""
        return dict(self.modelo.fijos)

    def evaluar(self, x) -> np.ndarray:
        return self.modelo(x, *self.p)

    def sigma_f(self, x) -> np.ndarray:
        """Incertidumbre (1σ) de la curva ajustada en x: √(J C Jᵀ)."""
        x = np.atleast_1d(np.asarray(x, dtype=float))
        J = self.modelo.jacobiano(x, self.p)
        return np.sqrt(np.clip(np.einsum("ij,jk,ik->i", J, self.cov, J), 0, None))

    def inversa(self, y0: float, sigma_y0: float = 0.0, intervalo: tuple[float, float] | None = None
                ) -> list[tuple[float, float]]:
        """x tales que f(x) = y0, con su incertidumbre (curvas de calibración).

        σ_x = √(σ_f(x)² + σ_y0²) / |f'(x)|, donde σ_f es la incertidumbre de la
        curva y σ_y0 la de la medida y0. Busca en el rango de los datos salvo que
        se indique ``intervalo``. Devuelve [(x, σ_x), ...] ordenado por x.
        """
        from scipy.optimize import brentq

        lo, hi = intervalo if intervalo is not None else (float(np.min(self.datos.x)), float(np.max(self.datos.x)))
        xs = np.linspace(lo, hi, 4001)
        with np.errstate(all="ignore"):
            g = self.evaluar(xs) - y0
        soluciones = []
        for i in range(xs.size - 1):
            if not (np.isfinite(g[i]) and np.isfinite(g[i + 1])):
                continue
            if g[i] == 0:
                x0 = float(xs[i])
            elif g[i] * g[i + 1] < 0:
                x0 = brentq(lambda t: float(self.evaluar(np.array([t]))[0] - y0), xs[i], xs[i + 1], xtol=1e-14)
            else:
                continue
            pendiente = float(self.modelo.derivada_x(np.array([x0]), self.p)[0])
            sx = float(np.hypot(self.sigma_f(x0)[0], sigma_y0) / abs(pendiente)) if pendiente != 0 else np.inf
            soluciones.append((x0, sx))
        return soluciones

    def bondad(self):
        from .estadistica import bondad

        return bondad(self)

    def banda(self, x, nivel: float = 0.6827, prediccion: bool = False):
        from .estadistica import banda

        return banda(self, x, nivel=nivel, prediccion=prediccion)

    def resumen(self) -> str:
        from .estadistica import informe

        return informe(self)

    def __str__(self) -> str:
        return self.resumen()


# ---------------------------------------------------------------------------
# Álgebra
# ---------------------------------------------------------------------------
def _cov_desde_jacobiano(A: np.ndarray) -> tuple[np.ndarray, bool]:
    """(AᵀA)⁻¹ vía SVD con escalado de columnas. Devuelve (cov, rango_deficiente)."""
    k = A.shape[1]
    escala = np.linalg.norm(A, axis=0)
    escala[escala == 0] = 1.0
    _, S, Vt = np.linalg.svd(A / escala, full_matrices=False)
    tol = S.max(initial=0.0) * max(A.shape) * np.finfo(float).eps
    deficiente = S.size < k or bool(np.any(S <= tol))
    inv_S2 = np.divide(1.0, S**2, out=np.zeros_like(S), where=S > tol)
    cov = (Vt.T * inv_S2) @ Vt / np.outer(escala, escala)
    if deficiente:
        cov = np.full((k, k), np.inf)
    return cov, deficiente


def _resolver_lineal(modelo: Modelo, x, y, s) -> tuple[np.ndarray, np.ndarray, bool]:
    """Ajuste exacto de un modelo lineal en los parámetros: f = f0(x) + J(x)·p."""
    ceros = np.zeros(modelo.k)
    J = modelo.jacobiano(x, ceros)
    b = (y - modelo(x, *ceros)) / s
    A = J / s[:, None]
    escala = np.linalg.norm(A, axis=0)
    escala[escala == 0] = 1.0
    p_esc, *_ = np.linalg.lstsq(A / escala, b, rcond=None)
    p = p_esc / escala
    cov, deficiente = _cov_desde_jacobiano(A)
    return p, cov, deficiente


def _candidatos_p0(p0: np.ndarray, n: int, rng: np.random.Generator) -> list[np.ndarray]:
    """p0 y perturbaciones log-uniformes en ±1 década, con cambios de signo ocasionales."""
    candidatos = [p0, np.ones_like(p0)]
    for _ in range(n):
        factor = 10.0 ** rng.uniform(-1, 1, p0.size)
        signo = np.where(rng.random(p0.size) < 0.2, -1.0, 1.0)
        base = np.where(p0 != 0, p0, rng.normal(0, 1, p0.size))
        candidatos.append(base * factor * signo)
    return candidatos


def _resolver_no_lineal(modelo: Modelo, x, y, s, inicios: list[np.ndarray], limites):
    def residuo(p):
        return np.nan_to_num((y - modelo(x, *p)) / s, nan=1e150, posinf=1e150, neginf=-1e150)

    def jac(p):
        return np.nan_to_num(-modelo.jacobiano(x, p) / s[:, None], nan=0.0, posinf=1e150, neginf=-1e150)

    metodo = "trf" if limites is not None else "lm"
    cotas = limites if limites is not None else (-np.inf, np.inf)

    def resolver(p_ini, max_nfev):
        # Los arranques aleatorios pueden desbordar: se descartan sin avisar
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return least_squares(residuo, p_ini, jac=jac, method=metodo, bounds=cotas, x_scale="jac",
                                 max_nfev=max_nfev)

    # Fase 1: cada arranque con poco presupuesto (descarta rápido los que divergen).
    mejor = None
    for p_ini in inicios:
        p_ini = np.asarray(p_ini, dtype=float)
        if limites is not None:
            p_ini = np.clip(p_ini, np.asarray(limites[0], float), np.asarray(limites[1], float))
        try:
            sol = resolver(p_ini, 50 * (modelo.k + 1))
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            continue
        if not np.all(np.isfinite(modelo(x, *sol.x))):
            continue
        if mejor is None or sol.cost < mejor.cost * (1 - 1e-12):
            mejor = sol
    # Fase 2: se pule el mejor hasta convergencia completa.
    if mejor is not None and mejor.status == 0:
        try:
            pulido = resolver(mejor.x, 1000 * (modelo.k + 1))
            if np.all(np.isfinite(modelo(x, *pulido.x))) and pulido.cost <= mejor.cost:
                mejor = pulido
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            pass
    if mejor is None:
        raise ErrorAjuste("Ningún punto de partida ha convergido. Prueba con otros valores iniciales (p0).")
    A = -jac(mejor.x)
    cov, deficiente = _cov_desde_jacobiano(A)
    return mejor.x, cov, deficiente, mejor.status > 0, mejor.message


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def ajustar(
    datos: Datos,
    modelo: Modelo | str,
    *,
    p0: Sequence[float] | None = None,
    limites: tuple[Sequence[float], Sequence[float]] | None = None,
    fijos: dict[str, float] | None = None,
    usar_dx: bool = True,
    n_inicios: int = 12,
    semilla: int = 0,
    max_iter_ve: int = 50,
) -> ResultadoAjuste:
    """Ajusta ``modelo`` a los puntos incluidos de ``datos``.

    Parámetros
    ----------
    p0 : valores iniciales (solo modelos no lineales). Si no se dan, se usa el
        estimador del modelo y se añaden ``n_inicios`` arranques aleatorios.
    limites : (inferiores, superiores) para cada parámetro (usa ``np.inf``).
    fijos : {nombre: valor} de parámetros que no se ajustan (p. ej. un fondo
        conocido). ``p0`` y ``limites`` se refieren entonces solo a los libres.
    usar_dx : si es False, ignora σ_x aunque exista.
    """
    if isinstance(modelo, str):
        modelo = obtener(modelo)
    if fijos:
        modelo = modelo.fijar(fijos)
    d = datos.activos()
    x, y, n, k = d.x, d.y, d.n, modelo.k
    if n < k:
        raise ErrorAjuste(f"Hay {n} puntos y el modelo tiene {k} parámetros: se necesitan al menos {k}.")
    if not modelo.dominio_valido(x):
        raise ErrorAjuste(f"Los datos están fuera del dominio del modelo '{modelo.nombre}' ({modelo.texto_dominio}).")
    avisos: list[str] = []
    if n == k:
        avisos.append("ν = 0: hay tantos puntos como parámetros; no se puede evaluar la bondad del ajuste.")

    con_dx = usar_dx and d.tiene_dx
    con_dy = d.tiene_dy
    errores_absolutos = con_dx or con_dy
    metodo = METODO_VE if con_dx else (METODO_WLS if con_dy else METODO_OLS)
    s_y = d.dy if con_dy else np.zeros(n)
    s = d.dy.copy() if con_dy else np.ones(n)  # pesos del primer ajuste

    rng = np.random.default_rng(semilla)
    p_ini = np.asarray(p0, dtype=float) if p0 is not None else modelo.p0(x, y)
    if p_ini.shape != (k,):
        raise ErrorAjuste(f"p0 debe tener {k} valores {modelo.parametros}.")

    def resolver(sigma, inicios):
        if modelo.lineal and limites is None:
            p, cov, defi = _resolver_lineal(modelo, x, y, sigma)
            return p, cov, defi, True, "Solución exacta (modelo lineal en los parámetros)."
        return _resolver_no_lineal(modelo, x, y, sigma, inicios, limites)

    # 1) Ajuste inicial (con multi-start si es no lineal)
    inicios = [p_ini] if (p0 is not None and n_inicios == 0) else _candidatos_p0(p_ini, n_inicios, rng)
    p, cov, deficiente, convergido, mensaje = resolver(s, inicios)

    # 2) Varianza efectiva: se recalculan los pesos con ∂f/∂x hasta converger
    iteraciones = 0
    if con_dx:
        convergido_ve = False
        for iteraciones in range(1, max_iter_ve + 1):
            s = np.sqrt(s_y**2 + (modelo.derivada_x(x, p) * d.dx) ** 2)
            if not np.all(np.isfinite(s)):
                raise ErrorAjuste("∂f/∂x no es finita en algún punto: no se puede aplicar la varianza efectiva.")
            if np.any(s <= 0):
                suelo = 1e-12 * max(s.max(), 1e-300)
                s = np.maximum(s, suelo)
                if not any("σ_eff = 0" in a for a in avisos):
                    avisos.append("σ_eff = 0 en algún punto (sin σ_y y con ∂f/∂x = 0 o σ_x = 0); se ha usado un suelo numérico.")
            p_nuevo, cov, deficiente, convergido, mensaje = resolver(s, [p])
            cambio = np.abs(p_nuevo - p)
            p = p_nuevo
            if np.all(cambio <= 1e-8 * (np.abs(p) + np.sqrt(np.abs(np.diag(cov))) + 1e-300)):
                convergido_ve = True
                break
        if not convergido_ve:
            avisos.append(f"La varianza efectiva no ha convergido en {max_iter_ve} iteraciones.")
            convergido = False

    r = (y - modelo(x, *p)) / s
    chi2 = float(np.sum(r**2))
    nu = n - k
    if not errores_absolutos and nu > 0:
        cov = cov * chi2 / nu
    motivo = modelo.comprobar_plausibilidad(p, x)
    if motivo:
        avisos.append(f"Resultado poco plausible: {motivo}.")
    if deficiente:
        avisos.append("Parámetros degenerados (jacobiano de rango deficiente): algún parámetro no está determinado por los datos.")
        convergido = False

    return ResultadoAjuste(
        modelo=modelo,
        datos=d,
        p=np.asarray(p, dtype=float),
        cov=cov,
        sigma=s,
        chi2=chi2,
        nu=nu,
        metodo=metodo,
        errores_absolutos=errores_absolutos,
        convergido=bool(convergido),
        mensaje=str(mensaje),
        iteraciones_ve=iteraciones,
        avisos=avisos,
    )
