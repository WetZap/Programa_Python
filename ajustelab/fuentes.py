"""Tipografía de ajustelab: Inter (https://rsms.me/inter, licencia SIL OFL 1.1).

Va incluida en el paquete (``recursos/fuentes``, recortada a los alfabetos latino
y griego, símbolos matemáticos y flechas), así que se ve igual en Windows,
macOS y cualquier distribución, sin instalar nada. Se usa en:

* las gráficas (matplotlib), también en las fórmulas: el texto de las fórmulas
  en Inter y los símbolos que Inter no tiene, en STIX sans;
* la interfaz (Qt), con cifras tabulares en las tablas para que los números se
  alineen.

Si los ficheros faltasen, todo sigue funcionando con DejaVu Sans.
"""
from __future__ import annotations

from pathlib import Path

CARPETA = Path(__file__).resolve().parent / "recursos" / "fuentes"
FAMILIA = "Inter"
_en_matplotlib = False


def ficheros() -> list[Path]:
    return sorted(CARPETA.glob("Inter-*.ttf"))


def parametros_matplotlib() -> dict:
    """rcParams de matplotlib para escribir en Inter (texto y fórmulas)."""
    if not ficheros():
        return {}
    import matplotlib

    resto = [f for f in matplotlib.rcParamsDefault["font.sans-serif"] if f != FAMILIA]
    return {
        "font.family": "sans-serif",
        "font.sans-serif": [FAMILIA, *resto],
        "mathtext.fontset": "custom",
        "mathtext.rm": FAMILIA,
        "mathtext.sf": FAMILIA,
        "mathtext.it": f"{FAMILIA}:italic",
        "mathtext.bf": f"{FAMILIA}:bold",
        "mathtext.cal": f"{FAMILIA}:italic",  # si no, matplotlib busca una «cursive» que no suele haber
        "mathtext.fallback": "stixsans",
    }


def registrar_matplotlib(aplicar: bool = True) -> bool:
    """Añade Inter al gestor de fuentes de matplotlib (una vez) y, con ``aplicar``,
    la deja como fuente por defecto. Devuelve si Inter está disponible."""
    global _en_matplotlib
    import matplotlib
    from matplotlib import font_manager

    if not _en_matplotlib:
        for f in ficheros():
            font_manager.fontManager.addfont(str(f))
        _en_matplotlib = True
    rc = parametros_matplotlib()
    if aplicar and rc:
        matplotlib.rcParams.update(rc)
    return bool(rc)


def registrar_qt(app) -> str | None:
    """Carga Inter en Qt y la pone como fuente de la aplicación (con el tamaño que
    ya tuviera). Devuelve el nombre de la familia, o None si no se pudo."""
    from PySide6.QtGui import QFont, QFontDatabase

    familia = None
    for f in ficheros():
        ident = QFontDatabase.addApplicationFont(str(f))
        if ident >= 0 and familia is None:
            familias = QFontDatabase.applicationFontFamilies(ident)
            familia = familias[0] if familias else None
    if familia is None:
        return None
    fuente = QFont(app.font())
    fuente.setFamilies([familia, *[f for f in app.font().families() if f != familia]])
    app.setFont(fuente)
    return familia


def con_cifras_tabulares(fuente):
    """Misma fuente con cifras de anchura fija (OpenType «tnum»): los números de
    una columna quedan alineados. Sin efecto si Qt no lo admite (< 6.7)."""
    from PySide6.QtGui import QFont

    if hasattr(QFont, "Tag") and hasattr(fuente, "setFeature"):
        try:
            fuente.setFeature(QFont.Tag("tnum"), 1)
        except (TypeError, ValueError):
            pass
    return fuente
