"""Diálogo «Personalizar gráfica» y plantillas de estilo.

Pestañas: Textos, Ejes, Leyenda, Datos y curvas, Marcas, Textos libres y Estilo. Lo que
se ve en la gráfica (título, leyenda, etiquetas de los ejes y textos libres)
también se mueve arrastrándolo y se edita con doble clic; aquí está todo lo demás
y la forma de volver cada cosa a su sitio.

Una plantilla es solo el *estilo* (tamaños, marcas, rejilla, leyenda, colores…),
no los textos, los límites ni las posiciones, que dependen de cada gráfica. Hay
plantillas de fábrica y se pueden guardar las propias (en la configuración del
usuario, ``QSettings``). Un estilo puede quedar como el predeterminado de las
gráficas nuevas.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .grafica import (BORDES, CLAVES_ESTILO, ESTILOS_LINEA, FORMAS_MARCA, LOC_LEYENDA, MARCA_DEFECTO, MARCAS,
                      NOTACION, TIPOS_MARCA, OpcionesGrafica)

PLANTILLAS = {
    "Por defecto": {},
    "Revista (física)": {
        "marcas": "dentro", "marcas_espejo": True, "marcas_menores": True, "rejilla": False, "leyenda_marco": False,
        "tam_marcador": 4.0, "grosor_linea": 1.2, "grosor_ajuste": 1.5, "grosor_error": 0.8, "tam_tapa": 0.0,
    },
    "Presentación": {
        "tam_fuente": 14.0, "titulo_negrita": True, "tam_marcador": 7.0, "grosor_linea": 2.4, "grosor_ajuste": 3.0,
        "grosor_error": 1.5, "tam_tapa": 3.0,
    },
    "Minimalista": {
        "bordes": "abiertos", "alin_titulo": "left", "titulo_negrita": True, "leyenda_marco": False,
        "rejilla": True, "tam_tapa": 0.0,
    },
}
ALINEACION = {"left": "A la izquierda", "center": "En el centro", "right": "A la derecha"}
_CLAVE_PLANTILLAS = "plantillas_grafica"
_CLAVE_ESTILO = "estilo_grafica"


# --- plantillas guardadas ---------------------------------------------------------
def _leer_json(ajustes: QSettings, clave: str, defecto):
    try:
        valor = json.loads(ajustes.value(clave, "") or "null")
    except (TypeError, ValueError):
        return defecto
    return valor if isinstance(valor, type(defecto)) else defecto


def plantillas_usuario(ajustes: QSettings | None = None) -> dict[str, dict]:
    return _leer_json(ajustes or QSettings(), _CLAVE_PLANTILLAS, {})


def guardar_plantilla(nombre: str, estilo: dict, ajustes: QSettings | None = None) -> None:
    ajustes = ajustes or QSettings()
    todas = plantillas_usuario(ajustes)
    todas[nombre] = {k: v for k, v in estilo.items() if k in CLAVES_ESTILO}
    ajustes.setValue(_CLAVE_PLANTILLAS, json.dumps(todas))


def borrar_plantilla(nombre: str, ajustes: QSettings | None = None) -> None:
    ajustes = ajustes or QSettings()
    todas = plantillas_usuario(ajustes)
    todas.pop(nombre, None)
    ajustes.setValue(_CLAVE_PLANTILLAS, json.dumps(todas))


def estilo_predeterminado(ajustes: QSettings | None = None) -> dict:
    return _leer_json(ajustes or QSettings(), _CLAVE_ESTILO, {})


def fijar_estilo_predeterminado(estilo: dict | None, ajustes: QSettings | None = None) -> None:
    ajustes = ajustes or QSettings()
    if estilo:
        ajustes.setValue(_CLAVE_ESTILO, json.dumps({k: v for k, v in estilo.items() if k in CLAVES_ESTILO}))
    else:
        ajustes.remove(_CLAVE_ESTILO)


def opciones_nuevas(ajustes: QSettings | None = None) -> OpcionesGrafica:
    """Opciones de una gráfica nueva, con el estilo predeterminado del usuario."""
    o = OpcionesGrafica()
    estilo = estilo_predeterminado(ajustes)
    if estilo:
        o.aplicar_estilo(estilo)
    return o


# --- utilidades de los controles ---------------------------------------------------
def _numero(texto: str) -> float | None:
    texto = texto.strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _texto_numero(v) -> str:
    return "" if v is None else f"{v:g}"


def _giro(minimo, maximo, paso, decimales=1, automatico: str | None = None) -> QDoubleSpinBox:
    g = QDoubleSpinBox()
    g.setRange(minimo, maximo)
    g.setSingleStep(paso)
    g.setDecimals(decimales)
    if automatico:
        g.setSpecialValueText(automatico)  # el mínimo (0) se muestra como «Automático»
    return g


def _combo(opciones: dict) -> QComboBox:
    c = QComboBox()
    for k, v in opciones.items():
        c.addItem(v, k)
    return c


def _fijar_combo(c: QComboBox, dato) -> None:
    c.setCurrentIndex(max(0, c.findData(dato)))


class BotonColor(QPushButton):
    """Botón con una muestra del color; vacío = el del tema («Automático»)."""

    def __init__(self, titulo: str):
        super().__init__()
        self.titulo = titulo
        self.color = ""
        self.clicked.connect(self._elegir)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _p: self.fijar(""))
        self.setToolTip("Clic para elegir; clic derecho para volver al color del tema")
        self.fijar("")

    def fijar(self, color: str) -> None:
        self.color = color or ""
        if self.color:
            pm = QPixmap(14, 14)
            pm.fill(QColor(self.color))
            self.setIcon(QIcon(pm))
            self.setText(self.color)
        else:
            self.setIcon(QIcon())
            self.setText("Automático (tema)")

    def _elegir(self) -> None:
        color = QColorDialog.getColor(QColor(self.color or "#2f7ed8"), self, self.titulo)
        if color.isValid():
            self.fijar(color.name())


def describir_marca(m: dict) -> str:
    m = {**MARCA_DEFECTO, **m}
    tipo = m["tipo"]
    if tipo == "punto":
        donde = f"({m['x']:.6g}, {m['y']:.6g})"
    elif tipo == "tramo":
        donde = f"x de {min(m['x'], m['x2']):.6g} a {max(m['x'], m['x2']):.6g}"
    elif tipo == "vertical":
        donde = f"x = {m['x']:.6g}"
    else:
        donde = f"y = {m['y']:.6g}"
    return f"{TIPOS_MARCA.get(tipo, tipo)} {donde}" + (f" — «{m['texto']}»" if m["texto"] else "")


class DialogoMarca(QDialog):
    """Una marca: punto, tramo de x o línea vertical u horizontal, con su texto,
    color, forma, tamaño, estilo de línea y transparencia."""

    def __init__(self, marca: dict | None = None, parent=None, titulo: str = "Marca", doble_eje: bool = False):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        m = {**MARCA_DEFECTO, **(marca or {})}
        self.tipo = _combo(TIPOS_MARCA)
        self.x = QLineEdit()
        self.y = QLineEdit()
        self.x2 = QLineEdit()
        self.texto = QLineEdit()
        self.texto.setPlaceholderText("sin texto")
        self.texto.setToolTip("Admite LaTeX entre $…$")
        self.color = BotonColor("Color de la marca")
        self.forma = _combo(FORMAS_MARCA)
        self.tam = _giro(2, 60, 1, 0)
        self.relleno = QCheckBox("Rellena (si no, un aro alrededor del punto)")
        self.estilo = _combo(ESTILOS_LINEA)
        self.grosor = _giro(0.2, 10, 0.2)
        self.alfa = _giro(0.02, 1, 0.05, 2)
        self.leyenda = QCheckBox("El texto va en la leyenda (no junto a la marca)")
        self.eje = _combo({"izq": "Izquierdo", "der": "Derecho"})
        self.eje.setToolTip("Con dos ejes y: a qué eje se refiere la y")
        self._form = QFormLayout()
        f = self._form
        f.addRow("Tipo:", self.tipo)
        f.addRow("x:", self.x)
        f.addRow("hasta x:", self.x2)
        f.addRow("y:", self.y)
        f.addRow("Eje y:", self.eje)
        f.addRow("Texto:", self.texto)
        f.addRow("Color:", self.color)
        f.addRow("Forma:", self.forma)
        f.addRow("Tamaño:", self.tam)
        f.addRow("", self.relleno)
        f.addRow("Línea:", self.estilo)
        f.addRow("Grosor:", self.grosor)
        f.addRow("Opacidad:", self.alfa)
        f.addRow("", self.leyenda)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        self.aviso = QLabel()
        self.aviso.setObjectName("secundario")
        capa = QVBoxLayout(self)
        capa.addLayout(f)
        capa.addWidget(self.aviso)
        capa.addWidget(botones)
        self._doble_eje = doble_eje
        _fijar_combo(self.tipo, m["tipo"])
        self.x.setText(_texto_numero(m["x"]))
        self.y.setText(_texto_numero(m["y"]))
        self.x2.setText(_texto_numero(m["x2"]))
        self.texto.setText(m["texto"])
        self.color.fijar(m["color"])
        _fijar_combo(self.forma, m["forma"])
        self.tam.setValue(float(m["tam"]))
        self.relleno.setChecked(bool(m["relleno"]))
        _fijar_combo(self.estilo, m["estilo"])
        self.grosor.setValue(float(m["grosor"]))
        self.alfa.setValue(float(m["alfa"]))
        self.leyenda.setChecked(bool(m["leyenda"]))
        _fijar_combo(self.eje, m["eje"])
        self.tipo.currentIndexChanged.connect(self._ver_campos)
        self._ver_campos()

    def _ver_campos(self, *_):
        t = self.tipo.currentData()
        filas = {self.x2: t == "tramo", self.y: t in ("punto", "horizontal"),
                 self.eje: self._doble_eje and t in ("punto", "horizontal"),
                 self.forma: t == "punto", self.tam: t == "punto", self.relleno: t == "punto",
                 self.estilo: t in ("vertical", "horizontal"), self.grosor: t in ("vertical", "horizontal"),
                 self.alfa: t == "tramo", self.x: t != "horizontal"}
        for w, visible in filas.items():
            self._form.setRowVisible(w, visible)
        self.adjustSize()

    def marca(self) -> dict:
        t = self.tipo.currentData()
        m = {**MARCA_DEFECTO, "tipo": t, "texto": self.texto.text().strip(), "color": self.color.color,
             "forma": self.forma.currentData(), "tam": self.tam.value(), "relleno": self.relleno.isChecked(),
             "estilo": self.estilo.currentData(), "grosor": self.grosor.value(), "alfa": self.alfa.value(),
             "leyenda": self.leyenda.isChecked(), "eje": self.eje.currentData()}
        for clave, campo in (("x", self.x), ("y", self.y), ("x2", self.x2)):
            v = _numero(campo.text())
            m[clave] = v if v is not None else MARCA_DEFECTO[clave]
        if t != "punto" and t != "horizontal":
            m["y"] = _numero(self.y.text())
        return m

    def _aceptar(self) -> None:
        t = self.tipo.currentData()
        faltan = [n for n, campo, hace_falta in (("x", self.x, t != "horizontal"),
                                                 ("hasta x", self.x2, t == "tramo"),
                                                 ("y", self.y, t in ("punto", "horizontal")))
                  if hace_falta and _numero(campo.text()) is None]
        if faltan:
            self.aviso.setText("Falta un número en: " + ", ".join(faltan) + ".")
            return
        self.accept()


class DialogoPersonalizar(QDialog):
    """Todas las opciones de la gráfica, por pestañas. ``al_aplicar(dialogo)`` se
    llama con «Aplicar» para ver el cambio sin cerrar."""

    PESTANAS = ("textos", "ejes", "leyenda", "datos", "marcas", "notas", "estilo")

    def __init__(self, opciones: OpcionesGrafica, parent=None, pestana: str | None = None, al_aplicar=None,
                 ajustes: QSettings | None = None):
        super().__init__(parent)
        self.setWindowTitle("Personalizar gráfica")
        self._original = opciones
        self._ajustes = ajustes or QSettings()
        self._al_aplicar = al_aplicar
        self._restablecer_posiciones = False
        self._loc_tocada = False
        self._alin_tocada = False
        self.pestanas = QTabWidget()
        self.pestanas.addTab(self._pagina_textos(), "Textos")
        self.pestanas.addTab(self._pagina_ejes(), "Ejes")
        self.pestanas.addTab(self._pagina_leyenda(), "Leyenda")
        self.pestanas.addTab(self._pagina_datos(), "Datos y curvas")
        self.pestanas.addTab(self._pagina_marcas(), "Marcas")
        self.pestanas.addTab(self._pagina_notas(), "Textos libres")
        self.pestanas.addTab(self._pagina_estilo(), "Estilo")
        self._fijar_controles(opciones)
        if pestana in self.PESTANAS:
            self.pestanas.setCurrentIndex(self.PESTANAS.index(pestana))

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
                                   | QDialogButtonBox.Reset)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        botones.button(QDialogButtonBox.Apply).setText("Aplicar")
        botones.button(QDialogButtonBox.Apply).clicked.connect(self._aplicar_ya)
        botones.button(QDialogButtonBox.Apply).setEnabled(al_aplicar is not None)
        reset = botones.button(QDialogButtonBox.Reset)
        reset.setText("Restablecer todo")
        reset.setToolTip("Vuelve a las opciones de fábrica (también textos, límites y posiciones)")
        reset.clicked.connect(self._restablecer)
        capa = QVBoxLayout(self)
        capa.addWidget(self.pestanas)
        capa.addWidget(botones)
        self.resize(560, 470)

    # -- páginas ----------------------------------------------------------------
    def _pagina_textos(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.titulo = QLineEdit()
        self.titulo.setPlaceholderText("sin título")
        self.alin_titulo = _combo(ALINEACION)
        self.alin_titulo.activated.connect(lambda _i: setattr(self, "_alin_tocada", True))
        self.tam_titulo = _giro(0, 48, 0.5, automatico="Automático")
        self.titulo_negrita = QCheckBox("Negrita")
        self.ex = QLineEdit()
        self.ey = QLineEdit()
        self.ey2 = QLineEdit()
        for campo, ayuda in ((self.ex, "nombre de la columna"), (self.ey, "nombre de la columna"),
                             (self.ey2, "nombre de la columna (pestaña Representar)")):
            campo.setPlaceholderText(ayuda)
        for campo in (self.titulo, self.ex, self.ey, self.ey2):
            campo.setToolTip("Admite fórmulas LaTeX entre $…$, p. ej. $\\lambda$ (nm) o $t$ (s)")
        self.tam_fuente = _giro(5, 30, 0.5)
        fila = QHBoxLayout()
        fila.addWidget(self.alin_titulo, 1)
        fila.addWidget(self.tam_titulo)
        fila.addWidget(self.titulo_negrita)
        form.addRow("Título:", self.titulo)
        form.addRow("", fila)
        form.addRow("Eje x:", self.ex)
        form.addRow("Eje y:", self.ey)
        form.addRow("Eje y derecho:", self.ey2)
        form.addRow("Tamaño de letra:", self.tam_fuente)
        b = QPushButton("Devolver título, etiquetas, leyenda y cuadro a su sitio")
        b.setToolTip("Deshace lo que hayas movido arrastrando en la gráfica")
        b.clicked.connect(self._marcar_restablecer_posiciones)
        self.aviso_posiciones = QLabel()
        self.aviso_posiciones.setObjectName("secundario")
        form.addRow(b)
        form.addRow(self.aviso_posiciones)
        nota = QLabel("En la gráfica: arrastra el título, la leyenda, las etiquetas y los textos para moverlos; "
                      "doble clic para editarlos.")
        nota.setWordWrap(True)
        nota.setObjectName("secundario")
        form.addRow(nota)
        return w

    def _pagina_ejes(self) -> QWidget:
        w = QWidget()
        capa = QVBoxLayout(w)
        rejilla = QGridLayout()
        rejilla.addWidget(QLabel("Límites"), 0, 0)
        rejilla.addWidget(QLabel("mínimo"), 0, 1)
        rejilla.addWidget(QLabel("máximo"), 0, 2)
        self.limites = {}
        for fila, (eje, nombre) in enumerate((("x", "x"), ("y", "y"), ("y2", "y derecho")), start=1):
            rejilla.addWidget(QLabel(nombre + ":"), fila, 0)
            for col, lado in enumerate(("min", "max"), start=1):
                campo = QLineEdit()
                campo.setPlaceholderText("automático")
                campo.setToolTip("Vacío: automático. Con el eje partido, los límites de x no se aplican.")
                rejilla.addWidget(campo, fila, col)
                self.limites[f"{eje}_{lado}"] = campo
        capa.addLayout(rejilla)
        form = QFormLayout()
        self.marcas = _combo(MARCAS)
        self.marcas_espejo = QCheckBox("También arriba y a la derecha")
        self.marcas_menores = QCheckBox("Marcas secundarias")
        self.bordes = _combo(BORDES)
        self.rejilla = QCheckBox("Rejilla")
        self.rejilla_menor = QCheckBox("Rejilla secundaria")
        self.notacion = _combo(NOTACION)
        self.notacion.setToolTip("Científica: los números del eje con un factor común ×10ⁿ")
        fila = QHBoxLayout()
        fila.addWidget(self.marcas_espejo)
        fila.addWidget(self.marcas_menores)
        fila.addStretch(1)
        form.addRow("Marcas:", self.marcas)
        form.addRow("", fila)
        form.addRow("Bordes:", self.bordes)
        fila = QHBoxLayout()
        fila.addWidget(self.rejilla)
        fila.addWidget(self.rejilla_menor)
        fila.addStretch(1)
        form.addRow("Rejilla:", fila)
        form.addRow("Números:", self.notacion)
        capa.addLayout(form)
        nota = QLabel("Las escalas logarítmicas están en la barra de la gráfica (log x, log y) y en Representar "
                      "(log y dcho.).")
        nota.setWordWrap(True)
        nota.setObjectName("secundario")
        capa.addWidget(nota)
        capa.addStretch(1)
        return w

    def _pagina_leyenda(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.leyenda = QCheckBox("Mostrar la leyenda")
        self.loc_leyenda = _combo(LOC_LEYENDA)
        self.loc_leyenda.activated.connect(lambda _i: setattr(self, "_loc_tocada", True))
        self.loc_leyenda.setToolTip("«Fuera» deja la leyenda fuera de los ejes, sin tapar los datos")
        self.aviso_leyenda = QLabel()
        self.aviso_leyenda.setObjectName("secundario")
        self.aviso_leyenda.setWordWrap(True)
        self.leyenda_columnas = QSpinBox()
        self.leyenda_columnas.setRange(1, 8)
        self.leyenda_marco = QCheckBox("Con marco")
        self.tam_leyenda = _giro(0, 30, 0.5, automatico="Automático")
        self.titulo_leyenda = QLineEdit()
        self.titulo_leyenda.setPlaceholderText("sin título")
        form.addRow(self.leyenda)
        form.addRow("Posición:", self.loc_leyenda)
        form.addRow(self.aviso_leyenda)
        form.addRow("Columnas:", self.leyenda_columnas)
        form.addRow("Tamaño de letra:", self.tam_leyenda)
        form.addRow("Título:", self.titulo_leyenda)
        form.addRow(self.leyenda_marco)
        return w

    def _pagina_datos(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.tam_marcador = _giro(1, 20, 0.5)
        self.grosor_linea = _giro(0.2, 8, 0.2)
        self.grosor_ajuste = _giro(0.2, 8, 0.2)
        self.grosor_error = _giro(0, 5, 0.1)
        self.tam_tapa = _giro(0, 10, 0.5)
        self.tam_tapa.setSpecialValueText("Sin topes")
        self.color_datos = BotonColor("Color de los datos")
        self.color_ajuste = BotonColor("Color del ajuste")
        self.cuadro = QCheckBox("Cuadro con la ecuación y los parámetros (arrastrable)")
        form.addRow("Tamaño de los puntos:", self.tam_marcador)
        form.addRow("Grosor de las líneas:", self.grosor_linea)
        form.addRow("Grosor de las curvas ajustadas:", self.grosor_ajuste)
        form.addRow("Grosor de las barras de error:", self.grosor_error)
        form.addRow("Topes de las barras de error:", self.tam_tapa)
        form.addRow("Color de los datos:", self.color_datos)
        form.addRow("Color del ajuste:", self.color_ajuste)
        form.addRow(self.cuadro)
        nota = QLabel("Los tamaños van en puntos tipográficos. Los colores de las series de Representar se eligen "
                      "en su tabla.")
        nota.setWordWrap(True)
        nota.setObjectName("secundario")
        form.addRow(nota)
        return w

    def _pagina_marcas(self) -> QWidget:
        w = QWidget()
        capa = QVBoxLayout(w)
        self.lista_marcas = QListWidget()
        self.lista_marcas.itemDoubleClicked.connect(lambda _i: self._editar_marca())
        b_anadir = QPushButton("Añadir…")
        b_anadir.clicked.connect(self._anadir_marca)
        b_editar = QPushButton("Editar…")
        b_editar.clicked.connect(self._editar_marca)
        b_quitar = QPushButton("Quitar")
        b_quitar.clicked.connect(self._quitar_marca)
        fila = QHBoxLayout()
        for b in (b_anadir, b_editar, b_quitar):
            fila.addWidget(b)
        fila.addStretch(1)
        nota = QLabel("Señalan un punto importante, un tramo de x o un valor con una línea, con su texto, color, "
                      "forma y tamaño. En la gráfica: botón «Marcar» o clic derecho; doble clic en una marca para "
                      "editarla.")
        nota.setWordWrap(True)
        nota.setObjectName("secundario")
        capa.addWidget(self.lista_marcas, 1)
        capa.addLayout(fila)
        capa.addWidget(nota)
        self._marcas: list[dict] = []
        return w

    def _rellenar_marcas(self) -> None:
        self.lista_marcas.clear()
        for m in self._marcas:
            self.lista_marcas.addItem(describir_marca(m))

    def _anadir_marca(self) -> None:
        dlg = DialogoMarca(None, self, "Marca nueva", doble_eje=True)
        if dlg.exec() == QDialog.Accepted:
            self._marcas.append(dlg.marca())
            self._rellenar_marcas()

    def _editar_marca(self) -> None:
        i = self.lista_marcas.currentRow()
        if 0 <= i < len(self._marcas):
            dlg = DialogoMarca(self._marcas[i], self, "Editar marca", doble_eje=True)
            if dlg.exec() == QDialog.Accepted:
                self._marcas[i] = dlg.marca()
                self._rellenar_marcas()
                self.lista_marcas.setCurrentRow(i)

    def _quitar_marca(self) -> None:
        i = self.lista_marcas.currentRow()
        if 0 <= i < len(self._marcas):
            self._marcas.pop(i)
            self._rellenar_marcas()

    def _pagina_notas(self) -> QWidget:
        w = QWidget()
        capa = QVBoxLayout(w)
        self.notas = QTableWidget(0, 4)
        self.notas.setHorizontalHeaderLabels(["Texto", "Tamaño", "Flecha a x", "Flecha a y"])
        self.notas.verticalHeader().setVisible(False)
        self.notas.setSelectionBehavior(QAbstractItemView.SelectRows)
        cab = self.notas.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            cab.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        b_anadir = QPushButton("Añadir")
        b_anadir.clicked.connect(lambda: self._anadir_nota({"texto": "Texto", "x": 0.5, "y": 0.5}))
        b_quitar = QPushButton("Quitar")
        b_quitar.clicked.connect(lambda: self.notas.removeRow(max(self.notas.currentRow(), 0))
                                 if self.notas.rowCount() else None)
        fila = QHBoxLayout()
        fila.addWidget(b_anadir)
        fila.addWidget(b_quitar)
        fila.addStretch(1)
        nota = QLabel("Arrastra los textos en la gráfica para colocarlos. Con «Flecha a» (coordenadas de los datos) "
                      "el texto señala ese punto. Clic derecho en la gráfica → «Añadir una flecha que señale aquí».")
        nota.setWordWrap(True)
        nota.setObjectName("secundario")
        capa.addWidget(self.notas, 1)
        capa.addLayout(fila)
        capa.addWidget(nota)
        return w

    def _pagina_estilo(self) -> QWidget:
        w = QWidget()
        capa = QVBoxLayout(w)
        explicacion = QLabel("Una plantilla guarda el estilo (letra, marcas, rejilla, leyenda, tamaños y colores), "
                             "no los textos, los límites ni las posiciones.")
        explicacion.setWordWrap(True)
        explicacion.setObjectName("secundario")
        self.lista_plantillas = QListWidget()
        self.lista_plantillas.itemDoubleClicked.connect(lambda _i: self._aplicar_plantilla())
        b_aplicar = QPushButton("Aplicar")
        b_aplicar.clicked.connect(self._aplicar_plantilla)
        b_guardar = QPushButton("Guardar el estilo actual…")
        b_guardar.clicked.connect(self._guardar_plantilla)
        self.b_borrar = QPushButton("Borrar")
        self.b_borrar.clicked.connect(self._borrar_plantilla)
        self.lista_plantillas.currentItemChanged.connect(self._al_elegir_plantilla)
        fila = QHBoxLayout()
        for b in (b_aplicar, b_guardar, self.b_borrar):
            fila.addWidget(b)
        fila.addStretch(1)
        b_defecto = QPushButton("Usar el estilo actual en las gráficas nuevas")
        b_defecto.setToolTip("Se aplica al abrir el programa y en cada sesión nueva")
        b_defecto.clicked.connect(self._fijar_predeterminado)
        b_fabrica = QPushButton("Gráficas nuevas con el estilo de fábrica")
        b_fabrica.clicked.connect(lambda: (fijar_estilo_predeterminado(None, self._ajustes),
                                           self._actualizar_aviso_defecto()))
        self.aviso_defecto = QLabel()
        self.aviso_defecto.setObjectName("secundario")
        capa.addWidget(explicacion)
        capa.addWidget(self.lista_plantillas, 1)
        capa.addLayout(fila)
        capa.addWidget(b_defecto)
        capa.addWidget(b_fabrica)
        capa.addWidget(self.aviso_defecto)
        self._rellenar_plantillas()
        self._actualizar_aviso_defecto()
        return w

    # -- plantillas -------------------------------------------------------------
    def _rellenar_plantillas(self, elegir: str | None = None) -> None:
        self.lista_plantillas.clear()
        for nombre in PLANTILLAS:
            item = QListWidgetItem(nombre)
            item.setData(Qt.UserRole, ("fabrica", nombre))
            self.lista_plantillas.addItem(item)
        for nombre in sorted(plantillas_usuario(self._ajustes)):
            item = QListWidgetItem(f"{nombre}  (tuya)")
            item.setData(Qt.UserRole, ("usuario", nombre))
            self.lista_plantillas.addItem(item)
            if nombre == elegir:
                self.lista_plantillas.setCurrentItem(item)
        if self.lista_plantillas.currentItem() is None:
            self.lista_plantillas.setCurrentRow(0)

    def _al_elegir_plantilla(self, item, _anterior=None) -> None:
        self.b_borrar.setEnabled(item is not None and item.data(Qt.UserRole)[0] == "usuario")

    def _estilo_de(self, item) -> dict:
        tipo, nombre = item.data(Qt.UserRole)
        return PLANTILLAS[nombre] if tipo == "fabrica" else plantillas_usuario(self._ajustes).get(nombre, {})

    def aplicar_plantilla(self, nombre: str) -> None:
        """Pone en los controles el estilo de la plantilla ``nombre`` (de fábrica o tuya)."""
        estilo = PLANTILLAS.get(nombre)
        if estilo is None:
            estilo = plantillas_usuario(self._ajustes).get(nombre, {})
        o = self.opciones()
        o.aplicar_estilo(estilo)
        self._fijar_controles(o)

    def _aplicar_plantilla(self) -> None:
        item = self.lista_plantillas.currentItem()
        if item is not None:
            o = self.opciones()
            o.aplicar_estilo(self._estilo_de(item))
            self._fijar_controles(o)

    def _guardar_plantilla(self) -> None:
        nombre, ok = QInputDialog.getText(self, "Guardar plantilla", "Nombre de la plantilla:")
        nombre = nombre.strip()
        if not ok or not nombre:
            return
        if nombre in PLANTILLAS:
            QMessageBox.information(self, "Guardar plantilla", "Ese nombre es de una plantilla de fábrica: elige otro.")
            return
        guardar_plantilla(nombre, self.opciones().estilo(), self._ajustes)
        self._rellenar_plantillas(elegir=nombre)

    def _borrar_plantilla(self) -> None:
        item = self.lista_plantillas.currentItem()
        if item is not None and item.data(Qt.UserRole)[0] == "usuario":
            borrar_plantilla(item.data(Qt.UserRole)[1], self._ajustes)
            self._rellenar_plantillas()

    def _fijar_predeterminado(self) -> None:
        fijar_estilo_predeterminado(self.opciones().estilo(), self._ajustes)
        self._actualizar_aviso_defecto()

    def _actualizar_aviso_defecto(self) -> None:
        propio = bool(estilo_predeterminado(self._ajustes))
        self.aviso_defecto.setText("Las gráficas nuevas usan tu estilo predeterminado." if propio
                                   else "Las gráficas nuevas usan el estilo de fábrica.")

    # -- textos libres ------------------------------------------------------------
    def _anadir_nota(self, nota: dict) -> None:
        f = self.notas.rowCount()
        self.notas.insertRow(f)
        texto = QTableWidgetItem(str(nota.get("texto", "")))
        texto.setData(Qt.UserRole, (float(nota.get("x", 0.5)), float(nota.get("y", 0.5))))
        self.notas.setItem(f, 0, texto)
        tam = _giro(0, 40, 0.5, automatico="Auto")
        tam.setValue(float(nota.get("tam") or 0))
        self.notas.setCellWidget(f, 1, tam)
        flecha = nota.get("flecha") or [None, None]
        for col, v in ((2, flecha[0]), (3, flecha[1])):
            campo = QLineEdit(_texto_numero(v))
            campo.setPlaceholderText("sin flecha")
            self.notas.setCellWidget(f, col, campo)

    def _leer_notas(self) -> list[dict]:
        notas = []
        for f in range(self.notas.rowCount()):
            item = self.notas.item(f, 0)
            texto = item.text().strip() if item else ""
            if not texto:
                continue
            x, y = item.data(Qt.UserRole) or (0.5, 0.5)
            fx, fy = (_numero(self.notas.cellWidget(f, c).text()) for c in (2, 3))
            notas.append({"texto": texto, "x": x, "y": y, "tam": self.notas.cellWidget(f, 1).value(),
                          "flecha": [fx, fy] if fx is not None and fy is not None else None})
        return notas

    # -- leer y escribir los controles --------------------------------------------
    def _fijar_controles(self, o: OpcionesGrafica) -> None:
        self.titulo.setText(o.titulo)
        _fijar_combo(self.alin_titulo, o.alin_titulo)
        self.tam_titulo.setValue(o.tam_titulo)
        self.titulo_negrita.setChecked(o.titulo_negrita)
        self.ex.setText(o.etiqueta_x)
        self.ey.setText(o.etiqueta_y)
        self.ey2.setText(o.etiqueta_y2)
        self.tam_fuente.setValue(o.tam_fuente)
        movidos = [n for n, p in (("título", o.pos_titulo), ("leyenda", o.pos_leyenda),
                                  ("etiqueta x", o.pos_etiqueta_x), ("etiqueta y", o.pos_etiqueta_y),
                                  ("etiqueta y dcha.", o.pos_etiqueta_y2)) if p is not None]
        self.aviso_posiciones.setText(("Movidos a mano: " + ", ".join(movidos) + ".") if movidos else "")
        for clave, campo in self.limites.items():
            campo.setText(_texto_numero(getattr(o, clave)))
        _fijar_combo(self.marcas, o.marcas)
        self.marcas_espejo.setChecked(o.marcas_espejo)
        self.marcas_menores.setChecked(o.marcas_menores)
        _fijar_combo(self.bordes, o.bordes)
        self.rejilla.setChecked(o.rejilla)
        self.rejilla_menor.setChecked(o.rejilla_menor)
        _fijar_combo(self.notacion, o.notacion)
        self.leyenda.setChecked(o.leyenda)
        _fijar_combo(self.loc_leyenda, o.loc_leyenda)
        self.aviso_leyenda.setText("La has movido a mano: si eliges otra posición, vuelve a ella."
                                   if o.pos_leyenda is not None else "")
        self.leyenda_columnas.setValue(int(o.leyenda_columnas))
        self.leyenda_marco.setChecked(o.leyenda_marco)
        self.tam_leyenda.setValue(o.tam_leyenda)
        self.titulo_leyenda.setText(o.titulo_leyenda)
        self.tam_marcador.setValue(o.tam_marcador)
        self.grosor_linea.setValue(o.grosor_linea)
        self.grosor_ajuste.setValue(o.grosor_ajuste)
        self.grosor_error.setValue(o.grosor_error)
        self.tam_tapa.setValue(o.tam_tapa)
        self.color_datos.fijar(o.color_datos)
        self.color_ajuste.fijar(o.color_ajuste)
        self.cuadro.setChecked(o.cuadro_resultados)
        self.notas.setRowCount(0)
        for nota in o.anotaciones:
            self._anadir_nota(nota)
        self._marcas = [dict(m) for m in o.destacados]
        self._rellenar_marcas()

    def opciones(self) -> OpcionesGrafica:
        """Copia de las opciones originales con lo que hay en los controles."""
        o = OpcionesGrafica.desde_dict(self._original.a_dict())
        self.aplicar(o)
        return o

    def aplicar(self, o: OpcionesGrafica) -> None:
        o.titulo = self.titulo.text()
        o.alin_titulo = self.alin_titulo.currentData()
        o.tam_titulo = self.tam_titulo.value()
        o.titulo_negrita = self.titulo_negrita.isChecked()
        o.etiqueta_x = self.ex.text()
        o.etiqueta_y = self.ey.text()
        o.etiqueta_y2 = self.ey2.text()
        o.tam_fuente = self.tam_fuente.value()
        for clave, campo in self.limites.items():
            setattr(o, clave, _numero(campo.text()))
        o.marcas = self.marcas.currentData()
        o.marcas_espejo = self.marcas_espejo.isChecked()
        o.marcas_menores = self.marcas_menores.isChecked()
        o.bordes = self.bordes.currentData()
        o.rejilla = self.rejilla.isChecked()
        o.rejilla_menor = self.rejilla_menor.isChecked()
        o.notacion = self.notacion.currentData()
        o.leyenda = self.leyenda.isChecked()
        o.loc_leyenda = self.loc_leyenda.currentData()
        o.leyenda_columnas = self.leyenda_columnas.value()
        o.leyenda_marco = self.leyenda_marco.isChecked()
        o.tam_leyenda = self.tam_leyenda.value()
        o.titulo_leyenda = self.titulo_leyenda.text()
        o.tam_marcador = self.tam_marcador.value()
        o.grosor_linea = self.grosor_linea.value()
        o.grosor_ajuste = self.grosor_ajuste.value()
        o.grosor_error = self.grosor_error.value()
        o.tam_tapa = self.tam_tapa.value()
        o.color_datos = self.color_datos.color
        o.color_ajuste = self.color_ajuste.color
        o.cuadro_resultados = self.cuadro.isChecked()
        o.anotaciones = self._leer_notas()
        o.destacados = [dict(m) for m in self._marcas]
        if self._loc_tocada:  # elegir una posición deshace la que se arrastró
            o.pos_leyenda = None
        if self._alin_tocada:
            o.pos_titulo = None
        if self._restablecer_posiciones:
            o.restablecer_posiciones()

    def _marcar_restablecer_posiciones(self) -> None:
        self._restablecer_posiciones = True
        self.aviso_posiciones.setText("Al aceptar, todo vuelve a su sitio.")

    def _aplicar_ya(self) -> None:
        if self._al_aplicar is not None:
            self._al_aplicar(self)
            self._original = self.opciones()
            self._loc_tocada = self._alin_tocada = self._restablecer_posiciones = False
            self._fijar_controles(self._original)

    def _restablecer(self) -> None:
        self._restablecer_posiciones = True
        self._loc_tocada = self._alin_tocada = True
        self._fijar_controles(OpcionesGrafica())
