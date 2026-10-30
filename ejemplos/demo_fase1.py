"""Demostración del núcleo (Fase 1): lectura, ajuste y estadística.

Ejecutar desde la raíz del repositorio:
    python ejemplos/demo_fase1.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows: χ², ± en consola/ficheros
from pathlib import Path

from ajustelab import ajustar, cargar, leer_tabla

ruta = Path(__file__).with_name("descarga_rc.csv")

tabla = leer_tabla(ruta)
print("Detectado:", tabla.attrs)
datos = cargar(ruta)  # t, V, dt, dV asignadas por nombre
print(datos, *datos.avisos, sep="\n")

for modelo in ["exponencial", "V0*exp(-x/tau) + Vinf"]:
    print("\n" + "=" * 70)
    print(ajustar(datos, modelo).resumen())
