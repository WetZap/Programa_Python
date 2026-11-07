"""Utilidades pequeñas compartidas por la interfaz."""
from __future__ import annotations


def numero(texto: str) -> float | None:
    """Número escrito por el usuario (admite coma decimal). Vacío o no numérico: None."""
    t = (texto or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def numero_estricto(texto: str) -> float | None:
    """Como :func:`numero`, pero un texto que no es un número lanza ``ValueError``."""
    t = (texto or "").strip().replace(",", ".")
    return float(t) if t else None
