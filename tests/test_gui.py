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
    w.pestanas.setCurrentWidget(w.p_ajuste)  # la pestaña por defecto es «Representar»
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
        assert not ventana.grafica.escena.vacia
        if ventana.pestanas.currentWidget() is not ventana.p_repr or ventana.p_repr.tipo.currentData() == "xy":
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


# --- pestaña «Representar» --------------------------------------------------------
def _contenedores_error(fig):
    from matplotlib.container import ErrorbarContainer

    return [c for ax in fig.axes for c in ax.containers if isinstance(c, ErrorbarContainer)]


def test_representar_dos_ejes_apilados_y_barras(app, ventana):
    from ajustelab.gui.grafica import PALETA_SERIES

    ventana.abrir_ejemplo("carga")
    esperar(app, ventana)
    p = ventana.p_repr
    assert ventana.pestanas.currentWidget() is p
    cfg = p._series_config()
    assert [(s["y"], s["dy"], s["eje"]) for s in cfg] == [("V (V)", "dV", "izq"), ("I (mA)", "dI", "der")]
    fig = ventana.grafica.figura
    izq, der = fig.axes
    assert izq.get_ylabel() == "V (V)" and der.get_ylabel() == "I (mA)" and izq.get_xlabel() == "t (s)"
    claro = PALETA_SERIES[ventana.tema.oscuro]
    from matplotlib.colors import to_hex

    assert to_hex(izq.spines["left"].get_edgecolor()) == claro[0]  # cada eje, del color de su serie
    assert to_hex(der.spines["right"].get_edgecolor()) == claro[1]
    assert len(fig.legends) == 1 and "(eje dcho.)" in fig.legends[0].get_texts()[1].get_text()
    assert len(_contenedores_error(fig)) == 2
    # Sin barras de error
    p.barras.setChecked(False)
    esperar(app, ventana, 5)
    assert not _contenedores_error(ventana.grafica.figura)
    p.barras.setChecked(True)
    # Paneles apilados: misma x, uno encima de otro
    p.disposicion.setCurrentIndex(1)
    esperar(app, ventana, 5)
    arriba, abajo = ventana.grafica.figura.axes
    assert arriba.get_position().y0 > abajo.get_position().y1 and abajo.get_xlabel() == "t (s)"
    assert arriba.get_shared_x_axes().joined(arriba, abajo)
    # Región, Rango y Residuos no aplican sin ajuste
    assert not ventana.grafica.b_region.isEnabled() and not ventana.grafica.ver_residuos.isEnabled()
    ventana.pestanas.setCurrentWidget(ventana.p_ajuste)
    esperar(app, ventana, 5)
    assert ventana.grafica.b_region.isEnabled()


def test_representar_series_colores_y_columnas(app, ventana, monkeypatch):
    from PySide6.QtGui import QColor as QC
    from PySide6.QtWidgets import QColorDialog

    ventana.abrir_ejemplo("carga")
    esperar(app, ventana)
    p = ventana.p_repr
    # Quitar la primera serie no cambia el color de la otra (el color sigue a la serie)
    p.tabla.setCurrentCell(0, 0)
    p.quitar_serie()
    esperar(app, ventana, 5)
    assert [s["y"] for s in p._series_config()] == ["I (mA)"] and p._series_config()[0]["indice"] == 1
    # Una sola serie en el eje derecho: se dibuja con un solo eje
    assert len(ventana.grafica.figura.axes) == 1
    # Quitarlas todas deja la gráfica vacía (no vuelven solas); «Automático» las recupera
    p.quitar_serie()
    esperar(app, ventana, 5)
    assert p.tabla.rowCount() == 0 and not ventana.grafica.figura.axes
    p.configurar(automatico=True)
    esperar(app, ventana, 5)
    assert p.tabla.rowCount() == 2
    # Añadir una serie y elegir su color
    p.anadir_serie()
    assert p.tabla.rowCount() == 3 and p._series_config()[2]["indice"] == 2
    monkeypatch.setattr(QColorDialog, "getColor", lambda *a, **k: QC("#123456"))
    p._elegir_color(p.tabla.cellWidget(2, 5))
    assert p._series_config()[2]["color"] == "#123456"
    # Una columna nueva en la tabla aparece en las listas
    m = ventana.panel_datos.modelo
    m.renombrar(4, "δI")
    esperar(app, ventana, 5)
    assert "δI" in [p.tabla.cellWidget(0, 2).itemText(i) for i in range(p.tabla.cellWidget(0, 2).count())]


def test_representar_clic_excluye_fila(app, ventana):
    from matplotlib.backend_bases import MouseEvent

    ventana.abrir_ejemplo("carga")
    esperar(app, ventana)
    g = ventana.grafica
    g.lienzo.draw()
    assert g._puntos_px is not None and g._puntos_serie is not None
    # Un punto de la serie del eje derecho (I): fila 3
    k = int(np.flatnonzero((g._puntos_serie[:, 0] == 1) & (g._puntos_serie[:, 1] == 3))[0])
    MouseEvent("motion_notify_event", g.lienzo, *g._puntos_px[k])._process()
    assert g._anotacion is not None and "I (mA)" in g._anotacion.get_text()
    MouseEvent("button_press_event", g.lienzo, *g._puntos_px[k], button=1)._process()
    esperar(app, ventana)
    assert ventana.panel_datos.modelo.excluidas == {3}
    serie = ventana.grafica.escena.series[1]
    assert not serie.incluidos[3] and serie.incluidos.sum() == serie.x.size - 1


def test_representar_en_sesion(app, ventana, tmp_path, monkeypatch):
    ventana.abrir_ejemplo("carga")
    esperar(app, ventana)
    p = ventana.p_repr
    p.disposicion.setCurrentIndex(1)
    p.tabla.cellWidget(1, 4).setCurrentIndex(p.tabla.cellWidget(1, 4).findData("puntos_linea"))
    ruta = tmp_path / "carga.ajustelab"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(ruta), ""))
    assert ventana.guardar_sesion()
    ventana.nueva_sesion()
    assert ventana.abrir(ruta)
    esperar(app, ventana)
    assert ventana.pestanas.currentWidget() is ventana.p_repr
    assert p.disposicion.currentData() is True and p._series_config()[1]["estilo"] == "puntos_linea"
    assert len(ventana.grafica.figura.axes) == 2


def test_sesion_antigua_abre_su_pestana(app, ventana):
    """Las sesiones de antes de «Representar» guardaban el índice de la pestaña."""
    from ajustelab.gui import sesion

    ventana.abrir(EJEMPLO)
    esperar(app, ventana)
    d = sesion.a_dict(ventana)
    d.pop("pestana_panel")
    d["pestana"] = 0  # entonces, «Ajuste»
    sesion.restaurar(ventana, d)
    assert ventana.pestanas.currentWidget() is ventana.p_ajuste


# --- exportación ------------------------------------------------------------------
def test_exportar_formatos_tamano_y_texto(app, ventana, tmp_path):
    import re

    from PIL import Image

    from ajustelab.gui.dialogos import guardar_figura, renderizar
    from ajustelab.gui.grafica import COLORES_PUBLICACION

    abrir_y_ajustar(app, ventana)
    e, o = ventana.grafica.escena, ventana.grafica.opciones
    for fuente in ("sans", "serif"):
        for editable in (True, False):
            fig = renderizar(e, o, COLORES_PUBLICACION, False, 8.6, 6.4, fuente=fuente, tam_fuente=8,
                             editable=editable)
            for ext in ("png", "pdf", "svg", "eps", "tif"):
                ruta = tmp_path / f"g_{fuente}_{editable}.{ext}"
                guardar_figura(fig, ruta, dpi=300)
                assert ruta.stat().st_size > 2000, ruta
            svg = (tmp_path / f"g_{fuente}_{editable}.svg").read_text(encoding="utf-8")
            assert ("<text" in svg) == editable  # texto editable o convertido en trazos
    # Tamaño exacto: 8,6 × 6,4 cm
    px = (int(8.6 / 2.54 * 300), int(6.4 / 2.54 * 300))
    assert Image.open(tmp_path / "g_sans_True.png").size == px
    tif = Image.open(tmp_path / "g_sans_True.tif")
    assert tif.size == px and tif.info.get("compression") == "tiff_lzw"
    caja = re.search(rb"/MediaBox \[ *0 0 ([\d.]+) ([\d.]+)", (tmp_path / "g_sans_True.pdf").read_bytes())
    assert abs(float(caja[1]) - 8.6 / 2.54 * 72) < 0.5 and abs(float(caja[2]) - 6.4 / 2.54 * 72) < 0.5
    assert b"/FontFile2" in (tmp_path / "g_sans_True.pdf").read_bytes()  # TrueType incrustada (tipo 42)
    assert b"STIX" in (tmp_path / "g_serif_True.pdf").read_bytes()


def test_exportar_datos_csv(app, ventana, tmp_path):
    from ajustelab.gui.dialogos import guardar_tablas, tablas_escena

    abrir_y_ajustar(app, ventana)
    t = tablas_escena(ventana.grafica.escena)
    assert set(t) == {"datos", "ajuste"}
    assert {"f", "banda_inferior", "banda_superior"} <= set(t["ajuste"].columns) and len(t["datos"]) == 16
    rutas = guardar_tablas(ventana.grafica.escena, tmp_path / "figura.pdf")
    assert sorted(r.name for r in rutas) == ["figura_ajuste.csv", "figura_datos.csv"]
    ventana.abrir_ejemplo("carga")
    esperar(app, ventana)
    t = tablas_escena(ventana.grafica.escena)
    assert list(t["datos"].columns) == ["fila", "t (s)", "V (V)", "σ V (V)", "I (mA)", "σ I (mA)"]
    assert t["datos"]["fila"].iloc[0] == 1 and len(t["datos"]) == 26


def test_dialogo_exportar(app, ventana):
    from ajustelab.gui.dialogos import DialogoExportar

    abrir_y_ajustar(app, ventana)
    dlg = DialogoExportar(ventana, {"formato": "pdf", "fuente": "serif"}, ventana.grafica.escena,
                          ventana.grafica.opciones, ventana.tema)
    dlg.show()
    assert dlg.formato.currentData() == "pdf" and not dlg.dpi.isEnabled() and dlg.editable.isEnabled()
    dlg.preset.setCurrentText("Doble columna (17,8 cm)")
    assert dlg.ancho.value() == 17.8 and abs(dlg.alto.value() - 13.4) < 0.11 and not dlg.alto.isEnabled()
    dlg.proporcion.setCurrentText("Libre")
    assert dlg.alto.isEnabled()
    dlg.formato.setCurrentIndex(dlg.formato.findData("eps"))
    assert not dlg.transparente.isEnabled() and "transparencias" in dlg.aviso.text()
    dlg.formato.setCurrentIndex(dlg.formato.findData("png"))
    assert dlg.dpi.isEnabled() and "px" in dlg.info.text()
    for _ in range(40):
        app.processEvents()
        time.sleep(0.01)
    assert dlg.vista.pixmap() is not None and not dlg.vista.pixmap().isNull()
    dlg.close()


def test_exportar_de_principio_a_fin(app, ventana, tmp_path, monkeypatch):
    from ajustelab.gui import dialogos

    abrir_y_ajustar(app, ventana)
    monkeypatch.setattr(dialogos.DialogoExportar, "exec", lambda self: QtWidgets.QDialog.Accepted)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "practica"), ""))
    ventana._ultima_exportacion = {"formato": "svg", "ancho": 12.0, "proporcion": "Libre", "alto": 8.0,
                                   "datos": True}
    ventana.exportar_grafica()
    assert (tmp_path / "practica.svg").is_file()  # se añade la extensión del formato
    assert (tmp_path / "practica_datos.csv").is_file() and (tmp_path / "practica_ajuste.csv").is_file()
    import json

    assert json.loads(ventana.ajustes.value("exportacion"))["formato"] == "svg"  # se recuerda
    # Copiar: imagen y SVG a la vez
    QGuiApplication.clipboard().clear()
    ventana.copiar_grafica()
    mime = QGuiApplication.clipboard().mimeData()
    assert mime.hasImage() and mime.hasFormat("image/svg+xml") and b"<svg" in bytes(mime.data("image/svg+xml"))


@pytest.mark.parametrize("cierre", ["aboutToQuit", "fin_de_python"])
def test_copiar_grafica_y_salir_sin_error(cierre):
    """PySide6 se caía al salir si el portapapeles guardaba nuestro QMimeData (PNG + SVG)."""
    import subprocess
    import sys

    codigo = f"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from ajustelab.gui.dialogos import copiar_figura, renderizar
from ajustelab.gui.grafica import COLORES_PUBLICACION, Escena, OpcionesGrafica, SerieDibujo
import numpy as np
app = QApplication([])
s = SerieDibujo("y", np.arange(5.0), np.arange(5.0) ** 2)
copiar_figura(renderizar(Escena(series=[s], nombre_x="x"), OpcionesGrafica(), COLORES_PUBLICACION, False, 8, 6))
assert app.clipboard().mimeData().hasFormat("image/svg+xml")
if {cierre!r} == "aboutToQuit":
    QTimer.singleShot(50, app.quit)
    app.exec()
    assert not app.clipboard().image().isNull()  # la imagen sigue en el portapapeles
print("ok")
"""
    entorno = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=entorno, timeout=120)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-2000:]


# --- columnas de texto (etiquetas) -------------------------------------------------
def test_tabla_columnas_de_texto(app, ventana, tmp_path, monkeypatch):
    m = ventana.panel_datos.modelo
    QGuiApplication.clipboard().setText("Metal;Fracción;dF\nPb;0,25;0,01\nCu;0,40;0,02\nFe;0,35;0,01\n")
    ventana.pegar_tabla_nueva()
    esperar(app, ventana)
    assert m.nombres == ["Metal", "Fracción", "dF"]
    assert m.columnas_texto() == ["Metal"] and m.columnas_numericas() == ["Fracción", "dF"]
    assert m.etiquetas("Metal") == ["Pb", "Cu", "Fe"]
    assert m.data(m.index(1, 0)) == "Cu" and np.isnan(m.a_dataframe().iloc[1, 0])
    assert list(m.a_dataframe(con_texto=True)["Metal"]) == ["Pb", "Cu", "Fe"]
    # los desplegables de x/y solo ofrecen columnas numéricas
    combo = ventana.panel_datos.combos["x"]
    assert [combo.itemText(i) for i in range(combo.count())][:2] == ["Fracción", "dF"]
    # editar: texto donde había texto, número donde había número; deshacer
    assert m.setData(m.index(2, 0), "Zn") and m.etiquetas("Metal")[2] == "Zn"
    assert m.setData(m.index(0, 1), "abc") and m.data(m.index(0, 1)) == "abc"
    ventana.pila.undo()
    ventana.pila.undo()
    assert m.etiquetas("Metal") == ["Pb", "Cu", "Fe"] and m.a_dataframe().iloc[0, 1] == 0.25
    # pegar un bloque con texto y borrar celdas
    QGuiApplication.clipboard().setText("Ag\t0,5\nAu\t0,6")
    ventana.panel_datos.vista.setCurrentIndex(m.index(1, 0))
    ventana.panel_datos.vista.pegar()
    assert m.etiquetas("Metal")[:3] == ["Pb", "Ag", "Au"] and np.isclose(m.a_dataframe().iloc[2, 1], 0.6)
    ventana.pila.undo()
    assert m.etiquetas("Metal") == ["Pb", "Cu", "Fe"]
    # la sesión conserva el texto
    ruta = tmp_path / "metales.ajustelab"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(ruta), ""))
    assert ventana.guardar_sesion()
    ventana.nueva_sesion()
    assert ventana.abrir(ruta)
    esperar(app, ventana)
    m = ventana.panel_datos.modelo
    assert m.etiquetas("Metal") == ["Pb", "Cu", "Fe"] and np.allclose(m.a_dataframe()["Fracción"], [0.25, 0.40, 0.35])


# --- tipos de gráfica y eje partido ----------------------------------------------
def _evento(lienzo, ax, x, y, tipo="motion_notify_event", boton=None):
    """MouseEvent en las coordenadas de datos (x, y) de los ejes ``ax``."""
    from matplotlib.backend_bases import MouseEvent

    px, py = ax.transData.transform((x, y))
    ev = MouseEvent(tipo, lienzo, px, py, button=boton)
    ev._process()
    return ev


def _etiqueta(g, ax, x, y):
    g.lienzo.draw()
    _evento(g.lienzo, ax, x, y)
    return None if g._anotacion is None else g._anotacion.get_text()


def test_histograma_desde_ejemplo(app, ventana):
    from ajustelab.gui.graficas import Aviso, HistoGrafica

    ventana.abrir_ejemplo("medidas")
    esperar(app, ventana)
    p, g = ventana.p_repr, ventana.grafica
    assert p.tipo.currentData() == "histograma" and isinstance(g.escena.especial, HistoGrafica)
    h = g.escena.especial
    assert [c.nombre for c in h.columnas] == ["T grupo A (s)", "T grupo B (s)"]
    assert np.array_equal(h.histogramas[0].bordes, h.histogramas[1].bordes)  # mismos intervalos
    assert h.histogramas[0].n == 60 and h.histogramas[1].n == 45  # las celdas vacías no cuentan
    assert all(a is not None and a.distribucion == "normal" for a in h.ajustes)
    assert "μ = " in p.h_resultados.toPlainText() and "χ²" in p.h_resultados.toPlainText()
    assert g.figura.axes[0].get_xlabel() == "Valor (s)"
    assert not g.b_cortar.isVisible() and not g.b_region.isEnabled() and g.log_y.isEnabled()
    # etiqueta al pasar por un intervalo
    b = h.histogramas[0].bordes
    i = int(np.argmax(h.histogramas[0].cuentas))
    texto = _etiqueta(g, g.figura.axes[0], (b[i] + b[i + 1]) / 2, 0.5)
    assert texto and texto.startswith("[") and "T grupo A (s): N = " in texto and "esperadas" in texto
    # densidad: el área de cada histograma es 1
    p.h_norm.setCurrentIndex(p.h_norm.findData("densidad"))
    esperar(app, ventana, 5)
    h = g.escena.especial
    y, _ = h.histogramas[0].valores("densidad")
    assert np.isclose(np.sum(y * h.histogramas[0].anchos), 1)
    # número fijo de intervalos y anchura fija
    p.h_regla.setCurrentIndex(p.h_regla.findData("numero"))
    p.h_numero.setValue(7)
    esperar(app, ventana, 5)
    assert g.escena.especial.histogramas[0].cuentas.size == 7 and p.h_numero.isVisibleTo(p)
    p.h_regla.setCurrentIndex(p.h_regla.findData("ancho"))
    p.h_ancho.setText("abc")
    p.h_ancho.editingFinished.emit()
    esperar(app, ventana, 5)
    assert isinstance(g.escena.especial, Aviso) and "anchura" in p.h_resultados.toPlainText()
    p.h_ancho.setText("0,01")
    p.h_ancho.editingFinished.emit()
    esperar(app, ventana, 5)
    assert np.allclose(g.escena.especial.histogramas[0].anchos, 0.01)
    # excluir una fila la saca del histograma
    ventana.panel_datos.alternar_fila(0)
    esperar(app, ventana)
    assert g.escena.especial.histogramas[0].n == 59
    # Poisson con las cuentas
    p.h_series.configurar([{"ver": True, "y": "Cuentas en 1 s", "dy": "", "indice": 2, "color": None}])
    p.h_regla.setCurrentIndex(p.h_regla.findData("fd"))
    p.h_ajuste.setCurrentIndex(p.h_ajuste.findData("poisson"))
    esperar(app, ventana, 5)
    h = g.escena.especial
    assert h.histogramas[0].enteros and h.ajustes[0].discreta and "λ = " in p.h_resultados.toPlainText()


def test_barras_sectores_y_cajas(app, ventana):
    from ajustelab.gui.graficas import BarrasGrafica, CajasGrafica, CircularGrafica

    ventana.abrir_ejemplo("composicion")
    esperar(app, ventana)
    p, g = ventana.p_repr, ventana.grafica
    b = g.escena.especial
    assert isinstance(b, BarrasGrafica) and b.categorias[:2] == ["Cu", "Zn"]  # de mayor a menor
    assert b.series[0].errores is not None and np.all(np.diff(b.series[0].valores) <= 0)
    ax = g.figura.axes[0]
    texto = _etiqueta(g, ax, 0, b.series[0].valores[0] / 2)
    assert texto and texto.startswith("Cu") and "Fracción = " in texto
    # sectores
    p.tipo.setCurrentIndex(p.tipo.findData("circular"))
    esperar(app, ventana, 5)
    c = g.escena.especial
    assert isinstance(c, CircularGrafica) and c.etiquetas[0] == "Cu" and c.etiquetas[-1].startswith("Otros")
    assert np.isclose(c.valores.sum(), 1, atol=1e-3)
    g.lienzo.draw()
    cuna = g.figura.axes[0].patches[0]  # Cu: el sector más grande, a la derecha
    cx, cy = cuna.center
    r = cuna.r - cuna.width / 2
    ang = np.radians((cuna.theta1 + cuna.theta2) / 2)
    texto = _etiqueta(g, g.figura.axes[0], cx + r * np.cos(ang), cy + r * np.sin(ang))
    assert texto and texto.startswith("Cu") and "%" in texto
    # con negativos, un aviso en lugar de la gráfica
    m = ventana.panel_datos.modelo
    m.setData(m.index(2, 1), "-0,1")
    esperar(app, ventana)
    assert "≥ 0" in g.escena.especial.texto
    ventana.pila.undo()
    esperar(app, ventana)
    # «Ver como barras ordenadas»
    p.circular_a_barras()
    esperar(app, ventana, 5)
    b = g.escena.especial
    assert p.tipo.currentData() == "barras" and b.horizontal and b.categorias[0] == "Cu"
    # cajas con el ejemplo de medidas
    ventana.pila.setClean()
    ventana.abrir_ejemplo("medidas")
    esperar(app, ventana)
    p.tipo.setCurrentIndex(p.tipo.findData("cajas"))
    p.k_modo.setCurrentIndex(p.k_modo.findData("ambos"))
    esperar(app, ventana, 5)
    k = g.escena.especial
    assert isinstance(k, CajasGrafica) and [x.nombre for x in k.grupos] == ["T grupo A (s)", "T grupo B (s)"]
    mediana = float(np.median(k.grupos[0].valores))
    texto = _etiqueta(g, g.figura.axes[0], 1.0, mediana)
    assert texto and "mediana" in texto and "n = 60" in texto


def test_polar(app, ventana):
    from ajustelab.gui.graficas import PolarGrafica

    ventana.abrir_ejemplo("malus")
    esperar(app, ventana)
    p, g = ventana.p_repr, ventana.grafica
    pol = g.escena.especial
    assert isinstance(pol, PolarGrafica) and pol.grados and np.isclose(pol.series[0].x[3], np.radians(30))
    ax = g.figura.axes[0]
    assert ax.name == "polar"
    s = pol.series[0]
    texto = _etiqueta(g, ax, s.x[2], s.y[2])
    assert texto and "θ (°) = 20°" in texto and "fila 3" in texto
    p.p_orientacion.setCurrentIndex(p.p_orientacion.findData("brujula"))
    esperar(app, ventana, 5)
    ax = g.figura.axes[0]
    assert ax.get_theta_direction() == -1 and np.isclose(ax.get_theta_offset(), np.pi / 2)


def test_eje_partido(app, ventana, tmp_path, monkeypatch):
    from ajustelab.gui.dialogos import tablas_escena

    ventana.abrir_ejemplo("dos_tandas")
    esperar(app, ventana)
    p, g = ventana.p_repr, ventana.grafica
    assert p.cortes == [(12.0, 60.0)] and g.escena.cortes == [(12.0, 60.0)]
    izq, der = g.figura.axes
    assert izq.get_xlim()[1] < 13 and der.get_xlim()[0] > 59  # el hueco no se dibuja
    assert not der.spines["left"].get_visible() and not izq.spines["right"].get_visible()
    assert g.b_cortar.isVisible()
    # el clic en un punto del segundo tramo excluye su fila
    g.lienzo.draw()
    s = g.escena.series[0]
    j = int(np.flatnonzero(s.x == 62)[0])
    _evento(g.lienzo, der, 62, s.y[j], "button_press_event", 1)
    esperar(app, ventana)
    assert ventana.panel_datos.modelo.excluidas == {int(s.filas[j])}
    # cortar con la herramienta: arrastrar sobre el tramo 64–68 del segundo panel
    g.b_cortar.setChecked(True)
    g.lienzo.draw()
    der = g.figura.axes[1]
    yv = float(np.mean(der.get_ylim()))
    _evento(g.lienzo, der, 64.2, yv, "button_press_event", 1)
    _evento(g.lienzo, der, 66.5, yv, "motion_notify_event", 1)
    _evento(g.lienzo, der, 67.8, yv, "button_release_event", 1)
    esperar(app, ventana, 5)
    assert len(p.cortes) == 2 and 64 < p.cortes[1][0] < p.cortes[1][1] < 68
    assert len(g.figura.axes) == 3 and not g.b_cortar.isChecked()
    # los datos exportados no incluyen lo que cae en un corte
    df = tablas_escena(g.escena)["datos"]
    assert not np.any((df["t (min)"] > 12) & (df["t (min)"] < 60)) and 65 not in df["t (min)"].to_numpy()
    # en la sesión
    ruta = tmp_path / "tandas.ajustelab"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(ruta), ""))
    assert ventana.guardar_sesion()
    ventana.nueva_sesion()
    assert ventana.abrir(ruta)
    esperar(app, ventana)
    assert len(p.cortes) == 2 and len(g.figura.axes) == 3
    p.quitar_cortes()
    esperar(app, ventana, 5)
    assert len(g.figura.axes) == 1 and p.texto_cortes.text() == "ninguno"
    assert p.cortar_huecos() == 1 and len(g.figura.axes) == 2


def test_tipos_en_sesion_y_exportacion(app, ventana, tmp_path, monkeypatch):
    from ajustelab.gui.dialogos import guardar_figura, guardar_tablas, renderizar
    from ajustelab.gui.grafica import COLORES_PUBLICACION

    ventana.abrir_ejemplo("medidas")
    esperar(app, ventana)
    p = ventana.p_repr
    p.h_norm.setCurrentIndex(p.h_norm.findData("relativa"))
    esperar(app, ventana, 5)
    ruta = tmp_path / "medidas.ajustelab"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(ruta), ""))
    assert ventana.guardar_sesion()
    ventana.nueva_sesion()
    assert ventana.abrir(ruta)
    esperar(app, ventana)
    assert p.tipo.currentData() == "histograma" and p.h_norm.currentData() == "relativa"
    assert p.h_ajuste.currentData() == "normal" and len(p.h_series.config()) == 2
    # cada tipo se exporta (vectorial y CSV) con el mismo código que en pantalla
    for tipo in ("histograma", "barras", "circular", "cajas", "polar", "xy"):
        p.tipo.setCurrentIndex(p.tipo.findData(tipo))
        esperar(app, ventana, 3)
        e = ventana.grafica.escena
        fig = renderizar(e, ventana.grafica.opciones, COLORES_PUBLICACION, False, 12, 8)
        for ext in ("pdf", "svg"):
            guardar_figura(fig, tmp_path / f"{tipo}.{ext}")
            assert (tmp_path / f"{tipo}.{ext}").stat().st_size > 1000
        rutas = guardar_tablas(e, tmp_path / f"{tipo}.png")
        assert rutas and all(r.exists() and " " not in r.name for r in rutas)
