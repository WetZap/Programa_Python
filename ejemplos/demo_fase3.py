"""Demostración de interpolación e intersección (Fase 3).

    python ejemplos/demo_fase3.py

Los datos se generan aquí mismo (sintéticos) para que el resultado sea comprobable.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows: χ², ± en consola/ficheros
import numpy as np

from ajustelab import Datos, dividir, interpolar, intersecar_datos

# --- 1. Interpolación de una tabla con poco ruido -------------------------------
x = np.linspace(0, 8, 17)
y = np.exp(-x / 3) * np.cos(x)
tabla = Datos(x, y, dy=0.002, nombre_x="t", nombre_y="V")

f = interpolar(tabla, "natural")
print(f.resumen(), "\n")

r = f.monte_carlo(lambda g: g(2.3))
print(f"f(2.3) = {r.nominal:.5f} ± {r.sigma:.5f}   (exacto {np.exp(-2.3 / 3) * np.cos(2.3):.5f})")
print(f"Ceros de f: {np.round(f.inversa(0.0), 4)}   (exactos π/2, 3π/2, 5π/2 = "
      f"{np.round(np.pi * np.array([0.5, 1.5, 2.5]), 4)})")
I = f.monte_carlo(lambda g: g.integral(0, np.pi / 2))
print(f"∫_0^π/2 f dt = {I.nominal:.5f} ± {I.sigma:.5f}")
print("\nPrimeros tramos exportados:")
print("\n".join(f.exportar_tramos("txt").splitlines()[:4]))

# --- 2. Intersección (la antigua opción 4) -------------------------------------
rng = np.random.default_rng(3)
xa = np.linspace(0, 5, 8)
xb = np.linspace(6, 12, 8)
xs = np.concatenate([xa, xb])
ys = np.concatenate([1.8 * xa + 2, -0.7 * xb + 21]) + rng.normal(0, 0.15, xs.size)
todos = Datos(xs, ys, dy=0.15)
d1, d2 = dividir(todos, 8)  # 8 primeros puntos = recta 1, resto = recta 2

corte = intersecar_datos(d1, d2)
print("\n" + corte.resumen())
print(f"(valor real: x* = {19 / 2.5:.4f}, y* = {1.8 * 19 / 2.5 + 2:.4f})")
ancho, alto, angulo = corte.elipse(0.6827)
print(f"Elipse 68 %: ejes {ancho:.4f} × {alto:.4f}, girada {angulo:.1f}°")
