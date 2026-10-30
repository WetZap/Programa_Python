"""Pruebas de la interfaz. Se ejecutan sin pantalla (QT_QPA_PLATFORM=offscreen),
así que funcionan en la CI de Linux, Windows y macOS sin abrir ventanas.
Los ajustes de usuario (QSettings) se redirigen a una carpeta temporal.
"""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

pytestmark = pytest.mark.gui
EJEMPLO = Path(__file__).resolve().parents[1] / "ejemplos" / "descarga_rc.csv"


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path_factory.mktemp("ajustes")))
    a = QApplication.instance() or QApplication([])
    a.setOrganizationName("WetZap-pruebas")
    a.setApplicationName("ajustelab-pruebas")
    return a


@pytest.fixture
def ventana(app, monkeypatch):
    from ajustelab.gui.app import VentanaPrincipal
    from ajustelab.gui.tema import GestorTema

    errores = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: errores.append(a[2]))
    w = VentanaPrincipal(GestorTema(app, "sistema"))
    w.errores = errores
    w.resize(1300, 800)
    w.show()
    yield w
    w.close()


def esperar(app, w, veces=30):
    for _ in range(veces):
        app.processEvents()
        w.esperar_trabajos()
        app.processEvents()
        time.sleep(0.01)
    # el temporizador de «datos cambiados» espera 200 ms
    time.sleep(0.25)
    for _ in range(10):
        app.processEvents()
        w.esperar_trabajos()


def test_tema_claro_oscuro_y_colores(app):
    from ajustelab.gui.tema import GestorTema

    t = GestorTema(app, "oscuro")
    assert t.oscuro and t.estilo == "Fusion"
    oscuro = t.colores()
    t.fijar_preferencia("claro")
    assert not t.oscuro
    claro = t.colores()
    assert set(oscuro) == set(claro) >= {"datos", "ajuste", "texto", "fondo", "excluidos", "rejilla"}
    assert oscuro["fondo"] != claro["fondo"]
    t.fijar_preferencia("sistema")


def test_abrir_y_ajustar(app, ventana):
    assert ventana.abrir(EJEMPLO)
    esperar(app, ventana)
    assert "decimal «,»" in ventana.panel_datos.info.text()
    assert ventana.panel_datos.combos["dy"].currentText() == "dV"
    ventana.p_ajuste.selector.seleccionar_clave("exponencial_fondo")
    ventana.p_ajuste.ajustar()
    esperar(app, ventana)
    res = ventana.p_ajuste.resultado
    assert res is not None and np.allclose(res.p, [4.76, 1.71, 0.32], atol=0.05)
    assert ventana.p_ajuste.tabla.rowCount() == 3
    assert r"\begin{tabular}" in ventana.p_ajuste.latex()


def test_clic_en_un_punto_lo_excluye_y_reajusta(app, ventana):
    from matplotlib.backend_bases import MouseEvent

    ventana.abrir(EJEMPLO)
    ventana.p_ajuste.selector.seleccionar_clave("exponencial_fondo")
    ventana.p_ajuste.ajustar()
    esperar(app, ventana)
    g = ventana.grafica
    g.lienzo.draw()
    px, py = g._puntos_px[4]
    MouseEvent("button_press_event", g.lienzo, px, py, button=1)._process()
    esperar(app, ventana)
    assert ventana.panel_datos.modelo.excluidas == {4}
    assert ventana.p_ajuste.resultado.datos.n == 15
    ventana.grafica.puntoClicado.emit(4)  # segundo clic: vuelve a incluirlo
    esperar(app, ventana)
    assert ventana.p_ajuste.resultado.datos.n == 16


def test_seleccion_y_usar_en_ajuste(app, ventana):
    ventana.abrir(EJEMPLO)
    ventana.pestanas.setCurrentWidget(ventana.p_seleccion)
    ventana.p_seleccion.ejecutar()
    esperar(app, ventana, 60)
    sel = ventana.p_seleccion.seleccion
    assert sel is not None and sel.recomendado.clave == "exponencial_fondo"
    assert ventana.p_seleccion.tabla.rowCount() == len(sel.candidatos)
    ventana.p_seleccion.usar_en_ajuste()
    assert ventana.pestanas.currentWidget() is ventana.p_ajuste
    assert ventana.p_ajuste.resultado.modelo.nombre == "Exponencial con fondo"


def test_cancelar_seleccion(app, ventana):
    ventana.abrir(EJEMPLO)
    ventana.p_seleccion.ejecutar()
    ventana._cancelar()
    esperar(app, ventana)
    assert ventana._trabajo is None
    assert ventana.mensaje.text() in ("Cancelado.", "Listo.")  # pudo terminar antes de cancelar


def test_interpolacion_y_calculos(app, ventana, tmp_path, monkeypatch):
    ventana.abrir(EJEMPLO)
    esperar(app, ventana)
    p = ventana.p_interp
    ventana.pestanas.setCurrentWidget(p)
    p.metodo.setCurrentIndex(p.metodo.findData("pchip"))
    p.interpolar()
    assert p.resultado is not None and p.resultado.metodo == "pchip"
    p.x0.setText("2,5")
    p.a.setText("1")
    p.b.setText("3")
    p.calcular()
    esperar(app, ventana)
    texto = p.salida.toPlainText()
    assert "f(2.5) =" in texto and "∫ f dx de 1 a 3" in texto and "±" in texto
    destino = tmp_path / "tramos.tex"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), "LaTeX (*.tex)"))
    p.exportar()
    assert r"\begin{cases}" in destino.read_text(encoding="utf-8")


def test_interseccion(app, ventana):
    rng = np.random.default_rng(3)
    x = np.r_[np.linspace(0, 5, 8), np.linspace(6, 12, 8)]
    y = np.r_[1.8 * x[:8] + 2, -0.7 * x[8:] + 21] + rng.normal(0, 0.15, 16)
    ventana._cargar(pd.DataFrame({"x": x, "y": y, "dy": 0.15}))
    esperar(app, ventana)
    p = ventana.p_inter
    ventana.pestanas.setCurrentWidget(p)
    p.n.setValue(8)
    p.calcular()
    esperar(app, ventana)
    assert p.resultado is not None and abs(p.resultado.x - 7.6) < 0.4
    assert "Región de confianza" in p.salida.toPlainText()


def test_tabla_edicion_pegado_y_errores(app, ventana):
    m = ventana.panel_datos.modelo
    ventana.tabla_vacia()
    QGuiApplication.clipboard().setText("t;V\n1,0;2,5\n2,0;4,1\n3,0;6,2\n")
    ventana.pegar_tabla_nueva()
    esperar(app, ventana)
    assert m.nombres == ["t", "V"] and np.allclose(m.a_dataframe()["V"], [2.5, 4.1, 6.2])
    assert m.setData(m.index(0, 1), "2,6")
    assert m.a_dataframe().iloc[0, 1] == 2.6
    ventana.panel_datos.vista.selectAll()
    ventana.panel_datos.vista.copiar()
    assert QGuiApplication.clipboard().text().splitlines()[0] == "1\t2.6"
    # σy constante desde el desplegable
    pd_ = ventana.panel_datos
    pd_.combos["dy"].setCurrentText("constante…")
    pd_.constantes["dy"].setText("0,1")
    datos, _ = pd_.datos()
    assert np.allclose(datos.dy, 0.1)
    # Error de usuario: no bloquea y se informa
    ventana.tabla_vacia()
    ventana.p_ajuste.ajustar()
    assert ventana.panel_datos.combos["x"].currentText() == "x"
    assert ventana.panel_datos.combos["y"].currentText() == "y"
    assert ventana.errores and "al menos 2 filas" in ventana.errores[-1]


def test_exportar_grafica(app, ventana, tmp_path):
    ventana.abrir(EJEMPLO)
    esperar(app, ventana)
    for ext in ("png", "pdf", "svg"):
        ruta = tmp_path / f"g.{ext}"
        ventana.grafica.guardar(str(ruta))
        assert ruta.stat().st_size > 1000
