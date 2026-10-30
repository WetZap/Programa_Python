"""Guardar y abrir el trabajo completo (sesión ``.ajustelab``, JSON legible).

Se guarda: la tabla (con nombres de columna), la asignación x/y/σ, los puntos
excluidos, el rango de ajuste, la configuración de cada pestaña (modelo,
valores iniciales, fijos, límites...), las opciones de la gráfica y la pestaña
activa. Los resultados no se guardan: se recalculan al abrir, así que la sesión
siempre es coherente con la versión de ajustelab que la abre.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .. import __version__

FORMATO = "ajustelab-sesion"
VERSION = 1
EXTENSION = ".ajustelab"


class ErrorSesion(ValueError):
    """Fichero de sesión no válido."""


def _limpio(v):
    return None if isinstance(v, float) and not math.isfinite(v) else v


def a_dict(ventana) -> dict:
    m = ventana.panel_datos.modelo
    df = m.a_dataframe()
    return {
        "formato": FORMATO,
        "version": VERSION,
        "ajustelab": __version__,
        "origen": str(ventana._ruta_datos) if getattr(ventana, "_ruta_datos", None) else None,
        "tabla": {"columnas": list(df.columns),
                  "valores": [[_limpio(float(v)) for v in fila] for fila in df.to_numpy(dtype=float)]},
        "asignacion": ventana.panel_datos.asignacion(),
        "excluidas": sorted(int(f) for f in m.excluidas),
        "rango_x": list(m.rango_x) if m.rango_x is not None else None,
        "grafica": ventana.grafica.opciones.a_dict(),
        "pestana": ventana.pestanas.currentIndex(),
        "paneles": {p.__class__.__name__: p.estado() for p in ventana.paneles},
    }


def guardar(ventana, ruta: str | Path) -> Path:
    ruta = Path(ruta)
    if ruta.suffix != EXTENSION:
        ruta = ruta.with_suffix(EXTENSION)
    ruta.write_text(json.dumps(a_dict(ventana), ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def leer(ruta: str | Path) -> dict:
    try:
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ErrorSesion(f"No se puede leer la sesión: {e}") from e
    if d.get("formato") != FORMATO:
        raise ErrorSesion("El fichero no es una sesión de ajustelab.")
    if d.get("version", 0) > VERSION:
        raise ErrorSesion("La sesión es de una versión más reciente de ajustelab: actualiza el programa.")
    return d


def restaurar(ventana, d: dict) -> None:
    from .grafica import OpcionesGrafica

    t = d["tabla"]
    valores = np.array([[np.nan if v is None else v for v in fila] for fila in t["valores"]], dtype=float)
    df = pd.DataFrame(valores.reshape(len(t["valores"]), len(t["columnas"])), columns=t["columnas"])
    ventana.cargar_tabla(df, "Sesión restaurada" + (f" (datos de {Path(d['origen']).name})" if d.get("origen") else ""))
    pd_ = ventana.panel_datos
    pd_.fijar_asignacion(d.get("asignacion", {}))
    m = pd_.modelo
    m.excluidas = set(d.get("excluidas", []))
    m.rango_x = tuple(d["rango_x"]) if d.get("rango_x") else None
    m.layoutChanged.emit()
    m.rangoCambiado.emit()
    if m.pila is not None:
        m.pila.clear()
    ventana.grafica.fijar_opciones(OpcionesGrafica.desde_dict(d.get("grafica", {})))
    obtenidos = ventana.obtener_datos(silencioso=True)
    if obtenidos is not None:  # la asignación de columnas puede cambiar el número de puntos
        ventana.p_inter.actualizar_rango(obtenidos[0].n_total)
    estados = d.get("paneles", {})
    for p in ventana.paneles:
        if p.__class__.__name__ in estados:
            p.restaurar(estados[p.__class__.__name__])
    ventana.pestanas.setCurrentIndex(int(d.get("pestana", 0)))
