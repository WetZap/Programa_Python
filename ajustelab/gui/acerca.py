"""Diálogo «Acerca de» y su sorpresa: una imagen que flota sobre la ventana.

La imagen se busca en ``ajustelab/gui/recursos/sorpresa.{png,jpg,jpeg,webp,gif}``
(los GIF se animan). Si no existe, se muestra un marcador de posición.

La imagen flota *dentro* de la ventana principal (no como ventana aparte): así
funciona igual en Windows, macOS, X11 y Wayland, donde una aplicación no puede
colocar sus propias ventanas en la pantalla.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QMovie, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QDialog, QGraphicsDropShadowEffect, QGraphicsPixmapItem, QGraphicsScene, QHBoxLayout,
                               QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget)

from .. import __version__

RECURSOS = Path(__file__).resolve().parent / "recursos"
EXTENSIONES = ("png", "jpg", "jpeg", "webp", "gif")
URL_REPO = "https://github.com/WetZap/Programa_Python"


def buscar_imagen() -> Path | None:
    for ext in EXTENSIONES:
        ruta = RECURSOS / f"sorpresa.{ext}"
        if ruta.is_file():
            return ruta
    return None


def _marcador(lado: int = 260) -> QPixmap:
    """Imagen provisional mientras no exista ``recursos/sorpresa.*``."""
    pm = QPixmap(lado, lado)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, lado, lado)
    grad.setColorAt(0, QColor("#3987e5"))
    grad.setColorAt(1, QColor("#9085e9"))
    ruta = QPainterPath()
    ruta.addRoundedRect(QRectF(4, 4, lado - 8, lado - 8), 28, 28)
    p.fillPath(ruta, grad)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPointSize(54)
    p.setFont(f)
    p.drawText(QRectF(0, 20, lado, lado * 0.55), Qt.AlignCenter, "★")
    f.setPointSize(13)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(10, lado * 0.58, lado - 20, lado * 0.35), Qt.AlignCenter | Qt.TextWordWrap,
               "Aquí irá la sorpresa\n(imagen pendiente)")
    p.end()
    return pm


def _redondear(pm: QPixmap, radio: float = 18) -> QPixmap:
    """Esquinas redondeadas para imágenes opacas (fotos)."""
    img = pm.toImage()
    esquinas = [(0, 0), (img.width() - 1, 0), (0, img.height() - 1), (img.width() - 1, img.height() - 1)]
    if img.hasAlphaChannel() and any(img.pixelColor(x, y).alpha() < 250 for x, y in esquinas):
        return pm  # ya tiene forma propia (PNG con transparencia): se respeta
    salida = QPixmap(pm.size())
    salida.setDevicePixelRatio(pm.devicePixelRatio())
    salida.fill(Qt.transparent)
    p = QPainter(salida)
    p.setRenderHint(QPainter.Antialiasing)
    ruta = QPainterPath()
    ruta.addRoundedRect(QRectF(0, 0, pm.width(), pm.height()), radio, radio)
    p.setClipPath(ruta)
    p.drawPixmap(0, 0, pm)
    p.end()
    return salida


def _con_sombra(pm: QPixmap, margen: int, radio: int = 28) -> QImage:
    """Imagen + sombra difuminada, renderizada una sola vez (sin efectos anidados)."""
    escena = QGraphicsScene()
    item = QGraphicsPixmapItem(pm)
    sombra = QGraphicsDropShadowEffect()
    sombra.setBlurRadius(radio)
    sombra.setOffset(0, 8)
    sombra.setColor(QColor(0, 0, 0, 110))
    item.setGraphicsEffect(sombra)
    escena.addItem(item)
    img = QImage(pm.width() + 2 * margen, pm.height() + 2 * margen, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    escena.render(p, QRectF(0, 0, img.width(), img.height()),
                  QRectF(-margen, -margen, img.width(), img.height()))
    p.end()
    return img


class ImagenFlotante(QWidget):
    """Imagen que aparece con un fundido, flota suavemente, se puede arrastrar y
    se cierra con un clic, doble clic o Esc."""

    MARGEN = 30

    def __init__(self, anfitrion: QWidget, ruta: Path | None = None):
        super().__init__(anfitrion)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Arrástrala · clic o Esc para cerrar")
        self.ruta = ruta if ruta is not None else buscar_imagen()
        maximo = QSize(max(160, int(anfitrion.width() * 0.4)), max(160, int(anfitrion.height() * 0.5)))

        self._movie: QMovie | None = None
        self._fondo: QImage | None = None  # imagen + sombra ya compuesta (estáticas)
        if self.ruta is not None and self.ruta.suffix.lower() == ".gif":
            self._movie = QMovie(str(self.ruta))
            self._movie.jumpToFrame(0)
            tam = self._movie.currentPixmap().size().scaled(maximo, Qt.KeepAspectRatio)
            self._movie.setScaledSize(tam)
            self._movie.frameChanged.connect(lambda _: self.update())
            self._movie.start()
        else:
            pm = QPixmap(str(self.ruta)) if self.ruta is not None else QPixmap()
            if pm.isNull():
                pm = _marcador()
            if pm.width() > maximo.width() or pm.height() > maximo.height():
                pm = pm.scaled(maximo, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm = _redondear(pm)
            tam = pm.size()
            self._fondo = _con_sombra(pm, self.MARGEN)
        self.resize(tam.width() + 2 * self.MARGEN, tam.height() + 2 * self.MARGEN)

        # Posición base centrada; la animación la hace flotar alrededor
        self._base = QPoint((anfitrion.width() - self.width()) // 2, (anfitrion.height() - self.height()) // 2)
        self._arrastre: QPoint | None = None
        self._movido = False
        self._alfa = 0.0
        self.move(self._base)

        self._fundido = QVariantAnimation(self)
        self._fundido.setDuration(350)
        self._fundido.setEasingCurve(QEasingCurve.OutCubic)
        self._fundido.valueChanged.connect(self._fijar_alfa)

        self._flotar = QVariantAnimation(self)
        self._flotar.setStartValue(0.0)
        self._flotar.setEndValue(2 * math.pi)
        self._flotar.setDuration(3200)
        self._flotar.setLoopCount(-1)
        self._flotar.valueChanged.connect(self._al_flotar)

    def mostrar(self) -> "ImagenFlotante":
        self.show()
        self.raise_()
        self.setFocus()
        self._fundido.setStartValue(0.0)
        self._fundido.setEndValue(1.0)
        self._fundido.start()
        self._flotar.start()
        return self

    def _fijar_alfa(self, valor) -> None:
        self._alfa = float(valor)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setOpacity(self._alfa)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._fondo is not None:
            p.drawImage(0, 0, self._fondo)
        elif self._movie is not None:
            p.drawPixmap(self.MARGEN, self.MARGEN, self._movie.currentPixmap())
        p.end()

    def _al_flotar(self, t) -> None:
        if self._arrastre is None:
            self.move(self._base + QPoint(round(4 * math.sin(t / 2)), round(9 * math.sin(t))))

    def cerrar(self) -> None:
        self._flotar.stop()
        self._fundido.stop()
        self._fundido.setDuration(250)
        self._fundido.setStartValue(self._alfa)
        self._fundido.setEndValue(0.0)
        self._fundido.finished.connect(self.close)
        self._fundido.start()

    # -- ratón y teclado ----------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._arrastre = e.position().toPoint()
            self._movido = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._arrastre is not None:
            nuevo = self.mapToParent(e.position().toPoint() - self._arrastre)
            if (nuevo - self.pos()).manhattanLength() > 2:
                self._movido = True
            self._base = nuevo
            self.move(nuevo)

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.OpenHandCursor)
        self._arrastre = None
        if not self._movido:
            self.cerrar()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Space, Qt.Key_Return):
            self.cerrar()
        else:
            super().keyPressEvent(e)


class DialogoAcercaDe(QDialog):
    """Acerca de ajustelab. Esconde un botón casi invisible (abajo a la izquierda)."""

    def __init__(self, ventana, estilo: str, tema: str):
        super().__init__(ventana)
        self.setWindowTitle("Acerca de ajustelab")
        self.ventana = ventana
        titulo = QLabel(f"<span style='font-size:20px; font-weight:600'>ajustelab</span>"
                        f"&nbsp;&nbsp;<span>{__version__}</span>")
        texto = QLabel(
            "Ajuste de datos experimentales con base estadística: incertidumbres en x e y, χ² y p-valor, "
            "selección automática de modelo, interpolación e intersecciones.<br><br>"
            "Jorge del Río López (WetZap) · Grado en Física, Universidad de Granada<br>"
            f"Licencia MIT · <a href='{URL_REPO}'>{URL_REPO}</a><br><br>"
            f"<span style='color:gray'>Estilo: {estilo} · Tema: {tema}</span>")
        texto.setWordWrap(True)
        texto.setOpenExternalLinks(True)
        texto.setTextInteractionFlags(Qt.TextBrowserInteraction)
        cerrar = QPushButton("Cerrar")
        cerrar.setDefault(True)
        cerrar.clicked.connect(self.accept)

        self.sorpresa = QToolButton()
        self.sorpresa.setObjectName("sorpresa")
        self.sorpresa.setText("π")
        self.sorpresa.setCursor(Qt.PointingHandCursor)
        self.sorpresa.setAccessibleName("Sorpresa")
        self.sorpresa.clicked.connect(self._sorpresa)

        abajo = QHBoxLayout()
        abajo.addWidget(self.sorpresa, 0, Qt.AlignBottom)
        abajo.addStretch(1)
        abajo.addWidget(cerrar)
        capa = QVBoxLayout(self)
        capa.addWidget(titulo)
        capa.addWidget(texto)
        capa.addLayout(abajo)
        self.setMinimumWidth(460)

    def _sorpresa(self) -> None:
        self.accept()
        self.ventana.mostrar_sorpresa()
