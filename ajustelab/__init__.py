"""ajustelab — ajuste de datos experimentales con base estadística.

Uso rápido::

    from ajustelab import cargar, ajustar
    datos = cargar("medidas.csv")          # detecta formato y columnas x, y, dx, dy
    res = ajustar(datos, "lineal")          # o una expresión: "A*exp(-x/tau) + C"
    print(res.resumen())
    print(seleccionar(datos))             # prueba todo el catálogo y recomienda
    f = interpolar(datos, "pchip")          # interpolación / spline de suavizado
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__version__ = "1.6.0"

# Carga perezosa (PEP 562): «import ajustelab» no arrastra SciPy ni SymPy hasta
# que se usa algo, así que «ajustelab --version» o «--diagnostico» responden al
# momento. «from ajustelab import ajustar» funciona exactamente igual que antes.
_ORIGEN = {
    "ajuste": ("ErrorAjuste", "ResultadoAjuste", "ajustar"),
    "datos": ("Datos", "ErrorDatos", "a_datos", "cargar", "hojas", "leer_tabla", "leer_texto"),
    "estadistica": ("banda", "bondad", "formatear", "redondear"),
    "modelos": ("CATALOGO", "ErrorModelo", "Modelo", "desde_expresion", "obtener", "polinomio"),
    "seleccion": ("CANDIDATOS_AUTO", "Seleccion", "seleccionar"),
    "interpolacion": ("METODOS", "Interpolacion", "interpolar"),
    "interseccion": ("Interseccion", "dividir", "intersecar", "intersecar_datos"),
}
_MODULO_DE = {nombre: modulo for modulo, nombres in _ORIGEN.items() for nombre in nombres}

__all__ = [
    "Datos", "ErrorDatos", "a_datos", "cargar", "hojas", "leer_tabla", "leer_texto",
    "Modelo", "ErrorModelo", "CATALOGO", "desde_expresion", "obtener", "polinomio",
    "ResultadoAjuste", "ErrorAjuste", "ajustar",
    "banda", "bondad", "formatear", "redondear",
    "CANDIDATOS_AUTO", "Seleccion", "seleccionar",
    "METODOS", "Interpolacion", "interpolar",
    "Interseccion", "dividir", "intersecar", "intersecar_datos",
]


def __getattr__(nombre: str):
    modulo = _MODULO_DE.get(nombre)
    if modulo is None:
        raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
    valor = getattr(importlib.import_module(f".{modulo}", __name__), nombre)
    globals()[nombre] = valor  # la próxima vez ya no pasa por aquí
    return valor


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


if TYPE_CHECKING:  # para los editores y comprobadores de tipos
    from .ajuste import ErrorAjuste, ResultadoAjuste, ajustar  # noqa: F401
    from .datos import Datos, ErrorDatos, a_datos, cargar, hojas, leer_tabla, leer_texto  # noqa: F401
    from .estadistica import banda, bondad, formatear, redondear  # noqa: F401
    from .interpolacion import METODOS, Interpolacion, interpolar  # noqa: F401
    from .interseccion import Interseccion, dividir, intersecar, intersecar_datos  # noqa: F401
    from .modelos import CATALOGO, ErrorModelo, Modelo, desde_expresion, obtener, polinomio  # noqa: F401
    from .seleccion import CANDIDATOS_AUTO, Seleccion, seleccionar  # noqa: F401
