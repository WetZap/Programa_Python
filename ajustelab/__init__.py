"""ajustelab — ajuste de datos experimentales con base estadística.

Uso rápido::

    from ajustelab import cargar, ajustar
    datos = cargar("medidas.csv")          # detecta formato y columnas x, y, dx, dy
    res = ajustar(datos, "lineal")          # o una expresión: "A*exp(-x/tau) + C"
    print(res.resumen())
    print(seleccionar(datos))             # prueba todo el catálogo y recomienda
    f = interpolar(datos, "pchip")          # interpolación / spline de suavizado
"""
from .ajuste import ErrorAjuste, ResultadoAjuste, ajustar
from .datos import Datos, ErrorDatos, a_datos, cargar, hojas, leer_tabla, leer_texto
from .estadistica import banda, bondad, formatear, redondear
from .modelos import CATALOGO, ErrorModelo, Modelo, desde_expresion, obtener, polinomio
from .seleccion import CANDIDATOS_AUTO, Seleccion, seleccionar
from .interpolacion import METODOS, Interpolacion, interpolar
from .interseccion import Interseccion, dividir, intersecar, intersecar_datos

__version__ = "1.1.0"

__all__ = [
    "Datos", "ErrorDatos", "a_datos", "cargar", "hojas", "leer_tabla", "leer_texto",
    "Modelo", "ErrorModelo", "CATALOGO", "desde_expresion", "obtener", "polinomio",
    "ResultadoAjuste", "ErrorAjuste", "ajustar",
    "banda", "bondad", "formatear", "redondear",
    "CANDIDATOS_AUTO", "Seleccion", "seleccionar",
    "METODOS", "Interpolacion", "interpolar",
    "Interseccion", "dividir", "intersecar", "intersecar_datos",
]
