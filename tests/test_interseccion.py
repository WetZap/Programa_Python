import numpy as np
import pytest
from scipy import stats

from ajustelab import Datos, ajustar, obtener
from ajustelab.interseccion import ErrorInterseccion, dividir, intersecar, intersecar_datos

X1 = np.linspace(0, 5, 10)
X2 = np.linspace(4, 10, 10)


def _rectas(rng, s=0.2):
    d1 = Datos(X1, 2 * X1 + 1 + rng.normal(0, s, X1.size), dy=s)
    d2 = Datos(X2, -X2 + 20 + rng.normal(0, s, X2.size), dy=s)
    return d1, d2


def test_rectas_analitico_y_covarianza_numerica():
    I = intersecar_datos(*_rectas(np.random.default_rng(0)))
    (a1, b1), (a2, b2) = I.ajuste1.p, I.ajuste2.p
    assert np.isclose(I.x, (b2 - b1) / (a1 - a2))
    assert np.isclose(I.y, a1 * I.x + b1)

    # Jacobiano por diferencias finitas de (x*, y*) respecto a (a1, b1, a2, b2)
    def corte(p):
        x = (p[3] - p[1]) / (p[0] - p[2])
        return np.array([x, p[0] * x + p[1]])

    p = np.array([a1, b1, a2, b2])
    h = 1e-7
    G = np.column_stack([(corte(p + h * e) - corte(p - h * e)) / (2 * h) for e in np.eye(4)])
    C = np.zeros((4, 4))
    C[:2, :2], C[2:, 2:] = I.ajuste1.cov, I.ajuste2.cov
    assert np.allclose(I.cov, G @ C @ G.T, rtol=1e-5)
    assert any("extrapolación" in a for a in I.avisos)  # x* ≈ 6.3 está fuera de [0, 5]


@pytest.mark.lento
def test_monte_carlo_pulls_y_correlacion():
    rng = np.random.default_rng(1)
    x_real, y_real = 19 / 3, 2 * 19 / 3 + 1
    pulls, rhos, muestras = [], [], []
    for _ in range(500):
        I = intersecar_datos(*_rectas(rng, s=0.3))
        pulls.append([(I.x - x_real) / I.sigma_x, (I.y - y_real) / I.sigma_y])
        rhos.append(I.rho)
        muestras.append([I.x, I.y])
    pulls = np.array(pulls)
    assert np.all(np.abs(pulls.mean(axis=0)) < 0.2)
    assert np.all(np.abs(pulls.std(axis=0) - 1) < 0.1)
    assert abs(np.corrcoef(np.array(muestras).T)[0, 1] - np.mean(rhos)) < 0.1


def test_elipse_cobertura():
    I = intersecar_datos(*_rectas(np.random.default_rng(2)))
    ancho, alto, ang = I.elipse(0.6827)
    # Fracción de puntos gaussianos con esa covarianza dentro de la elipse
    pts = np.random.default_rng(3).multivariate_normal([0, 0], I.cov, 20000)
    t = np.radians(ang)
    u = pts[:, 0] * np.cos(t) + pts[:, 1] * np.sin(t)
    v = -pts[:, 0] * np.sin(t) + pts[:, 1] * np.cos(t)
    dentro = (u / (ancho / 2)) ** 2 + (v / (alto / 2)) ** 2 <= 1
    assert abs(dentro.mean() - 0.6827) < 0.015
    assert np.isclose(ancho / 2, np.sqrt(stats.chi2.ppf(0.6827, 2) * np.linalg.eigvalsh(I.cov).max()))


def test_curvas_no_lineales():
    rng = np.random.default_rng(4)
    t = np.linspace(0, 5, 25)
    r1 = ajustar(Datos(t, 5 * np.exp(-t / 1.5) + rng.normal(0, 0.05, t.size), dy=0.05), "A*exp(-x/tau)")
    r2 = ajustar(Datos(t, 0.5 * t + rng.normal(0, 0.05, t.size), dy=0.05), "proporcional")
    I = intersecar(r1, r2)
    assert np.isclose(r1.evaluar(I.x), r2.evaluar(I.x), atol=1e-10)
    assert abs(I.x - 2.23) < 0.1 and I.sigma_x > 0


def test_varios_cortes_paralelas_y_sin_corte():
    x = np.linspace(0, 10, 50)
    r_seno = ajustar(Datos(x, 2 * np.sin(1.3 * x) + 0.2, dy=0.01), obtener("seno"))
    r_cte = ajustar(Datos(x, np.full_like(x, 0.2), dy=0.01), "constante")
    cortes = intersecar(r_seno, r_cte, intervalo=(0.5, 10), todas=True)
    assert np.allclose([c.x for c in cortes], np.arange(1, 5) * np.pi / 1.3, atol=1e-6)
    unico = intersecar(r_seno, r_cte, intervalo=(0.5, 10))
    assert any("cortes" in a for a in unico.avisos)

    d = Datos(X1, 2 * X1 + 1, dy=0.1)
    d_par = Datos(X1, 2 * X1 + 5, dy=0.1)
    with pytest.raises(ErrorInterseccion):
        intersecar_datos(d, d_par)
    with pytest.raises(ErrorInterseccion):
        intersecar(ajustar(d, "lineal"), ajustar(d, "lineal"))  # misma recta: g ≡ 0


def test_x0_y_mismos_datos():
    d1, d2 = _rectas(np.random.default_rng(5))
    I = intersecar_datos(d1, d2, x0=5.0)
    assert np.isclose(I.x, intersecar_datos(d1, d2).x)
    I2 = intersecar_datos(d1, d1, "lineal", "cuadratico")
    assert any("mismos datos" in a for a in I2.avisos)


def test_dividir():
    d = Datos(np.arange(10.0), np.arange(10.0), dy=0.1)
    a, b = dividir(d, 4)
    assert a.n == 4 and b.n == 6 and b.x[0] == 4
    with pytest.raises(ValueError):
        dividir(d, 10)
