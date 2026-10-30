"""Pruebas de la interfaz. Se ejecutan sin pantalla (QT_QPA_PLATFORM=offscreen),
así que funcionan en la CI de Linux, Windows y macOS sin abrir ventanas.
Los ajustes de usuario (QSettings) se redirigen a una carpeta temporal.
"""
import os
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPixmap, QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

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
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = VentanaPrincipal(GestorTema(app, "sistema"))
    w.errores = errores
    w.resize(1300, 820)
    w.show()
    yield w
    w.pila.setClean()
    w.close()


def esperar(app, w, veces=30):
    for _ in range(veces):
        app.processEvents()
        w.esperar_trabajos()
        app.processEvents()
        time.sleep(0.01)
    time.sleep(0.25)  # el temporizador de «datos cambiados» espera 200 ms
    for _ in range(10):
        app.processEvents()
        w.esperar_trabajos()


def arrastrar(lienzo, desde, hasta):
    from matplotlib.backend_bases import MouseEvent

    MouseEvent("button_press_event", lienzo, *desde, button=1)._process()
    MouseEvent("motion_notify_event", lienzo, *hasta, button=1)._process()
    MouseEvent("button_release_event", lienzo, *hasta, button=1)._process()


def abrir_y_ajustar(app, w, clave="exponencial_fondo"):
    w.abrir(EJEMPLO)
    esperar(app, w)
    w.p_ajuste.selector.seleccionar_clave(clave)
    w.p_ajuste.ajustar()
    esperar(app, w)
    return w.p_ajuste.resultado


# --- tema, estilo e iconos ----------------------------------------------------
def test_tema_estilo_e_iconos(app):
    from ajustelab.gui.estilo import hoja_estilo
    from ajustelab.gui.iconos import _DIBUJOS, icono
    from ajustelab.gui.tema import GestorTema

    t = GestorTema(app, "oscuro")
    assert t.oscuro and t.estilo == "Fusion"
    oscuro = t.colores()
    qss = hoja_estilo(oscuro, True, True)
    assert "QLabel#chip" in qss and "indicator" in qss  # casillas visibles en Fusion oscuro
    t.fijar_preferencia("claro")
    assert not t.oscuro and t.colores()["fondo"] != oscuro["fondo"]
    t.fijar_preferencia("sistema")
    for nombre in _DIBUJOS:
        pm = icono(nombre).pixmap(24, 24)
        assert not pm.isNull() and pm.toImage().pixelColor(12, 12) is not None


def test_bienvenida_y_ejemplos(app, ventana):
    from ajustelab.gui import ejemplos

    assert ventana.centro.currentWidget() is ventana.bienvenida
    for clave in ejemplos.EJEMPLOS:
        ventana.abrir_ejemplo(clave)
        esperar(app, ventana, 5)
        assert ventana.centro.currentWidget() is ventana.grafica
        assert ventana.obtener_datos(silencioso=True) is not None
    ventana.nueva_sesion()
    assert ventana.centro.currentWidget() is ventana.bienvenida


# --- ajuste -------------------------------------------------------------------
def test_abrir_ajustar_resumen(app, ventana):
    res = abrir_y_ajustar(app, ventana)
    assert res is not None and np.allclose(res.p, [4.76, 1.71, 0.32], atol=0.05)
    p = ventana.p_ajuste
    assert p.chip.property("estado") == "bueno" and "Compatible" in p.chip.text()
    assert p.tiles["n"].valor.text() == "16 · 13"
    assert p.tabla.item(1, 5).text() == "1.71 ± 0.05"
    assert r"\begin{tabular}" in p.latex()
    assert "decimal «,»" in ventana.panel_datos.info.text()


def test_vista_previa_y_estimar(app, ventana):
    ventana.abrir(EJEMPLO)
    esperar(app, ventana)
    p = ventana.p_ajuste
    p.selector.seleccionar_clave("exponencial_fondo")
    esperar(app, ventana, 5)
    valores = p.tabla.valores()
    assert all(v["inicial"] is not None for v in valores.values())  # estimados al elegir el modelo
    escena = p.escena(*ventana.obtener_datos())
    assert escena.previa is not None and escena.previa[0].parametros == ("A", "tau", "C")
    p.previa.setChecked(False)
    assert p.escena(*ventana.obtener_datos()).previa is None


def test_parametros_fijos_limites_y_coherencia(app, ventana):
    abrir_y_ajustar(app, ventana)
    t = ventana.p_ajuste.tabla
    c, tau = t.nombres.index("C"), t.nombres.index("tau")
    t.item(c, 1).setText("0,3")
    t.item(c, 2).setCheckState(Qt.Checked)
    t.item(tau, 3).setText("1")
    t.item(tau, 4).setText("2")
    ventana.p_ajuste.ajustar()
    esperar(app, ventana)
    r = ventana.p_ajuste.resultado
    assert r.fijos == {"C": 0.3} and r.nombres == ("A", "tau") and 1 <= r.p[1] <= 2
    assert t.item(c, 5).text() == "0.3 (fijo)"
    t.item(tau, 3).setText("3")  # mínimo > máximo
    assert any("mínimo" in e for e in t.errores())
    n_errores = len(ventana.errores)
    ventana.p_ajuste.ajustar()
    assert len(ventana.errores) == n_errores + 1  # no ajusta y avisa
    t.item(tau, 3).setText("")
    ventana.p_ajuste.usar_resultado_como_iniciales()
    assert abs(t.valores()["A"]["inicial"] - r.p[0]) < 1e-6


def test_evaluar_y_coma_decimal(app, ventana):
    abrir_y_ajustar(app, ventana)
    p = ventana.p_ajuste
    p.ev_x.setText("1")
    p.ev_y.setText("2")
    p.ev_sy.setText("0,04")
    p.evaluar()
    texto = p.ev_salida.text()
    assert "f(1) =" in texto and "x = 1.78" in texto
    ventana.a_coma.setChecked(True)
    esperar(app, ventana, 5)
    assert "0,78" in p.chip.text() and p.tiles["chi2"].valor.text() == "0,683"
    assert "{,}" in p.latex()
    ventana.a_coma.setChecked(False)


# --- interacción con la gráfica --------------------------------------------
def test_clic_region_rango_y_deshacer(app, ventana):
    abrir_y_ajustar(app, ventana)
    g = ventana.grafica
    g.lienzo.draw()
    # clic en un punto
    from matplotlib.backend_bases import MouseEvent

    MouseEvent("button_press_event", g.lienzo, *g._puntos_px[4], button=1)._process()
    esperar(app, ventana)
    assert ventana.panel_datos.modelo.excluidas == {4} and ventana.p_ajuste.resultado.datos.n == 15
    # región alrededor de los puntos 7 y 8
    g.lienzo.draw()
    pts = g._puntos_px[[7, 8]]
    g.b_region.setChecked(True)
    arrastrar(g.lienzo, pts.min(axis=0) - 8, pts.max(axis=0) + 8)
    esperar(app, ventana)
    assert ventana.panel_datos.modelo.excluidas == {4, 7, 8} and not g.b_region.isChecked()
    assert ventana.p_ajuste.resultado.datos.n == 13
    # rango de ajuste
    g.lienzo.draw()
    ax = g._ax
    g.b_rango.setChecked(True)
    arrastrar(g.lienzo, ax.transData.transform((1.0, 2.0)), ax.transData.transform((5.0, 2.0)))
    esperar(app, ventana)
    lo, hi = ventana.panel_datos.modelo.rango_x
    assert abs(lo - 1) < 0.05 and abs(hi - 5) < 0.05
    assert np.all((ventana.p_ajuste.resultado.datos.x >= lo) & (ventana.p_ajuste.resultado.datos.x <= hi))
    # tres acciones en la pila: deshacer dos (rango y región) y rehacer una
    assert ventana.pila.count() == 3
    for _ in range(2):
        ventana.pila.undo()
    esperar(app, ventana)
    assert ventana.panel_datos.modelo.excluidas == {4} and ventana.panel_datos.modelo.rango_x is None
    ventana.pila.redo()
    esperar(app, ventana)
    assert ventana.panel_datos.modelo.excluidas == {4, 7, 8}
    assert ventana.isWindowModified()


def test_cuadro_resultados_y_personalizar(app, ventana):
    from ajustelab.gui.dialogos import DialogoPersonalizar

    abrir_y_ajustar(app, ventana)
    assert ventana.grafica._cuadro is not None
    dlg = DialogoPersonalizar(ventana.grafica.opciones, ventana)
    dlg.titulo.setText("Descarga RC")
    dlg.cuadro.setChecked(False)
    dlg.aplicar(ventana.grafica.opciones)
    ventana.grafica.redibujar()
    assert ventana.grafica._cuadro is None and ventana.grafica._ax.get_title() == "Descarga RC"


# --- selección, interpolación, intersección --------------------------------
def test_seleccion_comparar_y_usar(app, ventana):
    ventana.abrir(EJEMPLO)
    ventana.pestanas.setCurrentWidget(ventana.p_seleccion)
    ventana.ejecutar_pestana()
    esperar(app, ventana, 60)
    ps = ventana.p_seleccion
    assert ps.seleccion.recomendado.clave == "exponencial_fondo"
    for i in (1, 2, 3, 4):
        ps.tabla.item(i, 0).setCheckState(Qt.Checked)
    assert len(ps.comparados()) == 3  # el cuarto se rechaza
    escena = ps.escena(*ventana.obtener_datos())
    assert len(escena.comparar) == 3
    ps.usar_en_ajuste()
    assert ventana.pestanas.currentWidget() is ventana.p_ajuste
    assert ventana.p_ajuste.resultado.modelo.nombre == "Exponencial con fondo"


def test_cancelar_seleccion(app, ventana):
    ventana.abrir(EJEMPLO)
    ventana.p_seleccion.ejecutar()
    ventana._cancelar()
    esperar(app, ventana)
    assert ventana._trabajo is None


def test_interpolacion(app, ventana, tmp_path, monkeypatch):
    ventana.abrir(EJEMPLO)
    esperar(app, ventana)
    p = ventana.p_interp
    ventana.pestanas.setCurrentWidget(p)
    p.metodo.setCurrentIndex(p.metodo.findData("pchip"))
    p.interpolar()
    p.x0.setText("2,5")
    p.a.setText("1")
    p.b.setText("3")
    p.calcular()
    esperar(app, ventana)
    assert "f(2.5) =" in p.salida.toPlainText() and "±" in p.salida.toPlainText()
    destino = tmp_path / "tramos.tex"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), "LaTeX (*.tex)"))
    p.exportar()
    assert r"\begin{cases}" in destino.read_text(encoding="utf-8")


def test_interseccion(app, ventana, tmp_path, monkeypatch):
    ventana.abrir_ejemplo("rectas")
    esperar(app, ventana)
    assert ventana.pestanas.currentWidget() is ventana.p_inter and ventana.p_inter.n.value() == 8
    ventana.ejecutar_pestana()
    esperar(app, ventana)
    assert abs(ventana.p_inter.resultado.x - 7.6) < 0.4
    ruta = tmp_path / "rectas.ajustelab"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(ruta), ""))
    assert ventana.guardar_sesion()
    ventana.nueva_sesion()
    assert ventana.abrir(ruta)
    assert ventana.p_inter.n.value() == 8 and ventana.pestanas.currentWidget() is ventana.p_inter


def test_trabajos_en_pestanas_distintas_no_se_cancelan(app, ventana):
    abrir_y_ajustar(app, ventana)
    ventana.p_seleccion.ejecutar()  # canal «Selección»
    ventana.p_ajuste.ajustar()  # canal «Ajuste»: no debe cancelar la selección
    esperar(app, ventana, 60)
    assert ventana.p_seleccion.seleccion is not None and ventana.p_ajuste.resultado is not None


# --- tabla ---------------------------------------------------------------------
def test_tabla_edicion_pegado_deshacer(app, ventana):
    m = ventana.panel_datos.modelo
    QGuiApplication.clipboard().setText("t;V\n1,0;2,5\n2,0;4,1\n3,0;6,2\n")
    ventana.pegar_tabla_nueva()
    esperar(app, ventana)
    assert m.nombres == ["t", "V"] and np.allclose(m.a_dataframe()["V"], [2.5, 4.1, 6.2])
    assert m.setData(m.index(0, 1), "2,6") and m.a_dataframe().iloc[0, 1] == 2.6
    m.renombrar(1, "U")
    m.insertar_filas(2)
    assert m.rowCount() == 5 and m.nombres == ["t", "U"]
    ventana.pila.undo()
    ventana.pila.undo()
    ventana.pila.undo()
    assert m.rowCount() == 3 and m.nombres == ["t", "V"] and m.a_dataframe().iloc[0, 1] == 2.5
    ventana.panel_datos.vista.selectAll()
    ventana.panel_datos.vista.copiar()
    assert QGuiApplication.clipboard().text().splitlines()[0] == "1\t2.5"
    pd_ = ventana.panel_datos
    pd_.combos["dy"].setCurrentText("constante…")
    pd_.constantes["dy"].setText("0,1")
    datos, _ = pd_.datos()
    assert np.allclose(datos.dy, 0.1)
    ventana.tabla_vacia()
    ventana.p_ajuste.ajustar()
    assert ventana.errores and "al menos 2 filas" in ventana.errores[-1]


# --- sesiones, recientes y exportación ----------------------------------------
def test_sesion_ida_y_vuelta(app, ventana, tmp_path, monkeypatch):
    abrir_y_ajustar(app, ventana)
    t = ventana.p_ajuste.tabla
    t.item(t.nombres.index("C"), 2).setCheckState(Qt.Checked)
    ventana.p_ajuste.ajustar()
    ventana.panel_datos.alternar_fila(2)
    ventana.panel_datos.modelo.fijar_rango((0.5, 5.5))
    ventana.grafica.opciones.titulo = "Mi práctica"
    esperar(app, ventana)
    ruta = tmp_path / "practica.ajustelab"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(ruta), ""))
    assert ventana.guardar_sesion()
    assert not ventana.isWindowModified()
    ventana.nueva_sesion()
    assert ventana.abrir(ruta)
    esperar(app, ventana)
    m = ventana.panel_datos.modelo
    assert m.excluidas == {2} and m.rango_x == (0.5, 5.5)
    assert ventana.grafica.opciones.titulo == "Mi práctica"
    assert ventana.p_ajuste.resultado is not None and "C" in ventana.p_ajuste.resultado.fijos
    assert str(ruta.resolve()) in ventana._recientes()
    assert not ventana.pila.canUndo()


def test_sesion_invalida(app, ventana, tmp_path):
    malo = tmp_path / "x.ajustelab"
    malo.write_text('{"formato": "otro"}', encoding="utf-8")
    assert not ventana.abrir(malo)
    assert "no es una sesión" in ventana.errores[-1]


def test_exportar_y_copiar(app, ventana, tmp_path):
    from ajustelab.gui.dialogos import renderizar
    from ajustelab.gui.grafica import COLORES_PUBLICACION

    abrir_y_ajustar(app, ventana)
    fig = renderizar(ventana.grafica.escena, ventana.grafica.opciones, COLORES_PUBLICACION, False, 8.5, 6.5)
    assert np.allclose(fig.get_size_inches(), (8.5 / 2.54, 6.5 / 2.54))
    for ext in ("png", "pdf", "svg"):
        ruta = tmp_path / f"g.{ext}"
        fig.savefig(ruta, dpi=150)
        assert ruta.stat().st_size > 1000
    QGuiApplication.clipboard().clear()
    ventana.copiar_grafica()
    assert not QGuiApplication.clipboard().image().isNull()


# --- easter egg -------------------------------------------------------------
@pytest.mark.parametrize("formato", [None, "png", "gif"])
def test_sorpresa(app, ventana, tmp_path, monkeypatch, formato):
    from ajustelab.gui import acerca

    monkeypatch.setattr(acerca, "RECURSOS", tmp_path)
    if formato == "png":
        pm = QPixmap(120, 80)
        pm.fill(QColor("#2a78d6"))
        assert pm.save(str(tmp_path / "sorpresa.png"))
    elif formato == "gif":  # Qt no escribe GIF; Pillow viene con matplotlib
        from PIL import Image

        cuadros = [Image.new("RGB", (60, 40), c) for c in ("#2a78d6", "#eb6834")]
        cuadros[0].save(tmp_path / "sorpresa.gif", save_all=True, append_images=cuadros[1:], duration=80, loop=0)
    dlg = acerca.DialogoAcercaDe(ventana, "Fusion", "claro")
    dlg.show()
    assert dlg.sorpresa.objectName() == "sorpresa" and dlg.sorpresa.text() == "π"
    dlg.sorpresa.click()
    esperar(app, ventana, 25)
    flotantes = [c for c in ventana.children() if isinstance(c, acerca.ImagenFlotante)]
    assert len(flotantes) == 1
    f = flotantes[0]
    assert f.isVisible() and f._alfa > 0.9
    assert (f._movie is not None) == (formato == "gif")
    assert ventana.rect().contains(f.geometry().center())
    f.cerrar()
    esperar(app, ventana, 40)
    assert not [c for c in ventana.children() if isinstance(c, acerca.ImagenFlotante)]
