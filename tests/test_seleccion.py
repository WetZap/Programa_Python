"""Catálogo completo y selección automática de modelo."""
import numpy as np
import pytest
from casos_sinteticos import CASOS, EQUIVALENTES, generar

from ajustelab import CANDIDATOS_AUTO, CATALOGO, Datos, ajustar, seleccionar


# --- catálogo: cada modelo recupera sus parámetros -----------------------
@pytest.mark.parametrize("clave", list(CASOS))
def test_catalogo_recupera_parametros(clave):
    x, y, s = generar(clave, semilla=0)
    res = ajustar(Datos(x, y, dy=s), CATALOGO[clave])
    p_real = np.array(CASOS[clave][1])
    assert res.convergido
    assert np.max(np.abs((res.p - p_real) / res.sigma_p)) < 4


@pytest.mark.parametrize("clave", [k for k, m in CATALOGO.items() if m.estimador_p0 is not None])
def test_p0_sin_ruido_cerca_del_valor_real(clave):
    """Los estimadores de p0 deben caer cerca de la solución con datos limpios."""
    x, p, _ = CASOS[clave]
    m = CATALOGO[clave]
    p0 = m.p0(x, m(x, *p))
    assert np.allclose(p0, p, rtol=0.25, atol=0.15 * np.max(np.abs(p))), (p0, p)


def test_catalogo_completo():
    assert len(CATALOGO) >= 20
    assert set(CANDIDATOS_AUTO) <= set(CATALOGO)


def test_plausibilidad():
    g = CATALOGO["gaussiana"]
    x = np.linspace(-5, 5, 30)
    assert g.comprobar_plausibilidad([1, 0, 1, 0], x) is None
    assert "fuera del rango" in g.comprobar_plausibilidad([1, 20, 1, 0], x)
    seno = CATALOGO["seno"]
    assert "Nyquist" in seno.comprobar_plausibilidad([1, 100, 0, 0], x)
    assert "medio periodo" in seno.comprobar_plausibilidad([1, 0.01, 0, 0], x)


# --- selección -----------------------------------------------------------
@pytest.mark.parametrize("clave", ["lineal", "cuadratico", "exponencial_fondo", "potencia", "gaussiana",
                                   "lorentziana", "logistica", "seno_amortiguado", "carga"])
def test_selecciona_familia_correcta(clave):
    x, y, s = generar(clave, semilla=1)
    sel = seleccionar(Datos(x, y, dy=s))
    assert sel.recomendado.clave == EQUIVALENTES.get(clave, clave), sel.resumen()


def test_estructura_resultado():
    x, y, s = generar("exponencial_fondo")
    llamadas = []
    sel = seleccionar(Datos(x, y, dy=s), progreso=lambda i, n, nombre: llamadas.append(i))
    validos = sel.validos
    assert [c.criterio for c in validos] == sorted(c.criterio for c in validos)
    assert validos[0].delta == 0
    assert np.isclose(sum(c.peso for c in validos), 1)
    assert llamadas[-1] == len(CANDIDATOS_AUTO)
    tabla = sel.tabla()
    assert len(tabla) == len(CANDIDATOS_AUTO) and tabla["recomendado"].sum() == 1
    assert "Recomendado" in sel.resumen()


def test_exclusiones():
    x = np.linspace(-2, 2, 6)  # x ≤ 0 y solo 6 puntos
    y = 3 * x + 1 + np.random.default_rng(0).normal(0, 0.1, x.size)
    sel = seleccionar(Datos(x, y, dy=0.1))
    assert "dominio" in sel["potencia"].motivo
    assert "ν" in sel["seno_amortiguado"].motivo  # 6 − 5 = 1 < 2
    assert sel.recomendado.clave == "lineal"


def test_modelos_propios_y_lista_reducida():
    x, y, s = generar("cubico")
    sel = seleccionar(Datos(x, y, dy=s), modelos=["lineal", "cuadratico"], extra=["c0 + c3*x**3 + c1*x + c2*x**2"])
    assert len(sel.candidatos) == 3
    assert sel.recomendado.modelo.k == 4


def test_criterio_bic_y_avisos_sin_errores():
    x, y, _ = generar("lineal")
    sel = seleccionar(Datos(x, y), criterio="bic")
    assert sel.criterio == "bic" and sel.recomendado.clave == "lineal"
    assert any("Sin incertidumbres" in a for a in sel.avisos)
    with pytest.raises(ValueError):
        seleccionar(Datos(x, y), criterio="chi2")


def test_errores_subestimados_ningun_compatible():
    x, y, s = generar("lineal")
    sel = seleccionar(Datos(x, y, dy=s / 10), modelos=["constante", "lineal", "cuadratico"])
    assert any("Ningún modelo es compatible" in a for a in sel.avisos)


def test_varianza_efectiva_aviso():
    x, y, s = generar("lineal")
    sel = seleccionar(Datos(x, y, dx=0.05, dy=s), modelos=["lineal", "cuadratico"])
    assert any("aproximada" in a for a in sel.avisos)


@pytest.mark.lento
def test_tasa_de_acierto():
    """Tasa de acierto sobre todos los casos con 3 semillas (medida: ≈95 %).
    Los fallos son modelos con un parámetro más que absorben ruido."""
    aciertos = total = 0
    for clave in CASOS:
        for semilla in range(10, 13):
            x, y, s = generar(clave, semilla)
            total += 1
            aciertos += seleccionar(Datos(x, y, dy=s)).recomendado.clave == EQUIVALENTES.get(clave, clave)
    assert aciertos / total >= 0.9, f"{aciertos}/{total}"
