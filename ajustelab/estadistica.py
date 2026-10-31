"""Estadística del ajuste: bondad, tests sobre residuos, bandas, criterios de
información y redondeo de resultados.

Resumen de criterios
--------------------
* χ², ν = n − k, χ²_ν y p = P(χ²_ν ≥ χ²_obs). Solo tiene sentido con
  incertidumbres conocidas (``errores_absolutos``).
* Test de rachas (Wald–Wolfowitz) sobre el signo de los residuos ordenados en x,
  **unilateral** (pocas rachas = estructura sistemática = modelo inadecuado).
  Distribución exacta (combinatoria), no la aproximación normal.
* Shapiro–Wilk sobre los residuos normalizados (n ≥ 8).
* Durbin–Watson (≈ 2 si no hay autocorrelación).
* AIC, AICc y BIC para comparar modelos (se usarán en la selección automática).
* Bandas de confianza/predicción por el método delta: σ_f² = J C Jᵀ.
* Redondeo con la regla del PDG.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Context, Decimal
from typing import TYPE_CHECKING

import numpy as np
from scipy import stats

if TYPE_CHECKING:
    from .ajuste import ResultadoAjuste

__all__ = [
    "Bondad",
    "Test",
    "bondad",
    "banda",
    "correlacion",
    "prueba_rachas",
    "durbin_watson",
    "criterios_informacion",
    "redondear",
    "formatear",
    "informe",
]

_CTX = Context(prec=60)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@dataclass
class Test:
    nombre: str
    estadistico: float
    p: float
    detalle: str = ""

    def __str__(self) -> str:
        return f"{self.nombre}: {self.detalle} p = {self.p:.3g}".strip()


def _prob_rachas(r: int, n1: int, n2: int) -> float:
    """P(R = r) exacta para n1 signos + y n2 signos − colocados al azar."""
    total = math.comb(n1 + n2, n1)

    def c(a, b):
        return math.comb(a, b) if 0 <= b <= a else 0

    if r % 2 == 0:
        m = r // 2
        casos = 2 * c(n1 - 1, m - 1) * c(n2 - 1, m - 1)
    else:
        m = (r - 1) // 2
        casos = c(n1 - 1, m) * c(n2 - 1, m - 1) + c(n1 - 1, m - 1) * c(n2 - 1, m)
    return casos / total


def prueba_rachas(residuos_ordenados: np.ndarray) -> Test:
    """Test de rachas unilateral: p = P(R ≤ R_obs) bajo signos aleatorios.

    p pequeño ⇒ hay menos rachas de las esperadas ⇒ los residuos tienen estructura
    (curvatura, tendencia) que el modelo no explica.
    """
    r = np.asarray(residuos_ordenados, dtype=float)
    signos = np.sign(r[r != 0])
    n1, n2 = int(np.sum(signos > 0)), int(np.sum(signos < 0))
    n = n1 + n2
    if n < 2:
        return Test("Rachas", np.nan, np.nan, "pocos residuos no nulos.")
    if n1 == 0 or n2 == 0:
        return Test("Rachas", 1.0, 2 * 0.5**n, "todos los residuos tienen el mismo signo.")
    R = 1 + int(np.sum(signos[1:] != signos[:-1]))
    esperado = 1 + 2 * n1 * n2 / n
    if n <= 5000:
        p = sum(_prob_rachas(k, n1, n2) for k in range(2, R + 1))
    else:  # aproximación normal con corrección de continuidad
        var = 2 * n1 * n2 * (2 * n1 * n2 - n) / (n**2 * (n - 1))
        p = stats.norm.cdf((R + 0.5 - esperado) / math.sqrt(var))
    return Test("Rachas", float(R), float(min(p, 1.0)), f"R = {R} (esperado {esperado:.1f}),")


def durbin_watson(residuos_ordenados: np.ndarray) -> float:
    r = np.asarray(residuos_ordenados, dtype=float)
    den = float(np.sum(r**2))
    return float(np.sum(np.diff(r) ** 2) / den) if den > 0 else np.nan


def correlacion(cov: np.ndarray) -> np.ndarray:
    s = np.sqrt(np.clip(np.diag(cov), 0, None))
    with np.errstate(all="ignore"):
        rho = cov / np.outer(s, s)
    np.fill_diagonal(rho, 1.0)
    return rho


def criterios_informacion(chi2: float, n: int, k: int, errores_absolutos: bool) -> tuple[float, float, float]:
    """(AIC, AICc, BIC).

    Con σ conocidas, −2 ln L = χ² + cte. Sin σ, se usa n·ln(RSS/n) y se cuenta
    σ como un parámetro más. Solo las diferencias entre modelos (mismos datos)
    tienen significado.
    """
    if errores_absolutos:
        m2lnL, keff = chi2, k
    else:
        m2lnL, keff = n * math.log(max(chi2, 1e-300) / n), k + 1
    aic = m2lnL + 2 * keff
    aicc = aic + (2 * keff * (keff + 1) / (n - keff - 1) if n - keff - 1 > 0 else np.inf)
    bic = m2lnL + keff * math.log(n)
    return aic, aicc, bic


# ---------------------------------------------------------------------------
# Bondad del ajuste
# ---------------------------------------------------------------------------
@dataclass
class Bondad:
    n: int
    k: int
    nu: int
    chi2: float
    chi2_red: float
    p_valor: float
    r2: float
    aic: float
    aicc: float
    bic: float
    rachas: Test
    shapiro: Test | None
    durbin_watson: float
    factor_escala: float
    correlacion: np.ndarray
    atipicos: list[int] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def bondad(res: "ResultadoAjuste") -> Bondad:
    d = res.datos
    orden = np.argsort(d.x, kind="stable")
    rn = res.residuos_norm
    n, k, nu = d.n, res.modelo.k, res.nu

    # χ² y p-valor
    p_valor = float(stats.chi2.sf(res.chi2, nu)) if (res.errores_absolutos and nu > 0) else np.nan
    chi2_red = res.chi2_red

    # R² ponderado (solo informativo)
    w = 1 / res.sigma**2
    ym = np.sum(w * d.y) / np.sum(w)
    sst = np.sum(w * (d.y - ym) ** 2)
    r2 = float(1 - np.sum(w * res.residuos**2) / sst) if sst > 0 else np.nan

    aic, aicc, bic = criterios_informacion(res.chi2, n, k, res.errores_absolutos)
    rachas = prueba_rachas(res.residuos[orden])
    shapiro = None
    if n >= 8 and np.all(np.isfinite(rn)) and np.ptp(rn) > 0:
        W, p_sw = stats.shapiro(rn)
        shapiro = Test("Shapiro–Wilk", float(W), float(p_sw), f"W = {W:.3f},")
    dw = durbin_watson(res.residuos[orden])
    # Factor de escala PDG: solo si hay evidencia de errores subestimados (p < 0.05)
    escala = float(np.sqrt(chi2_red)) if (res.errores_absolutos and nu > 0 and p_valor < 0.05) else 1.0
    rho = correlacion(res.cov)
    atipicos = [int(i) for i in np.flatnonzero(np.abs(rn) > 3)] if np.all(np.isfinite(rn)) else []

    # -- Avisos interpretativos ----------------------------------------------
    avisos = list(res.avisos)
    if not res.convergido:
        avisos.append(f"El ajuste no ha convergido correctamente: {res.mensaje}")
    if not res.errores_absolutos:
        avisos.append("Sin incertidumbres: los errores de los parámetros se estiman con la dispersión de los "
                      "residuos (s² = RSS/ν) y no hay test χ². Si conoces σ_y, añádela.")
    elif nu > 0:
        if p_valor < 0.01:
            avisos.append(f"p = {p_valor:.2g} < 0.01 (χ²_ν = {chi2_red:.3g}): el modelo no es compatible con los datos "
                          "o las incertidumbres están subestimadas.")
        elif p_valor < 0.05:
            avisos.append(f"p = {p_valor:.2g} < 0.05: ajuste dudoso.")
        elif p_valor > 0.99:
            avisos.append(f"p = {p_valor:.3g} > 0.99 (χ²_ν = {chi2_red:.3g}): incertidumbres probablemente "
                          "sobreestimadas o correlacionadas.")
        if escala > 1:
            avisos.append(f"Si atribuyes χ²_ν > 1 a errores subestimados, multiplica σ de los parámetros por "
                          f"√χ²_ν = {escala:.3g} (criterio PDG).")
    if np.isfinite(rachas.p) and rachas.p < 0.05:
        avisos.append(f"Test de rachas p = {rachas.p:.2g}: los residuos tienen estructura sistemática; "
                      "probablemente falta un término en el modelo.")
    if shapiro is not None and shapiro.p < 0.05:
        avisos.append(f"Residuos no normales (Shapiro–Wilk p = {shapiro.p:.2g}): revisa puntos atípicos.")
    if atipicos:
        avisos.append(f"Puntos con |residuo normalizado| > 3 (índices entre los usados): {atipicos}.")
    nombres = res.nombres
    for i in range(k):
        for j in range(i + 1, k):
            if np.isfinite(rho[i, j]) and abs(rho[i, j]) > 0.95:
                avisos.append(f"{nombres[i]} y {nombres[j]} muy correlacionados (ρ = {rho[i, j]:+.3f}): "
                              "considera centrar x o reparametrizar.")
    for nombre, v, e in zip(nombres, res.p, res.sigma_p):
        if np.isfinite(e) and e > 0 and abs(v) < e:
            avisos.append(f"{nombre} es compatible con 0 (|{nombre}| < σ): quizá sobra ese parámetro.")

    return Bondad(n=n, k=k, nu=nu, chi2=res.chi2, chi2_red=chi2_red, p_valor=p_valor, r2=r2, aic=aic,
                  aicc=aicc, bic=bic, rachas=rachas, shapiro=shapiro, durbin_watson=dw, factor_escala=escala,
                  correlacion=rho, atipicos=atipicos, avisos=avisos)


# ---------------------------------------------------------------------------
# Bandas
# ---------------------------------------------------------------------------
def banda(res: "ResultadoAjuste", x, nivel: float = 0.6827, prediccion: bool = False):
    """Devuelve (f, inferior, superior) en x.

    Confianza: incertidumbre de la curva ajustada, σ_f² = J C Jᵀ.
    Predicción: además incluye la dispersión de una medida nueva (σ_y² interpolada
    o s² en OLS). Factor de cobertura: normal si σ conocidas, t de Student si no.
    """
    x = np.asarray(x, dtype=float)
    f = res.evaluar(x)
    J = res.modelo.jacobiano(x, res.p)
    var = np.einsum("ij,jk,ik->i", J, res.cov, J)
    if prediccion:
        if res.errores_absolutos:
            o = np.argsort(res.datos.x)
            var = var + np.interp(x, res.datos.x[o], res.sigma[o] ** 2)
        else:
            var = var + res.chi2_red
    q = (1 + nivel) / 2
    factor = stats.norm.ppf(q) if res.errores_absolutos or res.nu <= 0 else stats.t.ppf(q, res.nu)
    delta = factor * np.sqrt(np.clip(var, 0, None))
    return f, f - delta, f + delta


# ---------------------------------------------------------------------------
# Redondeo y formato
# ---------------------------------------------------------------------------
def redondear(valor: float, error: float, cifras: int | None = None) -> tuple[Decimal, Decimal, int] | None:
    """Redondeo con la regla del PDG (o ``cifras`` significativas fijas en el error).

    Regla PDG sobre las tres primeras cifras del error: 100–354 → 2 cifras;
    355–949 → 1 cifra; 950–999 → se sube a 1000 y se dan 2 cifras. El valor se
    redondea a la misma posición decimal. Devuelve (valor, error, posición)
    donde la última cifra está en 10**posición, o None si el error no es válido.
    """
    if not (np.isfinite(valor) and np.isfinite(error)) or error <= 0:
        return None
    e = Decimal(repr(float(error)))
    exp = e.adjusted()  # floor(log10(e))
    tres = int(e.scaleb(2 - exp, _CTX).to_integral_value(ROUND_HALF_UP))
    if tres >= 1000:
        exp, tres = exp + 1, 100
    if cifras is not None:
        nsig = cifras
    elif tres <= 354:
        nsig = 2
    elif tres <= 949:
        nsig = 1
    else:
        exp, nsig = exp + 1, 2
        e = Decimal(1).scaleb(exp)
    pos = exp - nsig + 1
    q = Decimal(1).scaleb(pos)
    e_r = e.quantize(q, ROUND_HALF_UP, _CTX)
    v_r = Decimal(repr(float(valor))).quantize(q, ROUND_HALF_UP, _CTX)
    return v_r, e_r, pos


_SUPER = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def formatear(valor: float, error: float, cifras: int | None = None, unidad: str = "", latex: bool = False) -> str:
    """'3.142 ± 0.023', '(1.235 ± 0.023)·10⁻³ m' o su versión LaTeX."""
    pm = r" \pm " if latex else " ± "
    r = redondear(valor, error, cifras)
    if r is None:
        txt = f"{valor:.6g}" + ("" if not np.isfinite(error) or error == 0 else f"{pm}{error:.2g}")
        return f"{txt} {unidad}".strip()
    v, e, pos = r
    ref = v if v != 0 else e
    exp_v = ref.adjusted()
    if exp_v >= 4 or exp_v <= -3:
        decimales = max(exp_v - pos, 0)
        mv = v.scaleb(-exp_v, _CTX)
        me = e.scaleb(-exp_v, _CTX)
        cuerpo = f"{mv:.{decimales}f}{pm}{me:.{decimales}f}"
        potencia = rf"\times 10^{{{exp_v}}}" if latex else f"·10{str(exp_v).translate(_SUPER)}"
        txt = f"({cuerpo}){potencia}"
    else:
        decimales = max(-pos, 0)
        txt = f"{v:.{decimales}f}{pm}{e:.{decimales}f}"
        if unidad:
            txt = f"({txt})"
    return f"{txt} {unidad}".strip()


# ---------------------------------------------------------------------------
# Informe de texto
# ---------------------------------------------------------------------------
def informe(res: "ResultadoAjuste") -> str:
    b = bondad(res)
    m = res.modelo
    lineas = [
        f"Modelo: {m.nombre}    y = {m.expresion}",
        f"Método: {res.metodo}" + (f"  ({res.iteraciones_ve} iteraciones)" if res.iteraciones_ve else ""),
        f"Puntos: n = {b.n}    Parámetros: k = {b.k}    ν = {b.nu}",
        "",
        "Parámetros (1σ):",
    ]
    ancho = max(len(nm) for nm in (*m.parametros, *m.fijos)) if (m.k or m.fijos) else 1
    for nm, v, e in zip(m.parametros, res.p, res.sigma_p):
        extra = ""
        if b.factor_escala > 1:
            extra = f"    [con σ×√χ²_ν: {formatear(v, e * b.factor_escala)}]"
        lineas.append(f"  {nm:>{ancho}} = {formatear(v, e)}    ({v:.10g} ± {e:.4g}){extra}")
    for nm, v in m.fijos.items():
        lineas.append(f"  {nm:>{ancho}} = {v:.10g}    (fijo)")
    if m.k > 1:
        lineas += ["", "Matriz de correlación:"]
        lineas.append(" " * (ancho + 2) + "".join(f"{nm:>9}" for nm in m.parametros))
        for nm, fila in zip(m.parametros, b.correlacion):
            lineas.append(f"  {nm:>{ancho}}" + "".join(f"{v:9.3f}" for v in fila))
    lineas += ["", "Bondad del ajuste:"]
    if res.errores_absolutos:
        lineas.append(f"  χ² = {b.chi2:.4g}    χ²_ν = {b.chi2_red:.4g}    p = {b.p_valor:.3g}")
    else:
        lineas.append(f"  RSS = {b.chi2:.4g}    s = √(RSS/ν) = {np.sqrt(b.chi2_red):.4g}")
    lineas.append(f"  R² (ponderado) = {b.r2:.6f}")
    lineas.append(f"  {b.rachas}")
    if b.shapiro is not None:
        lineas.append(f"  {b.shapiro}")
    lineas.append(f"  Durbin–Watson = {b.durbin_watson:.3f}")
    lineas.append(f"  AIC = {b.aic:.4g}    AICc = {b.aicc:.4g}    BIC = {b.bic:.4g}")
    if b.avisos:
        lineas += ["", "Avisos:"] + [f"  - {a}" for a in b.avisos]
    return "\n".join(lineas)
