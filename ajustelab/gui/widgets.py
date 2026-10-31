"""Componentes visuales reutilizables: aviso flotante (toast), chip de estado,
cifra destacada (tile), ecuación renderizada y pantalla de bienvenida."""
from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPalette, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .iconos import icono

SIMBOLO = {"bueno": "✓", "aviso": "⚠", "grave": "⚠", "malo": "✗", "neutro": "•"}


class Chip(QLabel):
    """Etiqueta de estado: símbolo + texto sobre un fondo tenue del color de estado
    (el color nunca va solo: siempre lleva símbolo y texto)."""

    def __init__(self, texto: str = "", estado: str = "neutro", parent=None):
        super().__init__(parent)
        self.setObjectName("chip")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.fijar(texto, estado)

    def fijar(self, texto: str, estado: str = "neutro") -> None:
        self.setText(f"{SIMBOLO.get(estado, '•')}  {texto}" if texto else "")
        self.setProperty("estado", estado)
        self.setVisible(bool(texto))
        self.style().unpolish(self)
        self.style().polish(self)


class Tile(QFrame):
    """Cifra destacada con su título (χ²/ν, p, R²...)."""

    def __init__(self, titulo: str, ayuda: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self.titulo = QLabel(titulo)
        self.titulo.setObjectName("tile_titulo")
        self.valor = QLabel("—")
        self.valor.setObjectName("tile_valor")
        capa = QVBoxLayout(self)
        capa.setContentsMargins(10, 6, 10, 6)
        capa.setSpacing(0)
        capa.addWidget(self.titulo)
        capa.addWidget(self.valor)
        if ayuda:
            self.setToolTip(ayuda)

    def fijar(self, valor: str) -> None:
        self.valor.setText(valor)


class Ecuacion(QLabel):
    """Ecuación LaTeX renderizada con el motor de fórmulas de matplotlib, en el
    color del texto de la paleta y a la resolución de la pantalla."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._latex = ""
        self.setMinimumHeight(30)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def fijar(self, latex: str, alternativo: str = "") -> None:
        self._latex = latex
        self._alternativo = alternativo
        self.renderizar()

    def renderizar(self) -> None:
        if not self._latex:
            self.clear()
            return
        try:
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            from matplotlib.figure import Figure

            color = self.palette().color(QPalette.WindowText).name()
            dpr = self.devicePixelRatioF() or 1.0
            fig = Figure(figsize=(0.01, 0.01))
            FigureCanvasAgg(fig)
            fig.text(0, 0, f"${self._latex}$", fontsize=12, color=color)
            buf = io.BytesIO()
            # Fondo transparente: la fórmula se integra en cualquier tema
            fig.savefig(buf, dpi=100 * dpr, format="png", transparent=True, bbox_inches="tight", pad_inches=0.03)
            pm = QPixmap()
            pm.loadFromData(buf.getvalue(), "PNG")
            pm.setDevicePixelRatio(dpr)
            self.setPixmap(pm)
            self.setToolTip(self._alternativo)
        except Exception:  # fórmula no representable: texto
            self.setText(self._alternativo)

    def changeEvent(self, evento):
        if evento.type() == QEvent.PaletteChange and self._latex:
            self.renderizar()
        super().changeEvent(evento)


class Notificador(QObject):
    """Avisos breves que aparecen y se desvanecen en la esquina inferior derecha
    de un widget (no interrumpen como un cuadro de diálogo)."""

    def __init__(self, anfitrion: QWidget):
        super().__init__(anfitrion)
        self.anfitrion = anfitrion
        self.marco = QFrame(anfitrion)
        self.marco.setObjectName("toast")
        self.marco.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.etiqueta = QLabel(self.marco)
        self.etiqueta.setWordWrap(True)
        self.etiqueta.setMaximumWidth(420)
        capa = QHBoxLayout(self.marco)
        capa.setContentsMargins(14, 9, 14, 9)
        capa.addWidget(self.etiqueta)
        self.efecto = QGraphicsOpacityEffect(self.marco)
        self.marco.setGraphicsEffect(self.efecto)
        self.anim = QPropertyAnimation(self.efecto, b"opacity", self)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.reloj = QTimer(self)
        self.reloj.setSingleShot(True)
        self.reloj.timeout.connect(self._ocultar)
        self.anim.finished.connect(self._al_terminar_anim)
        self.marco.hide()
        anfitrion.installEventFilter(self)

    def mostrar(self, texto: str, estado: str = "neutro", ms: int = 3500) -> None:
        self.etiqueta.setText(f"{SIMBOLO.get(estado, '')}  {texto}".strip())
        self.marco.adjustSize()
        self._colocar()
        self.marco.show()
        self.marco.raise_()
        self.anim.stop()
        self.anim.setDuration(180)
        self.anim.setStartValue(self.efecto.opacity() if self.marco.isVisible() else 0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.reloj.start(ms)

    def _ocultar(self) -> None:
        self.anim.stop()
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _al_terminar_anim(self) -> None:
        if self.efecto.opacity() <= 0.01:
            self.marco.hide()

    def _colocar(self) -> None:
        m = 16
        r = self.anfitrion.rect()
        self.marco.move(r.right() - self.marco.width() - m, r.bottom() - self.marco.height() - m)

    def eventFilter(self, obj, evento):
        if obj is self.anfitrion and evento.type() == QEvent.Resize and self.marco.isVisible():
            self._colocar()
        return False


class Bienvenida(QWidget):
    """Pantalla inicial cuando no hay datos: abrir, pegar, ejemplos y recientes."""

    abrir = Signal()
    pegar = Signal()
    vacia = Signal()
    ejemplo = Signal(str)
    reciente = Signal(str)

    def __init__(self, ejemplos: dict[str, str], parent=None):
        super().__init__(parent)
        self.setAcceptDrops(False)  # lo gestiona la ventana
        tarjeta = QFrame()
        tarjeta.setObjectName("bienvenida")
        tarjeta.setMaximumWidth(560)
        titulo = QLabel("ajustelab")
        titulo.setObjectName("bienvenida_titulo")
        texto = QLabel("Abre un fichero de datos o arrástralo a la ventana.\n"
                       "csv, dat, txt, xlsx, ods, json, npy, mat…")
        texto.setObjectName("bienvenida_texto")
        texto.setAlignment(Qt.AlignCenter)
        titulo.setAlignment(Qt.AlignCenter)

        def boton(nombre, etiqueta, senal, principal=False):
            b = QPushButton(icono(nombre), etiqueta)
            b.setIconSize(QSize(20, 20))
            b.setMinimumHeight(34)
            if principal:
                b.setProperty("primario", True)
            if senal is not None:
                b.clicked.connect(senal)
            return b

        b_abrir = boton("abrir", "Abrir fichero…", self.abrir, principal=True)
        b_pegar = boton("pegar", "Pegar del portapapeles", self.pegar)
        b_vacia = boton("nuevo", "Escribir los datos", self.vacia)
        b_ejemplo = boton("ejemplo", "Datos de ejemplo", None)
        menu = QMenu(b_ejemplo)
        for clave, nombre in ejemplos.items():
            menu.addAction(nombre, lambda c=clave: self.ejemplo.emit(c))
        b_ejemplo.setMenu(menu)

        rejilla = QHBoxLayout()
        for b in (b_abrir, b_pegar):
            rejilla.addWidget(b)
        rejilla2 = QHBoxLayout()
        for b in (b_vacia, b_ejemplo):
            rejilla2.addWidget(b)

        self.titulo_recientes = QLabel("Recientes")
        self.titulo_recientes.setObjectName("seccion")
        self.lista_recientes = QVBoxLayout()
        self.lista_recientes.setSpacing(0)

        capa_t = QVBoxLayout(tarjeta)
        capa_t.setContentsMargins(36, 30, 36, 30)
        capa_t.setSpacing(12)
        capa_t.addWidget(titulo)
        capa_t.addWidget(texto)
        capa_t.addSpacing(6)
        capa_t.addLayout(rejilla)
        capa_t.addLayout(rejilla2)
        capa_t.addSpacing(6)
        capa_t.addWidget(self.titulo_recientes)
        capa_t.addLayout(self.lista_recientes)

        capa = QVBoxLayout(self)
        capa.addStretch(1)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(tarjeta, 3)
        fila.addStretch(1)
        capa.addLayout(fila)
        capa.addStretch(1)

    def fijar_recientes(self, rutas: list[str]) -> None:
        while self.lista_recientes.count():
            w = self.lista_recientes.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        rutas = [r for r in rutas if Path(r).exists()][:6]
        self.titulo_recientes.setVisible(bool(rutas))
        for r in rutas:
            b = QPushButton(Path(r).name)
            b.setObjectName("reciente")
            b.setToolTip(r)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, ruta=r: self.reciente.emit(ruta))
            self.lista_recientes.addWidget(b)


def copiar_al_portapapeles(texto: str) -> None:
    QGuiApplication.clipboard().setText(texto)
