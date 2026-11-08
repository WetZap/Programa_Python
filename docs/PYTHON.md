# Terminal y Python

[← README](../README.md) · [Instalación](INSTALACION.md) · [Guía](GUIA.md) · [Base estadística](ESTADISTICA.md) · **Terminal y Python** · [Desarrollo](DESARROLLO.md)

Todo lo que hace la interfaz se puede hacer sin ella. Hace falta la instalación con Python (los
[ejecutables](INSTALACION.md#ejecutables) solo traen la interfaz).

## Desde la terminal

```bash
ajustelab-cli medidas.csv                                  # ajuste lineal
ajustelab-cli medidas.csv -m exponencial_fondo -g ajuste.png -o informe.txt
ajustelab-cli medidas.csv -m "A*exp(-x/tau) + C" --p0 "5;1.5;0"
ajustelab-cli medidas.csv --seleccionar --criterio bic     # prueba todo el catálogo
ajustelab-cli medidas.dat --x t --y V --dy-cte 0.05 --excluir 3,7
ajustelab-cli medidas.csv -i pchip --tramos tramos.tex     # interpolación
ajustelab-cli --modelos                                    # lista del catálogo
ajustelab-cli --help
```

Las columnas se indican por nombre o por posición (empezando en 0). En `--p0` los valores se separan
con `;` para que la coma decimal no sea ambigua.

## Desde Python

```python
import numpy as np
from ajustelab import cargar, ajustar, seleccionar, interpolar, intersecar_datos, dividir

datos = cargar("ejemplos/descarga_rc.csv")          # detecta formato y columnas
res = ajustar(datos, "exponencial_fondo")            # o ajustar(datos, "V0*exp(-x/tau) + Vinf")
print(res.resumen())                                 # informe completo
tau, sigma_tau = res.parametros["tau"]

b = res.bondad()                                     # χ², p-valor, rachas, AICc...
print(b.chi2_red, b.p_valor, b.avisos)
f, inferior, superior = res.banda([1.0, 2.0], nivel=0.95)

res = ajustar(datos, "exponencial_fondo", fijos={"C": 0.32},        # C fijo
              limites=([-np.inf, 0], [np.inf, np.inf]))               # τ ≥ 0 (libres: A, tau)
print(res.sigma_f([1.0, 2.0]))                       # σ de la curva en esos x
print(res.inversa(2.0, sigma_y0=0.04))               # [(x, σx)] tal que f(x) = 2.0

sel = seleccionar(datos)                             # selección automática
print(sel.resumen())
print(sel.tabla())                                   # DataFrame con la clasificación

spline = interpolar(datos, "pchip")
r = spline.monte_carlo(lambda g: g.integral(1, 3))   # valor ± σ por Monte Carlo
print(r.nominal, r.sigma)

corte = intersecar_datos(*dividir(cargar("ejemplos/dos_rectas.dat"), 8))
print(corte.resumen())
```

Evaluar una interpolación y escribir el resumen para el informe:

```python
f = interpolar(cargar("calibracion.csv"), "pchip")
tabla = f.evaluar([100, 125, 150])                  # DataFrame: x, f, sigma_f, derivada, sigma_derivada
print(f.informe(xs=[100, 125, 150]))                 # párrafo + tabla corta
print(f.informe(xs=[100, 125, 150], latex=True))     # lo mismo en LaTeX (tabla booktabs)

from ajustelab.interpolacion import valores_x
valores_x("0:10:0,5")                                # las x como se escriben en la interfaz
```

Guardar una tabla (o una parte) en otro formato:

```python
from ajustelab.datos import guardar_tabla, leer_tabla

df = leer_tabla("medida_larga.csv")
guardar_tabla(df[df["t"] <= 100], "primeros_100s.xlsx")   # el formato sale de la extensión
guardar_tabla(df, "para_excel.csv", formato="csv_es")      # «;» y coma decimal
```

Para redondear cualquier resultado: `formatear(3.14159, 0.0234)` → `"3.142 ± 0.023"`.

Histogramas con su estadística:

```python
from ajustelab.histograma import ajustar_distribucion, histograma, resumen

h = histograma(medidas)                    # Freedman–Diaconis; también "scott", "sturges", "raiz",
                                           # intervalos=20 o ancho=0.5
y, dy = h.valores("densidad")              # alturas y errores √N en la normalización pedida
a = ajustar_distribucion(medidas, "normal", h)
print(a.texto())                           # μ ± σ_μ, σ ± σ_σ, χ², ν y p
print(resumen(medidas).filas())            # media ± error, mediana, cuartiles…
```

En `ejemplos/` hay tres demos ejecutables (`demo_fase1.py`, `demo_fase2.py`, `demo_fase3.py`) y
tres ficheros de datos sintéticos en formatos distintos.
