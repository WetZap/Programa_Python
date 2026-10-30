"""Validación Monte Carlo: ¿las incertidumbres que da el programa son correctas?

Para cada escenario se generan M conjuntos sintéticos con parámetros conocidos
y se comprueba que:
* los pulls (p̂ − p_verdadero)/σ_p siguen N(0, 1)  (media 0, desviación 1);
* <χ²_ν> ≈ 1 y los p-valores son uniformes (test KS).
Si esto falla, las barras de error de los parámetros no son fiables.
Tarda unos segundos; puede saltarse con ``pytest -m "not lento"``.
"""
import numpy as np
import pytest
from scipy import stats

from ajustelab import Datos, ajustar

pytestmark = pytest.mark.lento


def _simular(modelo, p_real, x, dy, M, dx=None, semilla=0, **kw):
    rng = np.random.default_rng(semilla)
    f = lambda xx: modelo(xx, *p_real)  # noqa: E731
    pulls, chi2r, pvals = [], [], []
    for _ in range(M):
        xv = x if dx is None else x + rng.normal(0, dx)  # x verdadera desconocida
        y = f(xv) + (rng.normal(0, dy) if dy is not None else 0)
        d = Datos(x, y, dx=dx, dy=dy)
        res = ajustar(d, modelo, **kw)
        pulls.append((res.p - p_real) / res.sigma_p)
        chi2r.append(res.chi2_red)
        pvals.append(res.bondad().p_valor)
    return np.array(pulls), np.array(chi2r), np.array(pvals)


def _comprobar_pulls(pulls, tol_std=0.12):
    M = pulls.shape[0]
    assert np.all(np.abs(pulls.mean(axis=0)) < 4 / np.sqrt(M)), pulls.mean(axis=0)
    assert np.all(np.abs(pulls.std(axis=0, ddof=1) - 1) < tol_std), pulls.std(axis=0)


def test_mc_lineal_wls():
    from ajustelab import obtener

    x = np.linspace(0, 10, 12)
    dy = 0.2 + 0.1 * x
    pulls, chi2r, pv = _simular(obtener("lineal"), np.array([1.7, -3.0]), x, dy, M=1000)
    _comprobar_pulls(pulls)
    assert abs(chi2r.mean() - 1) < 4 * np.sqrt(2 / 10) / np.sqrt(1000)
    assert stats.kstest(pv, "uniform").pvalue > 1e-3


def test_mc_exponencial_no_lineal():
    from ajustelab import obtener

    t = np.linspace(0, 4, 20)
    pulls, chi2r, pv = _simular(obtener("A*exp(-x/tau) + C"), np.array([5.0, 1.2, 0.5]), t, np.full(t.size, 0.05),
                                M=400, n_inicios=0)
    _comprobar_pulls(pulls, tol_std=0.15)
    assert stats.kstest(pv, "uniform").pvalue > 1e-3


def test_mc_varianza_efectiva():
    from ajustelab import obtener

    x = np.linspace(1, 10, 15)
    pulls, chi2r, pv = _simular(obtener("lineal"), np.array([2.0, 1.0]), x, np.full(x.size, 0.3), M=600,
                                dx=np.full(x.size, 0.15))
    _comprobar_pulls(pulls, tol_std=0.15)
    assert abs(chi2r.mean() - 1) < 0.1


def test_mc_ols_cobertura_t_student():
    """Sin σ: (p̂ − p)/σ̂ sigue una t de Student con ν g.l.; se comprueba la cobertura 68 %."""
    from ajustelab import obtener

    x = np.linspace(0, 10, 10)
    rng = np.random.default_rng(1)
    M, nu, dentro = 1000, 8, 0
    t68 = stats.t.ppf(0.5 + 0.6827 / 2, nu)
    m = obtener("lineal")
    for _ in range(M):
        y = 2 * x + 1 + rng.normal(0, 0.5, x.size)
        res = ajustar(Datos(x, y), m)
        dentro += abs((res.p[0] - 2) / res.sigma_p[0]) < t68
    cobertura = dentro / M
    assert abs(cobertura - 0.6827) < 3 * np.sqrt(0.6827 * 0.3173 / M)
