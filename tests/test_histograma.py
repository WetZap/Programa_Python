import math

import numpy as np
import pytest
from scipy.integrate import trapezoid

from ajustelab.histograma import (
    ErrorHistograma, ajustar_distribucion, bordes, histograma, resumen, _agrupar,
)


@pytest.fixture
def rng():
    return np.random.default_rng(20261105)


@pytest.mark.parametrize("regla,numpy", [("fd", "fd"), ("scott", "scott"), ("sturges", "sturges"), ("raiz", "sqrt")])
def test_reglas_como_numpy(rng, regla, numpy):
    x = rng.normal(5, 2, 1500)
    assert histograma(x, regla).cuentas.size == np.histogram_bin_edges(x, numpy).size - 1


def test_intervalos_y_anchura_fijos(rng):
    x = rng.normal(0, 1, 500)
    h = histograma(x, intervalos=12)
    assert h.cuentas.size == 12 and h.n == 500 and h.fuera == 0
    b = bordes(x, ancho=0.25)
    assert np.allclose(np.diff(b), 0.25) and np.isclose(b[0] / 0.25, round(b[0] / 0.25))
    assert b[0] <= x.min() and b[-1] >= x.max()
    with pytest.raises(ErrorHistograma):
        bordes(x, ancho=1e-6)  # demasiados intervalos
    with pytest.raises(ErrorHistograma):
        bordes(x, ancho=-1)


def test_enteros_centrados(rng):
    k = rng.poisson(3, 400)
    h = histograma(k)
    assert h.enteros and np.allclose(h.centros, np.arange(k.min(), k.max() + 1))
    assert h.etiqueta_y() == "Cuentas"
    h2 = histograma(k, ancho=2)
    assert np.allclose(np.diff(h2.bordes), 2) and h2.bordes[0] == k.min() - 0.5 and h2.n == 400


def test_rango_y_datos_constantes(rng):
    x = rng.normal(0, 1, 300)
    h = histograma(x, rango=(-1, 1))
    assert h.fuera == np.sum((x < -1) | (x > 1)) and h.n + h.fuera == 300
    assert histograma([2.5, 2.5, 2.5]).cuentas.tolist() == [3]
    with pytest.raises(ErrorHistograma):
        histograma([np.nan])


def test_normalizaciones(rng):
    x = rng.exponential(2, 700)
    h = histograma(x)
    y, dy = h.valores("cuentas")
    assert np.allclose(y, h.cuentas) and np.allclose(dy, np.sqrt(h.cuentas))
    y, _ = h.valores("relativa")
    assert math.isclose(y.sum(), 1)
    y, dy = h.valores("densidad")
    assert math.isclose(np.sum(y * h.anchos), 1)
    assert np.allclose(dy, np.sqrt(h.cuentas) / (700 * h.anchos))


def test_ajuste_normal(rng):
    x = rng.normal(5, 2, 3000)
    a = ajustar_distribucion(x, "normal", histograma(x))
    (_, mu, dmu), (_, s, ds) = a.parametros
    assert abs(mu - 5) < 4 * dmu and abs(s - 2) < 4 * ds
    assert math.isclose(dmu, s / math.sqrt(3000))
    assert a.ndof == a.intervalos_test - 3 and 0 <= a.p <= 1
    # la curva en cuentas integra a n
    h = histograma(x)
    cx, cy = a.curva(h)
    assert math.isclose(trapezoid(cy, cx) / h.anchos[0], h.n, rel_tol=0.02)


def test_ajuste_poisson_y_exponencial(rng):
    k = rng.poisson(4.2, 600)
    a = ajustar_distribucion(k, "poisson")
    _, lam, dlam = a.parametros[0]
    assert abs(lam - 4.2) < 4 * dlam and a.discreta
    h = histograma(k)
    cx, cy = a.curva(h)
    assert np.allclose(cx, h.centros) and math.isclose(cy.sum(), h.n, rel_tol=0.01)
    t = rng.exponential(1.7, 800)
    a = ajustar_distribucion(t, "exponencial")
    (_, tau, dtau), (_, lam, _) = a.parametros
    assert abs(tau - 1.7) < 4 * dtau and math.isclose(lam, 1 / tau)


@pytest.mark.parametrize("dist,datos", [
    ("poisson", [0.5, 1, 2]), ("poisson", [-1, 2, 3]), ("exponencial", [-0.1, 1, 2]), ("normal", [1, 1, 1, 1]),
    ("weibull", [1, 2, 3]),
])
def test_ajuste_datos_invalidos(dist, datos):
    with pytest.raises(ErrorHistograma):
        ajustar_distribucion(datos, dist)


def test_agrupar_hasta_cinco_esperadas():
    obs = np.array([1, 2, 10, 20, 10, 2, 1, 0])
    esp = np.array([0.5, 2.0, 9.0, 21.0, 11.0, 2.5, 1.5, 0.5])
    o, e = _agrupar(obs, esp)
    assert np.all(e >= 5) and o.sum() == obs.sum() and math.isclose(e.sum(), esp.sum())


@pytest.mark.lento
@pytest.mark.parametrize("dist,generar", [
    ("normal", lambda r: r.normal(0, 1, 300)),
    ("poisson", lambda r: r.poisson(4, 300)),
    ("exponencial", lambda r: r.exponential(2, 300)),
])
def test_p_valor_calibrado(rng, dist, generar):
    """Con datos que siguen la distribución, p < 0.05 en ~5 % de los casos."""
    p = np.array([ajustar_distribucion(z := generar(rng), dist, histograma(z)).p for _ in range(400)])
    assert 0.02 < np.mean(p < 0.05) < 0.09 and 0.42 < np.mean(p < 0.5) < 0.58


def test_resumen(rng):
    x = rng.normal(10, 3, 1000)
    r = resumen(x)
    assert r.n == 1000 and math.isclose(r.error_media, r.desviacion / math.sqrt(1000))
    assert r.q1 < r.mediana < r.q3 and abs(r.asimetria) < 0.3 and abs(r.curtosis) < 0.5
    assert dict(r.filas())["n"] == "1000"
