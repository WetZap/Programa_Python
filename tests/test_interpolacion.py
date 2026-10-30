import numpy as np
import pytest

from ajustelab import Datos
from ajustelab.interpolacion import METODOS, ErrorInterpolacion, interpolar

X = np.linspace(0, 2 * np.pi, 15)
SENO = Datos(X, np.sin(X))
CUBICO = lambda x: 0.5 * x**3 - 2 * x**2 + x - 3  # noqa: E731
DCUBICO = lambda x: 1.5 * x**2 - 4 * x + 1  # noqa: E731
XC = np.array([-2.0, -1.2, 0.0, 0.5, 1.7, 3.0, 4.1])


def _kw(m):
    return {"derivadas_extremos": (1.0, 1.0)} if m == "clamped" else {}


@pytest.mark.parametrize("metodo", [m for m in METODOS if m != "suavizado"])
def test_pasa_por_los_nodos(metodo):
    f = interpolar(SENO, metodo, **_kw(metodo))
    assert np.allclose(f(X), np.sin(X), atol=1e-10)


@pytest.mark.parametrize("metodo, kw", [
    ("not-a-knot", {}), ("polinomio", {}), ("clamped", {"derivadas_extremos": (DCUBICO(-2.0), DCUBICO(4.1))})])
def test_reproduce_cubico_exacto(metodo, kw):
    f = interpolar(Datos(XC, CUBICO(XC)), metodo, **kw)
    xx = np.linspace(-2, 4.1, 300)
    assert np.allclose(f(xx), CUBICO(xx), atol=1e-9)


def test_natural_segunda_derivada_nula_en_extremos():
    f = interpolar(SENO, "natural")
    assert np.allclose(f.derivada([X[0], X[-1]], orden=2), 0, atol=1e-12)


def test_periodico():
    f = interpolar(SENO, "periodico")
    assert np.isclose(*f.derivada([X[0], X[-1]]))
    with pytest.raises(ErrorInterpolacion):
        interpolar(Datos(X, np.cos(X) + X), "periodico")


def test_pchip_no_sobreoscila_y_spline_si():
    x = np.arange(10.0)
    y = np.where(x < 5, 0.0, 1.0)  # escalón
    xx = np.linspace(0, 9, 2000)
    p = interpolar(Datos(x, y), "pchip")(xx)
    assert p.min() >= -1e-12 and p.max() <= 1 + 1e-12 and np.all(np.diff(p) >= -1e-12)
    s = interpolar(Datos(x, y), "natural")(xx)
    assert s.min() < -0.01 and s.max() > 1.01


def test_derivada_integral_inversa_extremos():
    f = interpolar(Datos(np.linspace(0, 2 * np.pi, 40), np.sin(np.linspace(0, 2 * np.pi, 40))), "natural")
    xx = np.linspace(0.5, 5.5, 50)
    assert np.allclose(f.derivada(xx), np.cos(xx), atol=2e-3)
    assert np.isclose(f.integral(0, np.pi), 2.0, atol=1e-4)
    assert np.allclose(f.inversa(0.5), [np.pi / 6, 5 * np.pi / 6], atol=1e-4)
    assert np.allclose(f.inversa(0.0), [0, np.pi, 2 * np.pi], atol=1e-6)
    ext = f.extremos()
    assert [t for _, _, t in ext] == ["máximo", "mínimo"]
    assert np.allclose([e[0] for e in ext], [np.pi / 2, 3 * np.pi / 2], atol=1e-3)


def test_extremos_lineal_en_nodos():
    f = interpolar(Datos([0.0, 1, 2, 3, 4], [0.0, 2, 1, 3, 0]), "lineal")
    assert [(x, t) for x, _, t in f.extremos()] == [(1.0, "máximo"), (2.0, "mínimo"), (3.0, "máximo")]


def test_extrapolacion():
    f = interpolar(SENO, "natural")
    assert np.isnan(f(-1.0))
    with pytest.raises(ErrorInterpolacion):
        f.integral(-1, 1)
    g = interpolar(SENO, "natural", extrapolar=True)
    assert np.isfinite(g(-1.0))


def test_duplicados_promediados():
    f = interpolar(Datos([0.0, 1, 1, 2], [0.0, 1, 3, 2], dy=[0.1, 0.1, 0.2, 0.1]), "lineal")
    w = np.array([1 / 0.1**2, 1 / 0.2**2])
    assert np.isclose(f(1.0), np.sum(w * [1, 3]) / w.sum())
    assert np.isclose(f.dy[1], 1 / np.sqrt(w.sum()))
    assert any("repetida" in a for a in f.avisos)


def test_suavizado_con_sigma_se_acerca_mas_a_la_verdad():
    """Con ruido, el spline de suavizado reconstruye la curva verdadera mejor que
    un interpolante (promedio de 5 realizaciones)."""
    x = np.linspace(0, 10, 60)
    xx = np.linspace(0, 10, 500)
    v = np.sin(xx) + 0.1 * xx
    s = np.where(x > 5, 0.25, 0.15)
    err_suav, err_interp = [], []
    for semilla in range(5):
        y = np.sin(x) + 0.1 * x + np.random.default_rng(semilla).normal(0, s)
        f = interpolar(Datos(x, y, dy=s), "suavizado")
        assert np.sum(((y - f(x)) / s) ** 2) < 1.5 * x.size
        err_suav.append(np.sqrt(np.mean((f(xx) - v) ** 2)))
        err_interp.append(np.sqrt(np.mean((interpolar(Datos(x, y), "natural")(xx) - v) ** 2)))
    assert np.mean(err_suav) < 0.6 * np.mean(err_interp)


def test_suavizado_gcv_sin_sigma():
    x = np.linspace(0, 5, 30)
    y = x**2 + np.random.default_rng(1).normal(0, 0.3, x.size)
    f = interpolar(Datos(x, y), "suavizado")
    assert np.max(np.abs(f(x) - x**2)) < 1.0


def test_monte_carlo_lineal_analitico():
    s1, s2 = 0.3, 0.4
    f = interpolar(Datos([0.0, 1.0, 2.0], [1.0, 2.0, 0.0], dy=[s1, s2, 0.1]), "lineal")
    sigma = f.sigma(0.5, n=4000)
    assert np.isclose(sigma, 0.5 * np.hypot(s1, s2), rtol=0.05)
    r = f.monte_carlo(lambda g: g.integral(0, 1), n=4000)
    assert np.isclose(r.sigma, 0.5 * np.hypot(s1, s2), rtol=0.05)  # trapecio: (y0 + y1)/2
    with pytest.raises(ErrorInterpolacion):
        interpolar(SENO, "lineal").sigma(1.0)


@pytest.mark.parametrize("metodo", ["lineal", "natural", "pchip", "suavizado", "polinomio"])
def test_exportar_tramos(metodo):
    rng = np.random.default_rng(2)
    d = Datos(X, np.sin(X) + rng.normal(0, 0.01, X.size), dy=0.01)
    f = interpolar(d, metodo)
    tramos = f.tramos()
    for t in tramos:
        xm = np.linspace(t.x_ini, t.x_fin, 5)
        assert np.allclose(t(xm), f(xm), atol=1e-9)
    # El texto se puede evaluar y reproduce la curva
    for i, linea in enumerate(f.exportar_tramos("txt").splitlines()[2:]):
        expr = linea.split("C(x) = ")[1]
        xm = (tramos[i].x_ini + tramos[i].x_fin) / 2
        assert np.isclose(eval(expr, {"x": xm}), f(xm), atol=1e-7)
    csv = np.loadtxt(f.exportar_tramos("csv").splitlines(), delimiter=",", skiprows=1, ndmin=2)
    assert csv.shape[0] == len(tramos)
    assert r"\begin{cases}" in f.exportar_tramos("latex")


def test_errores_de_uso():
    with pytest.raises(ErrorInterpolacion):
        interpolar(SENO, "inventado")
    with pytest.raises(ErrorInterpolacion):
        interpolar(SENO, "clamped")
    with pytest.raises(ErrorInterpolacion):
        interpolar(Datos([0.0, 1, 2], [0.0, 1, 0]), "suavizado")
    f = interpolar(Datos(np.arange(15.0), np.arange(15.0) ** 2), "polinomio")
    assert any("Runge" in a for a in f.avisos)
