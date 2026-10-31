"""Hoja de estilo (QSS) de los elementos propios de la interfaz.

Solo se aplica a widgets marcados con ``objectName`` o propiedades dinámicas
(botón principal, tarjetas, chips de estado, avisos flotantes...). El resto de
controles conserva el estilo nativo de cada sistema. Los colores salen de la
paleta activa (``GestorTema.colores()``) y la hoja se regenera al cambiar de
modo, salvo los de estado, que son fijos y siempre van con icono y texto.
"""
from __future__ import annotations

# Paleta de estado (fija): bueno, aviso, grave, crítico
ESTADO = {"bueno": "#0ca30c", "aviso": "#fab219", "grave": "#ec835a", "malo": "#d03b3b", "neutro": "#8a8a85"}
ACENTO = {False: "#2a78d6", True: "#3987e5"}


def _rgba(hexa: str, alfa: float) -> str:
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alfa})"


def _imagen_marca() -> str | None:
    """Marca de verificación blanca (1× y 2×) en la caché del usuario, para las
    casillas del modo oscuro. Devuelve la ruta con barras «/» (válida en QSS)."""
    from PySide6.QtCore import QPointF, QStandardPaths, Qt
    from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
    from pathlib import Path

    carpeta = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation) or ".") / "estilo"
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        for nombre, lado in (("marca.png", 14), ("marca@2x.png", 28)):
            ruta = carpeta / nombre
            if ruta.exists():
                continue
            pm = QPixmap(lado, lado)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor("white"), lado * 0.14, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            r = QPainterPath(QPointF(lado * 0.22, lado * 0.52))
            r.lineTo(lado * 0.42, lado * 0.72)
            r.lineTo(lado * 0.78, lado * 0.30)
            p.drawPath(r)
            p.end()
            pm.save(str(ruta))
        return (carpeta / "marca.png").as_posix()
    except OSError:
        return None


def hoja_estilo(c: dict[str, str], oscuro: bool, fusion: bool = True) -> str:
    """``c``: colores de :meth:`GestorTema.colores` (ejes, texto, secundario, rejilla).
    ``fusion``: el estilo activo es Fusion (solo entonces se retocan las casillas)."""
    acento = ACENTO[oscuro]
    base, texto, sec, borde = c["ejes"], c["texto"], c["secundario"], c["rejilla"]
    reglas = [
        # Botón principal de cada pestaña
        f'QPushButton[primario="true"] {{ background-color: {acento}; color: white; border: 1px solid {acento};'
        f' border-radius: 6px; padding: 5px 16px; font-weight: 600; }}',
        f'QPushButton[primario="true"]:hover {{ background-color: {_rgba(acento, 0.85)}; }}',
        'QPushButton[primario="true"]:pressed { padding-top: 6px; padding-bottom: 4px; }',
        f'QPushButton[primario="true"]:disabled {{ background-color: {borde}; border-color: {borde}; }}',
        # Tarjetas y cifras destacadas
        f'QFrame#tarjeta {{ background-color: {base}; border: 1px solid {borde}; border-radius: 8px; }}',
        f'QLabel#tile_titulo {{ color: {sec}; font-size: 11px; }}',
        'QLabel#tile_valor { font-size: 18px; font-weight: 600; }',
        'QLabel#seccion { font-weight: 600; }',
        f'QLabel#secundario {{ color: {sec}; }}',
        # Aviso flotante (toast)
        f'QFrame#toast {{ background-color: {base}; border: 1px solid {borde}; border-radius: 8px; }}',
        f'QFrame#toast QLabel {{ color: {texto}; }}',
        # Pantalla de bienvenida
        f'QFrame#bienvenida {{ background-color: {base}; border: 2px dashed {borde}; border-radius: 14px; }}',
        'QLabel#bienvenida_titulo { font-size: 22px; font-weight: 600; }',
        f'QLabel#bienvenida_texto {{ color: {sec}; }}',
        f'QPushButton#reciente {{ text-align: left; border: none; padding: 2px 4px; color: {acento}; }}',
        'QPushButton#reciente:hover { text-decoration: underline; }',
        # Easter egg: botón casi invisible
        f'QToolButton#sorpresa {{ border: none; color: {borde}; font-size: 12px; padding: 0px; }}',
        f'QToolButton#sorpresa:hover {{ color: {acento}; }}',
    ]
    if oscuro and fusion:
        # Fusion dibuja el borde de las casillas más oscuro que el fondo: en modo
        # oscuro casi no se ven. Se dibujan con borde claro y relleno de acento.
        marca = _imagen_marca()
        ind = "QCheckBox::indicator, QAbstractItemView::indicator, QGroupBox::indicator"
        reglas += [
            f"{ind} {{ width: 14px; height: 14px; border: 1px solid {sec}; border-radius: 3px;"
            f" background-color: {base}; }}",
            f"QCheckBox::indicator:hover, QAbstractItemView::indicator:hover {{ border-color: {acento}; }}",
            "QCheckBox::indicator:checked, QAbstractItemView::indicator:checked, QGroupBox::indicator:checked"
            f" {{ background-color: {acento}; border-color: {acento};" + (f" image: url({marca});" if marca else "")
            + " }",
            f"QCheckBox::indicator:disabled {{ border-color: {borde}; }}",
        ]
    for nombre, color in ESTADO.items():
        reglas.append(f'QLabel#chip[estado="{nombre}"] {{ background-color: {_rgba(color, 0.16)};'
                      f' border: 1px solid {color}; border-radius: 10px; padding: 2px 10px; }}')
    return "\n".join(reglas)
