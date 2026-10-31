"""Ventana principal de ajustelab.

Arranque:  ``ajustelab [fichero o sesión]``  o  ``python -m ajustelab [...]``.

Disposición: la gráfica ocupa el centro; «Datos» y «Análisis» son paneles
acoplables (se pueden mover a cualquier lado, sacar como ventana, ocultar y
restablecer desde Ver). La disposición se recuerda entre sesiones.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("QtAgg")

from PySide6.QtCore import QSettings, QSize, Qt, QThreadPool, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import (QAction, QActionGroup, QDesktopServices, QGuiApplication, QKeySequence,  # noqa: E402
                           QUndoStack)
from PySide6.QtWidgets import (QApplication, QDialog, QDockWidget, QFileDialog, QInputDialog, QLabel,  # noqa: E402
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QStackedWidget, QTabWidget,
                               QToolBar, QVBoxLayout)

from .. import __version__  # noqa: E402
from ..datos import EXTENSIONES, EXT_HOJA, ErrorDatos, hojas, leer_tabla, leer_texto  # noqa: E402
from . import ejemplos, sesion  # noqa: E402
from .acerca import DialogoAcercaDe, ImagenFlotante  # noqa: E402
from .dialogos import DialogoPersonalizar, copiar_figura, exportar, renderizar  # noqa: E402
from .estilo import hoja_estilo  # noqa: E402
from .grafica import COLORES_PUBLICACION, Escena, Grafica, con_coma  # noqa: E402
from .iconos import icono  # noqa: E402
from .paneles import PanelAjuste, PanelInterpolacion, PanelInterseccion, PanelSeleccion  # noqa: E402
from .tabla import PanelDatos  # noqa: E402
from .tema import GestorTema  # noqa: E402
from .trabajos import Trabajo  # noqa: E402
from .widgets import Bienvenida, Notificador  # noqa: E402

URL_REPO = "https://github.com/WetZap/Programa_Python"
MAX_RECIENTES = 8

ATAJOS = [
    ("Ctrl+O", "Abrir datos o sesión"), ("Ctrl+S / Ctrl+Mayús+S", "Guardar sesión / como…"),
    ("Ctrl+N", "Nueva sesión"), ("Ctrl+Mayús+V", "Pegar el portapapeles como tabla nueva"),
    ("Ctrl+Z / Ctrl+Mayús+Z", "Deshacer / rehacer cambios en los datos"),
    ("Ctrl+Intro", "Ejecutar la pestaña activa (ajustar, probar modelos…)"),
    ("Ctrl+1 … Ctrl+4", "Ir a Ajuste, Selección, Interpolación, Intersección"),
    ("Ctrl+E / Ctrl+Mayús+C", "Exportar gráfica / copiarla al portapapeles"),
    ("Clic en un punto", "Excluir o volver a incluir"), ("Región / Rango", "Arrastrar sobre la gráfica"),
    ("Ctrl+C / Ctrl+V en la tabla", "Copiar / pegar un bloque"), ("Supr en la tabla", "Vaciar celdas"),
]


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
        self._trabajos: dict[str, Trabajo] = {}
        self._id_trabajo: dict[str, int] = {}
        self._ruta_datos: Path | None = None
        self._ruta_sesion: Path | None = None
        self._ultima_exportacion: dict | None = None
        self.coma_decimal = self.ajustes.value("coma_decimal", False, type=bool)
        self.pila = QUndoStack(self)

        # --- datos y gráfica
        self.panel_datos = PanelDatos()
        self.panel_datos.modelo.pila = self.pila
        self.grafica = Grafica(tema)
        self.bienvenida = Bienvenida(ejemplos.nombres())
        self.centro = QStackedWidget()
        self.centro.addWidget(self.bienvenida)
        self.centro.addWidget(self.grafica)
        self.setCentralWidget(self.centro)
        self.notificador = Notificador(self.centro)

        # --- pestañas de análisis
        self.paneles = []
        self.pestanas = QTabWidget()
        self.pestanas.setDocumentMode(True)
        for clase in (PanelAjuste, PanelSeleccion, PanelInterpolacion, PanelInterseccion):
            p = clase(self)
            self.paneles.append(p)
            self.pestanas.addTab(p, icono(p.nombre_icono), p.titulo)
        self.p_ajuste, self.p_seleccion, self.p_interp, self.p_inter = self.paneles

        # --- paneles acoplables
        self.dock_datos = self._dock("Datos", "dock_datos", self.panel_datos, Qt.LeftDockWidgetArea)
        self.dock_analisis = self._dock("Análisis", "dock_analisis", self.pestanas, Qt.BottomDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)

        # --- barra de estado con progreso y cancelación
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

        self._crear_acciones()
        self._crear_menus()
        self._crear_barra()
        self.setAcceptDrops(True)
        self.setDockNestingEnabled(True)

        # --- conexiones
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(200)
        self._temporizador.timeout.connect(self._datos_cambiados)
        self.panel_datos.datosCambiados.connect(self._temporizador.start)
        self.grafica.puntoClicado.connect(self.panel_datos.alternar_fila)
        self.grafica.regionSeleccionada.connect(self.panel_datos.modelo.alternar_varias)
        self.grafica.rangoSeleccionado.connect(lambda lo, hi: self.panel_datos.modelo.fijar_rango((lo, hi)))
        self.grafica.personalizar.connect(self.personalizar_grafica)
        self.pestanas.currentChanged.connect(lambda _: self.actualizar_grafica())
        self.pila.cleanChanged.connect(lambda limpio: self.setWindowModified(not limpio))
        self.bienvenida.abrir.connect(self.dialogo_abrir)
        self.bienvenida.pegar.connect(self.pegar_tabla_nueva)
        self.bienvenida.vacia.connect(self.tabla_vacia)
        self.bienvenida.ejemplo.connect(self.abrir_ejemplo)
        self.bienvenida.reciente.connect(self.abrir)
        tema.cambiado.connect(self._aplicar_estilo)

        # --- estado inicial
        self._aplicar_estilo()
        self.panel_datos.modelo.vaciar()
        self._actualizar_recientes()
        self._actualizar_titulo()
        self.resize(1400, 880)
        self.resizeDocks([self.dock_datos], [380], Qt.Horizontal)
        self.resizeDocks([self.dock_analisis], [330], Qt.Vertical)
        self._disposicion_inicial = self.saveState()
        geometria = self.ajustes.value("geometria")
        if geometria is not None:
            self.restoreGeometry(geometria)
        disposicion = self.ajustes.value("disposicion")
        if disposicion is not None:
            self.restoreState(disposicion)
        self.centro.setCurrentWidget(self.bienvenida)
        self.estado("Abre un fichero (Ctrl+O), arrástralo a la ventana, pega datos o prueba un ejemplo.")

    # ------------------------------------------------------------ construcción
    def _dock(self, titulo, nombre, widget, area) -> QDockWidget:
        d = QDockWidget(titulo, self)
        d.setObjectName(nombre)
        d.setWidget(widget)
        d.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(area, d)
        return d

    def _accion(self, texto, funcion, atajo=None, nombre_icono=None, ayuda=None) -> QAction:
        a = QAction(texto, self)
        if nombre_icono:
            a.setIcon(icono(nombre_icono))
        if atajo is not None:
            a.setShortcuts(atajo if isinstance(atajo, list) else [atajo])
        if ayuda:
            a.setToolTip(ayuda)
            a.setStatusTip(ayuda)
        a.triggered.connect(funcion)
        return a

    def _crear_acciones(self) -> None:
        A = self._accion
        self.a_nueva = A("&Nueva sesión", self.nueva_sesion, QKeySequence.New, "nuevo")
        self.a_abrir = A("&Abrir…", self.dialogo_abrir, QKeySequence.Open, "abrir", "Abrir datos o una sesión")
        self.a_pegar = A("Pegar como tabla &nueva", self.pegar_tabla_nueva, QKeySequence("Ctrl+Shift+V"), "pegar")
        self.a_guardar = A("&Guardar sesión", self.guardar_sesion, QKeySequence.Save, "guardar",
                           "Guarda datos, configuración y pestañas en un fichero .ajustelab")
        self.a_guardar_como = A("Guardar sesión &como…", lambda: self.guardar_sesion(como=True),
                                QKeySequence("Ctrl+Shift+S"))
        self.a_exportar = A("Exportar &gráfica…", self.exportar_grafica, QKeySequence("Ctrl+E"), "exportar",
                            "PNG, PDF o SVG con tamaño y resolución para publicación")
        self.a_copiar_graf = A("Copiar gráfica", self.copiar_grafica, QKeySequence("Ctrl+Shift+C"), "copiar",
                               "Copia la gráfica al portapapeles (estilo de publicación)")
        self.a_informe = A("Guardar &informe…", self.guardar_informe)
        self.a_tabla = A("Exportar &tabla (CSV)…", self.exportar_tabla)
        self.a_salir = A("&Salir", self.close, QKeySequence.Quit)
        self.a_deshacer = self.pila.createUndoAction(self, "Deshacer")
        self.a_deshacer.setShortcuts(QKeySequence.Undo)
        self.a_deshacer.setIcon(icono("deshacer"))
        self.a_rehacer = self.pila.createRedoAction(self, "Rehacer")
        self.a_rehacer.setShortcuts([QKeySequence.Redo, QKeySequence("Ctrl+Shift+Z")])
        self.a_rehacer.setIcon(icono("rehacer"))
        # En la barra, texto fijo (el del menú cambia: «Deshacer excluir punto»…)
        self.b_deshacer = A("Deshacer", self.pila.undo, None, "deshacer")
        self.b_rehacer = A("Rehacer", self.pila.redo, None, "rehacer")
        for b, puede, texto in ((self.b_deshacer, self.pila.canUndoChanged, self.pila.undoTextChanged),
                                (self.b_rehacer, self.pila.canRedoChanged, self.pila.redoTextChanged)):
            b.setEnabled(False)
            puede.connect(b.setEnabled)
            texto.connect(lambda t, b=b: b.setToolTip(f"{b.text()} {t}".strip()))
        self.a_ejecutar = A("&Ejecutar", self.ejecutar_pestana, [QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")],
                            "ajustar", "Ejecuta la pestaña activa: ajustar, probar modelos, interpolar… (Ctrl+Intro)")
        self.a_personalizar = A("&Personalizar gráfica…", self.personalizar_grafica, None, "personalizar")

    def _crear_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        m.addAction(self.a_nueva)
        m.addAction(self.a_abrir)
        self.menu_recientes = m.addMenu("Abrir &reciente")
        m_ej = m.addMenu(icono("ejemplo"), "Datos de &ejemplo")
        for clave, nombre in ejemplos.nombres().items():
            m_ej.addAction(nombre, lambda c=clave: self.abrir_ejemplo(c))
        m.addAction(self.a_pegar)
        m.addSeparator()
        m.addAction(self.a_guardar)
        m.addAction(self.a_guardar_como)
        m.addSeparator()
        m.addAction(self.a_exportar)
        m.addAction(self.a_copiar_graf)
        m.addAction(self.a_informe)
        m.addAction(self.a_tabla)
        m.addSeparator()
        m.addAction(self.a_salir)

        m = mb.addMenu("&Editar")
        m.addAction(self.a_deshacer)
        m.addAction(self.a_rehacer)
        m.addSeparator()
        m.addAction(self._accion("&Incluir todos los puntos", self.panel_datos.incluir_todas))
        m.addAction(self._accion("&Quitar rango de ajuste", lambda: self.panel_datos.modelo.fijar_rango(None)))
        m.addAction(self._accion("&Añadir fila", lambda: self.panel_datos.modelo.insertar_filas(1)))
        m.addAction(self._accion("&Borrar filas seleccionadas", self.panel_datos.borrar_filas_seleccionadas))

        m = mb.addMenu("A&nálisis")
        m.addAction(self.a_ejecutar)
        m.addSeparator()
        for i, p in enumerate(self.paneles):
            m.addAction(self._accion(p.titulo, lambda _=False, i=i: self._ir_a(i), QKeySequence(f"Ctrl+{i + 1}"),
                                     p.nombre_icono))

        m = mb.addMenu("&Ver")
        sub = m.addMenu("&Tema")
        grupo = QActionGroup(self)
        for clave, texto in (("sistema", "Seguir al &sistema"), ("claro", "&Claro"), ("oscuro", "&Oscuro")):
            a = QAction(texto, self, checkable=True)
            a.setChecked(self.tema.preferencia == clave)
            a.triggered.connect(lambda _=False, c=clave: self.tema.fijar_preferencia(c))
            grupo.addAction(a)
            sub.addAction(a)
        self.a_coma = QAction("Coma &decimal en resultados (3,14)", self, checkable=True)
        self.a_coma.setChecked(self.coma_decimal)
        self.a_coma.toggled.connect(self.fijar_coma_decimal)
        m.addAction(self.a_coma)
        m.addAction(self.a_personalizar)
        m.addSeparator()
        m.addAction(self.dock_datos.toggleViewAction())
        m.addAction(self.dock_analisis.toggleViewAction())
        self.menu_ver = m
        m.addAction(self._accion("&Restablecer disposición", self.restablecer_disposicion))

        m = mb.addMenu("A&yuda")
        m.addAction(self._accion("&Atajos de teclado", self._mostrar_atajos))
        m.addAction(self._accion("&Repositorio en GitHub", lambda: QDesktopServices.openUrl(QUrl(URL_REPO))))
        m.addAction(self._accion("Acerca &de ajustelab", self._acerca_de, None, "info"))

    def _crear_barra(self) -> None:
        barra = QToolBar("Barra de herramientas")
        barra.setObjectName("barra_principal")
        barra.setIconSize(QSize(20, 20))
        barra.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for a in (self.a_abrir, self.a_guardar, None, self.b_deshacer, self.b_rehacer, None, self.a_ejecutar, None,
                  self.a_exportar, self.a_copiar_graf):
            if a is None:
                barra.addSeparator()
            else:
                barra.addAction(a)
        self.addToolBar(barra)
        self.menu_ver.insertAction(self.menu_ver.actions()[-1], barra.toggleViewAction())

    # ------------------------------------------------------------ utilidades
    def estado(self, texto: str) -> None:
        self.mensaje.setText(texto)

    def notificar(self, texto: str, estado: str = "neutro") -> None:
        self.notificador.mostrar(texto, estado)
        self.estado(texto)

    def mostrar_error(self, texto: str) -> None:
        self.estado(f"⚠ {texto}")
        QMessageBox.warning(self, "ajustelab", texto)

    def fmt(self, texto: str) -> str:
        """Aplica la preferencia de coma decimal a un texto de resultados."""
        return con_coma(texto) if self.coma_decimal else texto

    def fijar_coma_decimal(self, activa: bool) -> None:
        self.coma_decimal = activa
        self.ajustes.setValue("coma_decimal", activa)
        if self.p_ajuste.resultado is not None:
            self.p_ajuste.mostrar_resultado(self.p_ajuste.resultado, silencioso=True)
        if self.p_seleccion.seleccion is not None:
            self.p_seleccion.mostrar(self.p_seleccion.seleccion)
        if self.p_interp.resultado is not None:
            self.p_interp.salida.setPlainText(self.fmt(self.p_interp.resultado.resumen()))
        if self.p_inter.resultado is not None:
            self.p_inter.mostrar(self.p_inter.resultado)
        self.actualizar_grafica()

    def _aplicar_estilo(self) -> None:
        self.setStyleSheet(hoja_estilo(self.tema.colores(), self.tema.oscuro, self.tema.estilo == "Fusion"))

    def _actualizar_titulo(self) -> None:
        if self._ruta_sesion:
            nombre = self._ruta_sesion.name
        elif self._ruta_datos:
            nombre = self._ruta_datos.name
        else:
            nombre = "sin título"
        self.setWindowTitle(f"{nombre}[*] — ajustelab {__version__}")

    def obtener_datos(self, silencioso: bool = False):
        try:
            return self.panel_datos.datos()
        except ErrorDatos as e:
            if not silencioso:
                self.mostrar_error(str(e))
            return None

    def _ir_a(self, indice: int) -> None:
        self.dock_analisis.show()
        self.pestanas.setCurrentIndex(indice)

    # ---------------------------------------------------- trabajos en segundo plano
    def lanzar(self, trabajo: Trabajo, al_terminar, texto: str, cancelable: bool = False,
               canal: str | None = None) -> None:
        """Ejecuta en segundo plano. Un trabajo nuevo en el mismo canal (por defecto,
        la pestaña activa) hace que se ignore el resultado del anterior."""
        canal = canal or self.panel_activo().titulo
        if canal in self._trabajos:
            self._trabajos[canal].cancelar()
        ident = self._id_trabajo.get(canal, 0) + 1
        self._id_trabajo[canal] = ident
        self._trabajos[canal] = trabajo
        s = trabajo.senales

        def vigente():
            return self._id_trabajo.get(canal) == ident

        def fin(mensaje: str):
            if vigente():
                self._trabajos.pop(canal, None)
                if not self._trabajos:
                    self.progreso.setVisible(False)
                    self.b_cancelar.setVisible(False)
                if mensaje:
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
        self.progreso.setRange(0, 0)
        self.progreso.setVisible(True)
        self.b_cancelar.setVisible(cancelable)
        QThreadPool.globalInstance().start(trabajo)

    @property
    def _trabajo(self):
        """Compatibilidad: algún trabajo en curso (o None)."""
        return next(iter(self._trabajos.values()), None)

    def _cancelar(self) -> None:
        for t in self._trabajos.values():
            t.cancelar()
        self.estado("Cancelando…")

    def esperar_trabajos(self, ms: int = 60000) -> bool:
        """Espera a que terminen los trabajos en curso (útil en pruebas)."""
        return QThreadPool.globalInstance().waitForDone(ms)

    # ----------------------------------------------------------- coordinación
    def panel_activo(self):
        return self.paneles[self.pestanas.currentIndex()] if self.paneles else None

    def ejecutar_pestana(self) -> None:
        p = self.panel_activo()
        accion = {PanelAjuste: "ajustar", PanelSeleccion: "ejecutar", PanelInterpolacion: "interpolar",
                  PanelInterseccion: "calcular"}[type(p)]
        getattr(p, accion)()

    def actualizar_grafica(self) -> None:
        if not getattr(self, "paneles", None) or len(self.paneles) < 4:
            return  # todavía construyéndose
        obtenidos = self.obtener_datos(silencioso=True)
        if obtenidos is None:
            self.grafica.mostrar(Escena())
            return
        datos, filas = obtenidos
        escena = self.panel_activo().escena(datos, filas)
        escena.rango = self.panel_datos.modelo.rango_x
        escena.coma_decimal = self.coma_decimal
        self.grafica.mostrar(escena)

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
            if obtenidos is not None and not self.p_ajuste.tiene_resultado():
                self.p_ajuste.al_cambiar_datos()
            self.actualizar_grafica()

    def usar_en_ajuste(self, resultado) -> None:
        self.p_ajuste.usar(resultado)
        self.pestanas.setCurrentWidget(self.p_ajuste)

    # --------------------------------------------------------------- ficheros
    def _patrones(self) -> str:
        datos = " ".join(f"*{e}" for e in EXTENSIONES)
        return (f"Datos y sesiones ({datos} *{sesion.EXTENSION});;Sesión de ajustelab (*{sesion.EXTENSION});;"
                f"Datos ({datos});;Todos los ficheros (*)")

    def dialogo_abrir(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir", self.ajustes.value("ultima_carpeta", ""),
                                              self._patrones())
        if ruta:
            self.abrir(ruta)

    def abrir(self, ruta) -> bool:
        ruta = Path(ruta)
        if ruta.suffix == sesion.EXTENSION:
            return self.abrir_sesion(ruta)
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
        if not self._confirmar_descartar():
            return False
        self._ruta_datos, self._ruta_sesion = ruta, None
        self.ajustes.setValue("ultima_carpeta", str(ruta.parent))
        self.cargar_tabla(df, _describir(df))
        self._añadir_reciente(ruta)
        self.notificar(f"Abierto {ruta.name}", "bueno")
        return True

    def cargar_tabla(self, df, descripcion: str) -> None:
        for p in self.paneles:
            p.reiniciar()
        self.panel_datos.cargar(df, descripcion)
        self.pila.clear()
        obtenidos = self.obtener_datos(silencioso=True)
        if obtenidos is not None:  # antes de que una sesión o un ejemplo fijen n
            self.p_inter.actualizar_rango(obtenidos[0].n_total)
        self.centro.setCurrentWidget(self.grafica)
        self._actualizar_titulo()
        self.actualizar_grafica()

    def abrir_ejemplo(self, clave: str) -> None:
        if not self._confirmar_descartar():
            return
        df, descripcion = ejemplos.generar(clave)
        self._ruta_datos = self._ruta_sesion = None
        self.cargar_tabla(df, descripcion)
        sugerencia = {"descarga": (0, "exponencial_fondo"), "pico": (1, None), "pendulo": (0, "seno_amortiguado"),
                      "rectas": (3, None), "calibracion": (2, None)}[clave]
        self.pestanas.setCurrentIndex(sugerencia[0])
        if sugerencia[1]:
            self.p_ajuste.selector.seleccionar_clave(sugerencia[1])
        if clave == "rectas":
            self.p_inter.n.setValue(8)
        self.notificar(f"{ejemplos.nombres()[clave]} — pulsa Ctrl+Intro para calcular.", "neutro")

    def pegar_tabla_nueva(self) -> None:
        texto = QGuiApplication.clipboard().text()
        try:
            df = leer_texto(texto)
        except ErrorDatos as e:
            self.mostrar_error(f"El portapapeles no contiene una tabla de números: {e}")
            return
        if not self._confirmar_descartar():
            return
        self._ruta_datos = self._ruta_sesion = None
        self.cargar_tabla(df, _describir(df))

    def tabla_vacia(self) -> None:
        if not self._confirmar_descartar():
            return
        self._ruta_datos = self._ruta_sesion = None
        for p in self.paneles:
            p.reiniciar()
        self.panel_datos.modelo.vaciar()
        self.panel_datos.info.setText("Tabla vacía: escribe o pega los datos.")
        self.centro.setCurrentWidget(self.grafica)
        self.dock_datos.show()
        self._actualizar_titulo()

    def nueva_sesion(self) -> None:
        if not self._confirmar_descartar():
            return
        self._ruta_datos = self._ruta_sesion = None
        for p in self.paneles:
            p.reiniciar()
        self.panel_datos.modelo.vaciar()
        self.panel_datos.info.setText("Sin datos")
        self.pila.clear()
        self.centro.setCurrentWidget(self.bienvenida)
        self._actualizar_titulo()

    # ---------------------------------------------------------------- sesiones
    def guardar_sesion(self, como: bool = False) -> bool:
        ruta = self._ruta_sesion
        if ruta is None or como:
            base = (self._ruta_datos.stem if self._ruta_datos else "sesion") + sesion.EXTENSION
            carpeta = Path(self.ajustes.value("ultima_carpeta", ""))
            r, _ = QFileDialog.getSaveFileName(self, "Guardar sesión", str(carpeta / base),
                                               f"Sesión de ajustelab (*{sesion.EXTENSION})")
            if not r:
                return False
            ruta = Path(r)
        try:
            ruta = sesion.guardar(self, ruta)
        except OSError as e:
            self.mostrar_error(f"No se ha podido guardar: {e}")
            return False
        self._ruta_sesion = ruta
        self.pila.setClean()
        self._añadir_reciente(ruta)
        self._actualizar_titulo()
        self.notificar(f"Sesión guardada en {ruta.name}", "bueno")
        return True

    def abrir_sesion(self, ruta: Path) -> bool:
        try:
            d = sesion.leer(ruta)
        except sesion.ErrorSesion as e:
            self.mostrar_error(str(e))
            return False
        if not self._confirmar_descartar():
            return False
        sesion.restaurar(self, d)
        self._ruta_sesion = ruta
        self._ruta_datos = Path(d["origen"]) if d.get("origen") else None
        self.pila.setClean()
        self._añadir_reciente(ruta)
        self._actualizar_titulo()
        self.notificar(f"Sesión {ruta.name} restaurada", "bueno")
        return True

    def _confirmar_descartar(self) -> bool:
        """Si hay cambios sin guardar, pregunta antes de perderlos."""
        if self.pila.isClean():
            return True
        r = QMessageBox.question(self, "Cambios sin guardar", "Hay cambios en los datos sin guardar. "
                                 "¿Quieres guardar la sesión antes de continuar?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.guardar_sesion()
        return r == QMessageBox.Discard

    # ---------------------------------------------------------------- recientes
    def _recientes(self) -> list[str]:
        valor = self.ajustes.value("recientes", [])
        return [valor] if isinstance(valor, str) else list(valor or [])

    def _añadir_reciente(self, ruta: Path) -> None:
        r = str(Path(ruta).resolve())
        lista = [r] + [x for x in self._recientes() if x != r]
        self.ajustes.setValue("recientes", lista[:MAX_RECIENTES])
        self._actualizar_recientes()

    def _actualizar_recientes(self) -> None:
        lista = [r for r in self._recientes() if Path(r).exists()]
        self.menu_recientes.clear()
        for r in lista:
            self.menu_recientes.addAction(Path(r).name, lambda _=False, ruta=r: self.abrir(ruta)).setToolTip(r)
        self.menu_recientes.setEnabled(bool(lista))
        if lista:
            self.menu_recientes.addSeparator()
            self.menu_recientes.addAction("Vaciar lista", lambda: (self.ajustes.setValue("recientes", []),
                                                                   self._actualizar_recientes()))
        self.bienvenida.fijar_recientes(lista)

    # ---------------------------------------------------------------- exportar
    def exportar_grafica(self) -> None:
        if self.centro.currentWidget() is not self.grafica:
            self.mostrar_error("Todavía no hay ninguna gráfica.")
            return
        base = (self._ruta_datos.stem if self._ruta_datos else "grafica") + ".png"
        v = exportar(self, self.grafica, self._ultima_exportacion,
                     str(Path(self.ajustes.value("ultima_carpeta", "")) / base))
        if v is not None:
            self._ultima_exportacion = v

    def copiar_grafica(self) -> None:
        v = self._ultima_exportacion or {"ancho": 16.0, "alto": 11.0}
        fig = renderizar(self.grafica.escena, self.grafica.opciones, COLORES_PUBLICACION, False, v["ancho"], v["alto"])
        copiar_figura(fig)
        self.notificar("Gráfica copiada al portapapeles.", "bueno")

    def personalizar_grafica(self) -> None:
        dlg = DialogoPersonalizar(self.grafica.opciones, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.aplicar(self.grafica.opciones)
            self.grafica.redibujar()

    def guardar_informe(self) -> None:
        texto = self.panel_activo().texto_informe()
        if not texto:
            self.mostrar_error("La pestaña activa todavía no tiene resultados.")
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar informe", "informe.txt", "Texto (*.txt)")
        if ruta:
            Path(ruta).write_text(texto + "\n", encoding="utf-8")
            self.notificar(f"Informe guardado en {ruta}", "bueno")

    def exportar_tabla(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar tabla", "datos.csv", "CSV (*.csv)")
        if ruta:
            self.panel_datos.modelo.a_dataframe().to_csv(ruta, index=False)
            self.notificar(f"Tabla guardada en {ruta}", "bueno")

    # ---------------------------------------------------------- disposición
    def restablecer_disposicion(self) -> None:
        self.restoreState(self._disposicion_inicial)
        for d in (self.dock_datos, self.dock_analisis):
            d.setFloating(False)
            d.show()

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
        if not self._confirmar_descartar():
            evento.ignore()
            return
        self.ajustes.setValue("geometria", self.saveGeometry())
        self.ajustes.setValue("disposicion", self.saveState())
        self._cancelar()
        super().closeEvent(evento)

    # ---------------------------------------------------------------- ayuda
    def _mostrar_atajos(self) -> None:
        filas = "".join(f"<tr><td style='padding-right:18px'><b>{a}</b></td><td>{b}</td></tr>" for a, b in ATAJOS)
        dlg = QDialog(self)
        dlg.setWindowTitle("Atajos de teclado")
        capa = QVBoxLayout(dlg)
        etiqueta = QLabel(f"<table>{filas}</table><p style='color:gray'>En macOS, Ctrl equivale a ⌘.</p>")
        capa.addWidget(etiqueta)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(dlg.accept)
        capa.addWidget(cerrar, 0, Qt.AlignRight)
        dlg.exec()

    def _acerca_de(self) -> None:
        DialogoAcercaDe(self, self.tema.estilo, "oscuro" if self.tema.oscuro else "claro").exec()

    def mostrar_sorpresa(self) -> ImagenFlotante:
        return ImagenFlotante(self).mostrar()


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
