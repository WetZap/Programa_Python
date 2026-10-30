"""El motor de ajuste frente a soluciones analíticas y a SciPy."""
import numpy as np
import pytest
from scipy.optimize import curve_fit

from ajustelab import Datos, ErrorAjuste, ajustar, desde_expresion
from ajustelab.ajuste import METODO_OLS, METODO_VE, METODO_WLS

rng = np.random.default_rng(42)
X = np.linspace(1, 10, 15)
DY = 0.2 + 0.05 * X  # heterocedástico
Y = 2.0 * X + 5.0 + rng.normal(0, DY)


def test_lineal_vs_formulas_cerradas():
    """y = ax + b ponderado: fórmulas de las prácticas (opción 5 del script antiguo)."""
    w = 1 / DY**2
    S, Sx, Sy, Sxx, Sxy = w.sum(), (w * X).sum(), (w * Y).sum(), (w * X * X).sum(), (w * X * Y).sum()
    D = S * Sxx - Sx**2
    a, b = (S * Sxy - Sx * Sy) / D, (Sxx * Sy - Sx * Sxy) / D
    res = ajustar(Datos(X, Y, dy=DY), "lineal")
    assert res.metodo == METODO_WLS
    assert np.allclose(res.p, [a, b])
    assert np.allclose(res.sigma_p, [np.sqrt(S / D), np.sqrt(Sxx / D)])
    assert np.isclose(res.cov[0, 1], -Sx / D)
    assert res.nu == X.size - 2


def test_proporcional_corregido():
    """y = ax: a = Σwxy/Σwx², σ_a = 1/√Σwx², ν = n − 1 (fallo de la opción 6 antigua)."""
    w = 1 / DY**2
    res = ajustar(Datos(X, Y, dy=DY), "proporcional")
    assert np.isclose(res.p[0], np.sum(w * X * Y) / np.sum(w * X**2))
    assert np.isclose(res.sigma_p[0], 1 / np.sqrt(np.sum(w * X**2)))
    assert res.nu == X.size - 1


def test_polinomio_vs_polyfit():
    y = 0.3 * X**3 - X**2 + 2 + rng.normal(0, DY)
    res = ajustar(Datos(X, y, dy=DY), "cubico")
    p, cov = np.polyfit(X, y, 3, w=1 / DY, cov="unscaled")
    assert np.allclose(res.p, p[::-1])
    assert np.allclose(res.cov, cov[::-1, ::-1])


def test_no_lineal_vs_curve_fit():
    t = np.linspace(0, 6, 25)
    s = np.full_like(t, 0.05)
    y = 3 * np.exp(-t / 1.5) + 0.4 + rng.normal(0, s)
    res = ajustar(Datos(t, y, dy=s), "A*exp(-x/tau) + C")
    popt, pcov = curve_fit(lambda x, A, tau, C: A * np.exp(-x / tau) + C, t, y, p0=[3, 1.5, 0.4], sigma=s,
                           absolute_sigma=True)
    assert np.allclose(res.p, popt, rtol=1e-6)
    assert np.allclose(res.cov, pcov, rtol=1e-4)


def test_multistart_rescata_p0_malo():
    t = np.linspace(0, 100, 40)
    y = 50 * np.exp(-t / 30.0) + 2
    res = ajustar(Datos(t, y, dy=0.01), "A*exp(-x/tau) + C", p0=[1, -1, 0])
    assert np.allclose(res.p, [50, 30, 2], rtol=1e-6)


def test_ols_vs_curve_fit():
    res = ajustar(Datos(X, Y), "lineal")
    popt, pcov = curve_fit(lambda x, a, b: a * x + b, X, Y)
    assert res.metodo == METODO_OLS and not res.errores_absolutos
    assert np.allclose(res.p, popt) and np.allclose(res.cov, pcov)


def test_varianza_efectiva_recta_analitica():
    """Recta con σx, σy constantes: σ_eff² = σy² + a²σx² es constante, así que
    la pendiente coincide con WLS y la covarianza se escala por σ_eff²/σy²."""
    sx, sy = 0.1, 0.3
    res_ve = ajustar(Datos(X, Y, dx=sx, dy=sy), "lineal")
    res_w = ajustar(Datos(X, Y, dy=sy), "lineal")
    a = res_ve.p[0]
    assert res_ve.metodo == METODO_VE
    assert np.allclose(res_ve.p, res_w.p)
    assert np.allclose(res_ve.cov, res_w.cov * (sy**2 + a**2 * sx**2) / sy**2)


def test_dx_cero_equivale_a_wls():
    res_ve = ajustar(Datos(X, Y, dx=np.zeros_like(X), dy=DY), "lineal")
    res_w = ajustar(Datos(X, Y, dy=DY), "lineal")
    assert res_ve.metodo == METODO_WLS  # dx todo ceros = no hay errores en x
    assert np.allclose(res_ve.p, res_w.p)


def test_solo_dx():
    res = ajustar(Datos(X, Y, dx=0.1), "lineal")
    assert res.metodo == METODO_VE and res.convergido
    assert np.allclose(res.sigma, abs(res.p[0]) * 0.1)


def test_puntos_excluidos():
    y = Y.copy()
    y[3] += 50
    d = Datos(X, y, dy=DY)
    d.excluir(3)
    res = ajustar(d, "lineal")
    assert res.datos.n == X.size - 1
    assert abs(res.p[0] - 2) < 0.2


def test_limites():
    res = ajustar(Datos(X, Y, dy=DY), "lineal", limites=([-np.inf, -np.inf], [np.inf, 4.0]))
    assert res.p[1] <= 4.0 + 1e-9


def test_errores_de_uso():
    with pytest.raises(ErrorAjuste):
        ajustar(Datos([1.0, 2.0], [1.0, 2.0]), "cuadratico")  # n < k
    with pytest.raises(ErrorAjuste):
        ajustar(Datos([-1.0, 1.0, 2.0], [1.0, 1.0, 2.0]), "potencia")  # dominio x > 0
    with pytest.raises(ErrorAjuste):
        ajustar(Datos(X, Y), "A*exp(b*x)", p0=[1.0])


def test_degenerado():
    m = desde_expresion("a*b*x")  # solo el producto a·b está determinado
    res = ajustar(Datos(X, Y, dy=DY), m)
    assert not res.convergido
    assert any("degenerados" in a for a in res.avisos)


def test_fijos_equivale_a_modelo_reducido():
    """Fijar b = 5 en a·x + b equivale a ajustar a·x a los datos y − 5."""
    res = ajustar(Datos(X, Y, dy=DY), "lineal", fijos={"b": 5.0})
    ref = ajustar(Datos(X, Y - 5.0, dy=DY), "proporcional")
    assert res.nombres == ("a",) and res.fijos == {"b": 5.0}
    assert np.allclose(res.p, ref.p) and np.allclose(res.cov, ref.cov)
    assert res.nu == X.size - 1
    assert "(fijo)" in res.resumen()


def test_fijos_no_lineal_y_limites():
    t = np.linspace(0, 6, 25)
    y = 3 * np.exp(-t / 1.5) + 0.4 + rng.normal(0, 0.02, t.size)
    res = ajustar(Datos(t, y, dy=0.02), "exponencial_fondo", fijos={"C": 0.4}, limites=([0, 1.0], [10, 2.0]))
    assert res.convergido and abs(res.p[1] - 1.5) < 0.05 and 1.0 <= res.p[1] <= 2.0


def test_sigma_f_e_inversa_recta():
    """Para y = ax + b: x0 = (y0 − b)/a y σ_x = √(σ_f² + σ_y0²)/|a| (método delta)."""
    res = ajustar(Datos(X, Y, dy=DY), "lineal")
    (a, b), C = res.p, res.cov
    x0 = 4.3
    assert np.isclose(res.sigma_f(x0)[0], np.sqrt(C[0, 0] * x0**2 + C[1, 1] + 2 * x0 * C[0, 1]))
    y0, sy0 = 12.0, 0.3
    (xs, sx), = res.inversa(y0, sy0)
    assert np.isclose(xs, (y0 - b) / a)
    assert np.isclose(sx, np.hypot(res.sigma_f(xs)[0], sy0) / abs(a))
    assert res.inversa(1e6) == []  # fuera del rango de los datos
    assert len(res.inversa(1e6, intervalo=(0, 1e6))) == 1
