import itertools

import numpy as np
import pytest
from scipy import stats

from ajustelab import Datos, ajustar
from ajustelab.estadistica import (_prob_rachas, criterios_informacion, formatear, redondear, prueba_rachas)


# --- rachas ---------------------------------------------------------------
@pytest.mark.parametrize("n1, n2", [(1, 1), (3, 4), (5, 5), (7, 2), (20, 13)])
def test_distribucion_rachas_normalizada(n1, n2):
    total = sum(_prob_rachas(r, n1, n2) for r in range(2, n1 + n2 + 1))
    assert np.isclose(total, 1.0)


def test_rachas_exacta_vs_enumeracion():
    n1, n2 = 4, 3
    cuentas = {}
    for pos in itertools.combinations(range(n1 + n2), n1):
        s = np.full(n1 + n2, -1)
        s[list(pos)] = 1
        r = 1 + int(np.sum(s[1:] != s[:-1]))
        cuentas[r] = cuentas.get(r, 0) + 1
    total = sum(cuentas.values())
    for r, c in cuentas.items():
        assert np.isclose(_prob_rachas(r, n1, n2), c / total)


def test_rachas_detecta_curvatura():
    x = np.linspace(-1, 1, 30)
    r = x**2 - np.mean(x**2)  # residuos de ajustar una recta a una parábola
    assert prueba_rachas(r).p < 0.001
    alterno = np.array([1, -1] * 15, dtype=float)
    assert prueba_rachas(alterno).p > 0.99


# --- redondeo -------------------------------------------------------------
@pytest.mark.parametrize("v, e, esperado", [
    (3.14159, 0.0234, "3.142 ± 0.023"),       # 234 → 2 cifras
    (3.14159, 0.0456, "3.14 ± 0.05"),         # 456 → 1 cifra
    (9.8123, 0.0973, "9.81 ± 0.10"),          # 973 → se sube a 0.10
    (1234.5, 56, "1230 ± 60"),
    (0.0012345, 0.0000234, "(1.235 ± 0.023)·10⁻³"),
    (6.02214e23, 3.1e19, "(6.02214 ± 0.00031)·10²³"),
    (-0.5, 0.123, "-0.50 ± 0.12"),
    (12.0, 0.35, "12.00 ± 0.35"),
    (12.0, 0.355, "12.0 ± 0.4"),
])
def test_redondeo_pdg(v, e, esperado):
    assert formatear(v, e) == esperado


def test_redondeo_cifras_fijas_unidades_latex():
    assert formatear(3.14159, 0.0234, cifras=1) == "3.14 ± 0.02"
    assert formatear(3.14159, 0.0234, unidad="m") == "(3.142 ± 0.023) m"
    assert formatear(0.0012345, 0.0000234, latex=True) == r"(1.235 \pm 0.023)\times 10^{-3}"
    assert redondear(1.0, 0.0) is None
    assert formatear(1.0, np.nan).startswith("1")


# --- bondad y bandas ----------------------------------------------------
def test_pvalor_y_criterios():
    rng = np.random.default_rng(3)
    x = np.linspace(0, 10, 20)
    y = 1.5 * x + 2 + rng.normal(0, 0.5, x.size)
    res = ajustar(Datos(x, y, dy=0.5), "lineal")
    b = res.bondad()
    assert np.isclose(b.p_valor, stats.chi2.sf(res.chi2, 18))
    aic, aicc, bic = criterios_informacion(res.chi2, 20, 2, True)
    assert np.isclose(b.aicc, res.chi2 + 4 + 12 / 17) and np.isclose(aic, b.aic) and np.isclose(bic, b.bic)


def test_banda_recta():
    rng = np.random.default_rng(4)
    x = np.linspace(0, 10, 12)
    res = ajustar(Datos(x, 2 * x + 1 + rng.normal(0, 0.3, x.size), dy=0.3), "lineal")
    xx = np.array([-5.0, 0.0, 5.0, 20.0])
    f, lo, hi = res.banda(xx)
    C = res.cov
    sigma_f = np.sqrt(C[0, 0] * xx**2 + C[1, 1] + 2 * xx * C[0, 1])
    assert np.allclose(hi - f, stats.norm.ppf(0.84135) * sigma_f, rtol=1e-4)
    _, lo_p, hi_p = res.banda(xx, prediccion=True)
    assert np.all(hi_p - lo_p > hi - lo)


def test_avisos_modelo_incorrecto():
    x = np.linspace(0, 10, 25)
    y = 0.5 * x**2 + np.random.default_rng(5).normal(0, 0.2, x.size)
    b = ajustar(Datos(x, y, dy=0.2), "lineal").bondad()
    assert b.p_valor < 1e-6 and b.rachas.p < 0.01
    texto = " ".join(b.avisos)
    assert "no es compatible" in texto and "rachas" in texto
