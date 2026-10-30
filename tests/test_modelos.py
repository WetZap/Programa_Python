import numpy as np
import pytest

from ajustelab.modelos import CATALOGO, ErrorModelo, desde_expresion, obtener, polinomio


def test_parametros_en_orden_de_aparicion():
    m = desde_expresion("A*exp(-x/tau) + C")
    assert m.parametros == ("A", "tau", "C")
    assert not m.lineal


def test_nombres_reservados_de_sympy_son_parametros():
    m = desde_expresion("gamma*x + beta + E*I")
    assert set(m.parametros) == {"gamma", "beta", "E", "I"}


def test_xor_y_constantes():
    m = desde_expresion("a*x^2 + e*pi")
    assert m.parametros == ("a",)
    assert np.isclose(m(2.0, 1.0), 4 + np.e * np.pi)


@pytest.mark.parametrize("expr, lineal", [
    ("a*x + b", True), ("a/x + b", True), ("a*log(x) + b*sqrt(x)", True), ("a*x + 5", True),
    ("A*exp(b*x)", False), ("A*sin(w*x + phi)", False),
])
def test_deteccion_linealidad(expr, lineal):
    assert desde_expresion(expr).lineal is lineal


def test_derivadas_analiticas_vs_numericas():
    m = desde_expresion("A*exp(-x/tau)*cos(w*x) + C")
    x = np.linspace(0.1, 3, 7)
    p = np.array([2.0, 1.3, 4.0, 0.5])
    h = 1e-6
    num_dx = (m(x + h, *p) - m(x - h, *p)) / (2 * h)
    assert np.allclose(m.derivada_x(x, p), num_dx, atol=1e-6)
    J = m.jacobiano(x, p)
    for j in range(m.k):
        dp = np.zeros_like(p)
        dp[j] = h
        assert np.allclose(J[:, j], (m(x, *(p + dp)) - m(x, *(p - dp))) / (2 * h), atol=1e-6)


def test_constante_se_difunde():
    m = desde_expresion("c")
    assert m(np.arange(4.0), 3.0).shape == (4,)
    assert m.jacobiano(np.arange(4.0), [3.0]).shape == (4, 1)


@pytest.mark.parametrize("mala", ["", "__import__('os')", "x.real", "a*x; b", "a**", "lambda: 1"])
def test_expresiones_rechazadas(mala):
    with pytest.raises(ErrorModelo):
        desde_expresion(mala)


def test_catalogo_y_obtener():
    assert {"proporcional", "lineal", "cuadratico", "cubico", "exponencial", "potencia"} <= set(CATALOGO)
    assert obtener("Lineal") is CATALOGO["lineal"]
    assert obtener("polinomio_4").k == 5
    assert polinomio(1).lineal
    assert obtener("a*sin(x)").parametros == ("a",)


def test_p0_linealizacion():
    x = np.linspace(1, 5, 10)
    assert np.allclose(CATALOGO["exponencial"].p0(x, 3 * np.exp(-0.5 * x)), [3, -0.5])
    assert np.allclose(CATALOGO["potencia"].p0(x, 2 * x**1.5), [2, 1.5])
    assert not CATALOGO["potencia"].dominio_valido(np.array([-1.0, 1.0]))
