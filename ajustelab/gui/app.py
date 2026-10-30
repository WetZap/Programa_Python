"""Ventana principal de ajustelab.

Arranque:  ``ajustelab [fichero]``  o  ``python -m ajustelab [fichero]``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("QtAgg")

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication, QKeySequence  # noqa: E402
from PySide6.QtWidgets import (QApplication, QFileDialog, QInputDialog, QLabel, QMainWindow,  # noqa: E402
                               QMessageBox, QProgressBar, QPushButton, QSplitter, QTabWidget)

from .. import __version__  # noqa: E402
from ..datos import EXTENSIONES, EXT_HOJA, ErrorDatos, hojas, leer_tabla, leer_texto  # noqa: E402
from .grafica import Escena, Grafica  # noqa: E402
from .paneles import PanelAjuste, PanelInterpolacion, PanelInterseccion, PanelSeleccion  # noqa: E402
from .tabla import PanelDatos  # noqa: E402
from .tema import GestorTema  # noqa: E402
from .trabajos import Trabajo  # noqa: E402

URL_REPO = "https://github.com/WetZap/Programa_Python"


def _describir(df) -> str:
    a = df.attrs
    partes = [f"{df.shape[0]} filas × {df.shape[1]} columnas"]
    if "hoja" in a:
        partes.append(f"hoja «{a['hoja']}»")
    if "delimitador" in a:
        d = {"\t": "tabulador", " ": "espacios"}.get(a["delimitador"], a["delimitador"])
        partes.append(f"separador «{d}»")
    if "decimal" in a:
        partes.append(f"decimal «{a['decimal']}»")
    if a.get("filas_ignoradas"):
        partes.append(f"{a['filas_ignoradas']} líneas ignoradas")
    return "Detectado: " + ", ".join(partes)


class VentanaPrincipal(QMainWindow):
    def __init__(self, tema: GestorTema):
        super().__init__()
        self.tema = tema
        self.ajustes = QSettings()
        self._trabajo: Trabajo | None = None
        self._id_trabajo = 0
        self._ruta: Path | None = None

        self.panel_datos = PanelDatos()
        self.grafica = Grafica(tema)
        self.p_ajuste = PanelAjuste(self)
        self.p_seleccion = PanelSeleccion(self)
        self.p_interp = PanelInterpolacion(self)
        self.p_inter = PanelInterseccion(self)
        self.paneles = [self.p_ajuste, self.p_seleccion, self.p_interp, self.p_inter]
        self.pestanas = QTabWidget()
        for p in self.paneles:
            self.pestanas.addTab(p, p.titulo)

        derecha = QSplitter(Qt.Vertical)
        derecha.addWidget(self.grafica)
        derecha.addWidget(self.pestanas)
        derecha.setStretchFactor(0, 3)
        derecha.setStretchFactor(1, 2)
        principal = QSplitter(Qt.Horizontal)
        principal.addWidget(self.panel_datos)
        principal.addWidget(derecha)
        principal.setStretchFactor(1, 1)
        principal.setSizes([380, 1000])
        self.setCentralWidget(principal)

        # Barra de estado con progreso y cancelación
        self.mensaje = QLabel()
        self.progreso = QProgressBar()
        self.progreso.setMaximumWidth(220)
        self.progreso.setVisible(False)
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.setVisible(False)
        self.b_cancelar.clicked.connect(self._cancelar)
        self.statusBar().addWidget(self.mensaje, 1)
        self.statusBar().addPermanentWidget(self.progreso)
        self.statusBar().addPermanentWidget(self.b_cancelar)

        self._crear_menus()
        self.setAcceptDrops(True)

        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(200)
        self._temporizador.timeout.connect(self._datos_cambiados)
        self.panel_datos.datosCambiados.connect(self._temporizador.start)
        self.grafica.puntoClicado.connect(self.panel_datos.alternar_fila)
        self.pestanas.currentChanged.connect(lambda _: self.actualizar_grafica())

        self.panel_datos.modelo.vaciar()
        self._actualizar_titulo()
        geometria = self.ajustes.value("geometria")
        if geometria is not None:
            self.restoreGeometry(geometria)
        else:
            self.resize(1400, 860)
        self.estado("Abre un fichero (Ctrl+O), arrástralo a la ventana, pega datos o escríbelos en la tabla.")

    # ------------------------------------------------------------------ menús
    def _crear_menus(self) -> None:
        def accion(menu, texto, funcion, atajo=None):
            a = QAction(texto, self)
            if atajo is not None:
                a.setShortcut(atajo)
            a.triggered.connect(funcion)
            menu.addAction(a)
            return a

        m = self.menuBar().addMenu("&Archivo")
        accion(m, "&Abrir…", self.dialogo_abrir, QKeySequence.Open)
        accion(m, "Pegar como tabla &nueva", self.pegar_tabla_nueva, QKeySequence("Ctrl+Shift+V"))
        accion(m, "Tabla &vacía", self.tabla_vacia, QKeySequence.New)
        m.addSeparator()
        accion(m, "Exportar &gráfica…", self.exportar_grafica, QKeySequence("Ctrl+E"))
        accion(m, "Guardar &informe…", self.guardar_informe, QKeySequence.Save)
        accion(m, "Exportar &tabla (CSV)…", self.exportar_tabla)
        m.addSeparator()
        accion(m, "&Salir", self.close, QKeySequence.Quit)

        m = self.menuBar().addMenu("&Datos")
        accion(m, "&Incluir todos los puntos", self.panel_datos.incluir_todas)
        accion(m, "&Añadir fila", lambda: self.panel_datos.modelo.insertar_filas(1))
        accion(m, "&Borrar filas seleccionadas", self.panel_datos.borrar_filas_seleccionadas)

        m = self.menuBar().addMenu("&Ver")
        sub = m.addMenu("&Tema")
        grupo = QActionGroup(self)
        for clave, texto in (("sistema", "Seguir al &sistema"), ("claro", "&Claro"), ("oscuro", "&Oscuro")):
            a = QAction(texto, self, checkable=True)
            a.setChecked(self.tema.preferencia == clave)
            a.triggered.connect(lambda _=False, c=clave: self.tema.fijar_preferencia(c))
            grupo.addAction(a)
            sub.addAction(a)

        m = self.menuBar().addMenu("A&yuda")
        accion(m, "&Repositorio en GitHub", lambda: QDesktopServices.openUrl(QUrl(URL_REPO)))
        accion(m, "&Acerca de ajustelab", self._acerca_de)

    # ------------------------------------------------------------ utilidades
    def estado(self, texto: str) -> None:
        self.mensaje.setText(texto)

    def mostrar_error(self, texto: str) -> None:
        self.estado(f"⚠ {texto}")
        QMessageBox.warning(self, "ajustelab", texto)

    def _actualizar_titulo(self) -> None:
        nombre = self._ruta.name if self._ruta else "sin título"
        self.setWindowTitle(f"{nombre} — ajustelab {__version__}")

    def obtener_datos(self, silencioso: bool = False):
        try:
            return self.panel_datos.datos()
        except ErrorDatos as e:
            if not silencioso:
                self.mostrar_error(str(e))
            return None

    # ---------------------------------------------------- trabajos en segundo plano
    def lanzar(self, trabajo: Trabajo, al_terminar, texto: str, cancelable: bool = False) -> None:
        if self._trabajo is not None:
            self._trabajo.cancelar()  # el resultado del anterior se ignora
        self._id_trabajo += 1
        ident = self._id_trabajo
        self._trabajo = trabajo
        s = trabajo.senales

        def vigente():
            return ident == self._id_trabajo

        def fin(mensaje: str):
            if vigente():
                self._trabajo = None
                self.progreso.setVisible(False)
                self.b_cancelar.setVisible(False)
                self.estado(mensaje)

        def ok(resultado):
            if vigente():
                fin("Listo.")
                al_terminar(resultado)

        def error(msg):
            if vigente():
                fin("")
                self.mostrar_error(msg)

        def progreso(i, n, nombre):
            if vigente():
                self.progreso.setRange(0, n)
                self.progreso.setValue(i)
                self.estado(f"{texto} {nombre}")

        s.terminado.connect(ok)
        s.error.connect(error)
        s.cancelado.connect(lambda: fin("Cancelado."))
        s.progreso.connect(progreso)
        self.estado(texto)
        self.progreso.setRange(0, 0)  # indeterminado hasta el primer aviso de progreso
        self.progreso.setVisible(True)
        self.b_cancelar.setVisible(cancelable)
        QThreadPool.globalInstance().start(trabajo)

    def _cancelar(self) -> None:
        if self._trabajo is not None:
            self._trabajo.cancelar()
            self.estado("Cancelando…")

    def esperar_trabajos(self, ms: int = 60000) -> bool:
        """Espera a que termine el trabajo en curso (útil en pruebas)."""
        return QThreadPool.globalInstance().waitForDone(ms)

    # ----------------------------------------------------------- coordinación
    def panel_activo(self):
        return self.paneles[self.pestanas.currentIndex()]

    def actualizar_grafica(self) -> None:
        obtenidos = self.obtener_datos(silencioso=True)
        if obtenidos is None:
            self.grafica.mostrar(Escena())
            return
        datos, filas = obtenidos
        self.grafica.mostrar(self.panel_activo().escena(datos, filas))

    def _datos_cambiados(self) -> None:
        obtenidos = self.obtener_datos(silencioso=True)
        if obtenidos is not None:
            self.p_inter.actualizar_rango(obtenidos[0].n_total)
            if obtenidos[0].filas_descartadas:
                self.estado(f"{obtenidos[0].filas_descartadas} filas con huecos se ignoran.")
        activo = self.panel_activo()
        for p in self.paneles:
            if p is not activo:
                p.marcar_obsoleto()
        if activo.tiene_resultado() and obtenidos is not None and not isinstance(activo, PanelSeleccion):
            activo.recalcular()  # p. ej. tras excluir un punto, se reajusta solo
        else:
            if isinstance(activo, PanelSeleccion):
                activo.marcar_obsoleto()
            self.actualizar_grafica()

    def usar_en_ajuste(self, resultado) -> None:
        self.p_ajuste.usar(resultado)
        self.pestanas.setCurrentWidget(self.p_ajuste)

    # --------------------------------------------------------------- ficheros
    def dialogo_abrir(self) -> None:
        patrones = " ".join(f"*{e}" for e in EXTENSIONES)
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir datos", self.ajustes.value("ultima_carpeta", ""),
                                              f"Datos ({patrones});;Todos los ficheros (*)")
        if ruta:
            self.abrir(ruta)

    def abrir(self, ruta) -> bool:
        ruta = Path(ruta)
        hoja = None
        try:
            if ruta.suffix.lower() in EXT_HOJA:
                # Solo se pregunta entre las hojas que contienen datos numéricos
                legibles = {}
                for nombre in hojas(ruta):
                    try:
                        legibles[nombre] = leer_tabla(ruta, hoja=nombre)
                    except ErrorDatos:
                        pass
                if not legibles:
                    raise ErrorDatos("ninguna hoja contiene datos numéricos.")
                hoja = next(iter(legibles))
                if len(legibles) > 1:
                    hoja, ok = QInputDialog.getItem(self, "Hoja", "¿Qué hoja quieres abrir?", list(legibles), 0, False)
                    if not ok:
                        return False
                df = legibles[hoja]
            else:
                df = leer_tabla(ruta)
        except (ErrorDatos, OSError, ValueError) as e:
            self.mostrar_error(f"No se ha podido leer «{ruta.name}»: {e}")
            return False
        self._ruta = ruta
        self.ajustes.setValue("ultima_carpeta", str(ruta.parent))
        self._cargar(df)
        self.estado(f"Abierto {ruta}")
        return True

    def _cargar(self, df) -> None:
        for p in self.paneles:
            p.reiniciar()
        self.panel_datos.cargar(df, _describir(df))
        self._actualizar_titulo()

    def pegar_tabla_nueva(self) -> None:
        texto = QGuiApplication.clipboard().text()
        try:
            df = leer_texto(texto)
        except ErrorDatos as e:
            self.mostrar_error(f"El portapapeles no contiene una tabla de números: {e}")
            return
        self._ruta = None
        self._cargar(df)

    def tabla_vacia(self) -> None:
        self._ruta = None
        for p in self.paneles:
            p.reiniciar()
        self.panel_datos.modelo.vaciar()
        self.panel_datos.info.setText("Tabla vacía: escribe o pega los datos.")
        self._actualizar_titulo()

    def exportar_grafica(self) -> None:
        base = (self._ruta.stem if self._ruta else "grafica") + ".png"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar gráfica", str(Path(self.ajustes.value(
            "ultima_carpeta", "")) / base), "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if ruta:
            self.grafica.guardar(ruta)
            self.estado(f"Gráfica guardada en {ruta}")

    def guardar_informe(self) -> None:
        texto = self.panel_activo().texto_informe()
        if not texto:
            self.mostrar_error("La pestaña activa todavía no tiene resultados.")
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar informe", "informe.txt", "Texto (*.txt)")
        if ruta:
            Path(ruta).write_text(texto + "\n", encoding="utf-8")
            self.estado(f"Informe guardado en {ruta}")

    def exportar_tabla(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar tabla", "datos.csv", "CSV (*.csv)")
        if ruta:
            self.panel_datos.modelo.a_dataframe().to_csv(ruta, index=False)
            self.estado(f"Tabla guardada en {ruta}")

    # ---------------------------------------------------------- arrastrar/soltar
    def dragEnterEvent(self, evento):
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()

    def dropEvent(self, evento):
        for url in evento.mimeData().urls():
            if url.isLocalFile():
                self.abrir(url.toLocalFile())
                break

    def closeEvent(self, evento):
        self.ajustes.setValue("geometria", self.saveGeometry())
        if self._trabajo is not None:
            self._trabajo.cancelar()
        super().closeEvent(evento)

    def _acerca_de(self) -> None:
        QMessageBox.about(self, "Acerca de ajustelab",
                          f"<b>ajustelab {__version__}</b><br>Ajuste de datos experimentales con base estadística."
                          f"<br><br>Jorge del Río López (WetZap) · Licencia MIT<br><a href='{URL_REPO}'>{URL_REPO}</a>"
                          f"<br><br>Estilo: {self.tema.estilo} · Tema: {'oscuro' if self.tema.oscuro else 'claro'}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("ajustelab")
    app.setOrganizationName("WetZap")
    app.setApplicationVersion(__version__)
    tema = GestorTema(app)
    ventana = VentanaPrincipal(tema)
    ventana.show()
    if len(argv) > 1:
        ventana.abrir(argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
