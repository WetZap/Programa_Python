"""Demostración de la selección automática de modelo (Fase 2).

    python ejemplos/demo_fase2.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows: χ², ± en consola/ficheros
from pathlib import Path

from ajustelab import cargar, seleccionar

datos = cargar(Path(__file__).with_name("descarga_rc.csv"))

seleccion = seleccionar(datos, progreso=lambda i, n, nombre: print(f"\r[{i}/{n}] {nombre:<30}", end=""))
print("\r" + " " * 50)
print(seleccion.resumen())

print("\n" + "=" * 70)
print("Detalle del recomendado:\n")
print(seleccion.recomendado.resultado.resumen())

# La tabla completa como DataFrame (la usará la GUI):
# print(seleccion.tabla().to_string())
