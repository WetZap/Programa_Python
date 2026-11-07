# ajustelab — ajuste de datos experimentales

[![tests](https://github.com/WetZap/Programa_Python/actions/workflows/tests.yml/badge.svg)](https://github.com/WetZap/Programa_Python/actions/workflows/tests.yml)
[![ejecutables](https://github.com/WetZap/Programa_Python/actions/workflows/ejecutables.yml/badge.svg)](https://github.com/WetZap/Programa_Python/actions/workflows/ejecutables.yml)
[![Release](https://img.shields.io/github/v/release/WetZap/Programa_Python?label=descargar)](https://github.com/WetZap/Programa_Python/releases/latest)
![Plataformas](https://img.shields.io/badge/Windows%20%7C%20macOS%20%7C%20Linux-informational)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)

Programa para **ajustar, comparar, interpolar y representar datos de laboratorio** con una base
estadística seria: incertidumbres en x e y, χ² y p-valor, tests sobre los residuos, bandas de
confianza, redondeo correcto de resultados y **selección automática del modelo** que mejor describe
los datos.

Nació en las prácticas del Grado en Física de la **Universidad de Granada** para dejar de escribir
un script distinto para cada ajuste. Se usa con **interfaz gráfica**, desde la **terminal** o como
**biblioteca de Python**.

![Ajuste con un punto excluido y panel de residuos](docs/capturas/ajuste_claro.png)

| Selección automática de modelo (modo oscuro) | Marcas sobre la gráfica |
|---|---|
| ![Selección de modelo](docs/capturas/seleccion_oscuro.png) | ![Marcas](docs/capturas/marcas_claro.png) |

---

## Descargar

No hace falta instalar Python: descarga el fichero de tu sistema en
[**Releases**](https://github.com/WetZap/Programa_Python/releases/latest).

| Sistema | Fichero |
|---|---|
| **Windows 10/11** | `…-windows-x64-instalador.exe` (o el `…-portable.zip`, sin instalar) |
| **macOS** con chip Apple (M1, M2…) | `…-macos-arm64.dmg` |
| **macOS** con Intel | `…-macos-x86_64.dmg` |
| **Linux** (Ubuntu 22.04+, Debian 12+, Fedora, Arch, openSUSE…) | `…-linux-x86_64.AppImage` |

Los ejecutables no están firmados con un certificado de pago, así que **la primera vez** el sistema
avisa: en Windows, *Más información → Ejecutar de todas formas*; en macOS, *Ajustes del Sistema →
Privacidad y seguridad → Abrir igualmente*. En Linux: `chmod +x ajustelab-*.AppImage` y ejecútalo
(con `--instalar-escritorio` lo añade al menú de aplicaciones). Detalles en
[Instalación](docs/INSTALACION.md#ejecutables).

### Con Python (incluye `ajustelab-cli` y la biblioteca)

```bash
# Linux (cualquier distribución)
curl -fsSL https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.sh | sh
```

```powershell
# Windows 10/11, en PowerShell
irm https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.ps1 | iex
```

```bash
# Cualquier sistema, con pipx
pipx install git+https://github.com/WetZap/Programa_Python
```

Los instaladores lo dejan todo en tu usuario (sin administrador), instalan Python si falta, crean el
acceso en el menú y se actualizan volviendo a ejecutar la misma línea. Más opciones en
[Instalación](docs/INSTALACION.md).

---

## Primeros pasos

1. **Abre unos datos**: *Abrir* (Ctrl+O), arrastra el fichero a la ventana o pega una tabla copiada de
   Excel o LibreOffice (Ctrl+Mayús+V). Si es la primera vez, *Datos de ejemplo* trae diez conjuntos.
2. **Comprueba las columnas** x, y, σx y σy (se asignan solas).
3. **Elige una pestaña** y pulsa **Ctrl+Intro**:

| Pestaña | Qué hace |
|---|---|
| **Representar** | Dibuja las columnas sin ajustar: puntos x-y con uno o dos ejes y, eje x partido, histograma, barras, sectores, cajas / violín o polar. |
| **Ajuste** | Ajusta un modelo del catálogo o una expresión propia (`A*exp(-x/tau) + C`), con parámetros fijos y límites, bondad del ajuste y bandas. |
| **Selección de modelo** | Prueba todo el catálogo y recomienda un modelo por AICc o BIC. |
| **Interpolación** | Splines, PCHIP, Akima…: evalúa f(17), una tabla de valores, la inversa y la integral, con su error, y escribe un resumen para el informe. |
| **Intersección** | Punto de corte de dos ajustes con su elipse de confianza. |

La [guía de la interfaz](docs/GUIA.md) lo explica todo con capturas.

---

## Qué hace

- **Lee casi cualquier fichero de datos**: csv, dat, txt, xlsx, ods, json, npy, mat… Detecta solo el
  separador, la coma decimal, la cabecera, las líneas de metadatos (osciloscopios, LabVIEW) y las
  columnas de texto.
- **Incertidumbres en x e y**: mínimos cuadrados ponderados; con σ_x, *varianza efectiva*; sin
  incertidumbres, mínimos cuadrados ordinarios con errores escalados.
- **Bondad del ajuste completa**: χ², χ²_ν, p-valor, test de rachas, Shapiro–Wilk, Durbin–Watson,
  correlaciones, atípicos y avisos que explican qué significa cada problema.
- **23 modelos** con valores iniciales automáticos y robustos, y **modelos propios** escritos como texto.
- **Selección automática** por AICc o BIC que descarta los ajustes degenerados o físicamente imposibles.
- **Interpolación** con 10 métodos, derivada, integral, inversa y error por Monte Carlo; **evalúa en un
  punto o en una tabla** y da un **resumen para el informe** en vez de decenas de tramos.
- **Intersección de dos curvas** con su matriz de covarianza.
- **Resultados listos para el informe**: redondeo con la regla del PDG, tablas en LaTeX y gráficas
  PNG/PDF/SVG/EPS al tamaño exacto en cm.
- **Gráficas a tu gusto**: título, leyenda y textos que se arrastran, **marcas** para señalar puntos,
  tramos o valores de referencia, límites, marcas de los ejes, notación científica y **plantillas de
  estilo** (como *Revista (física)*).
- **Trabajo cómodo**: excluir puntos con un clic, **rango de x escrito o arrastrado**, **guardar una parte
  de los datos** como fichero nuevo, deshacer/rehacer, sesiones `.ajustelab`, coma decimal, tema
  claro/oscuro y fluidez con decenas de miles de puntos.
- Funciona en **Windows, macOS y Linux** (X11 y Wayland), con la tipografía **Inter** incluida.

### Novedades de la 1.7

- **Rango de x escrito** en el panel *Datos* (desde – hasta), sin tener que acertar con el ratón.
- **Guardar datos como…** (Ctrl+Mayús+D): la tabla o una parte (por x, por filas, la selección, las
  incluidas…) en csv, xlsx, ods, json o texto, y abrirla como tabla nueva.
- **Interpolación**: evaluar f(x) en un punto o en una tabla de x, y **resumen para el informe** (texto o
  LaTeX) en lugar de los tramos.
- **Marcas** en la gráfica: puntos, tramos de x y líneas verticales u horizontales, con texto, color,
  forma y estilo.
- **Ejecutables** para Windows, macOS y Linux, y más fluidez con muchos datos.

---

## Documentación

| | |
|---|---|
| [Instalación](docs/INSTALACION.md) | Ejecutables, instaladores de una línea, pipx, paso a paso y solución de problemas. |
| [Guía de la interfaz](docs/GUIA.md) | Cada pestaña, las herramientas de la gráfica, personalizar, exportar y los atajos. |
| [Base estadística](docs/ESTADISTICA.md) | Métodos y fórmulas, catálogo de modelos, interpolación, validación y referencias. |
| [Terminal y Python](docs/PYTHON.md) | `ajustelab-cli` y la biblioteca (`from ajustelab import ajustar`). |
| [Desarrollo](docs/DESARROLLO.md) | Tests, CI, cómo se construyen los ejecutables y la estructura del código. |

Si algo no arranca, lo primero es `ajustelab --diagnostico` (ver
[Solución de problemas](docs/INSTALACION.md#solución-de-problemas)).

---

## Licencia

[MIT](LICENSE) © 2026 Jorge del Río López (WetZap). Puedes usar, modificar y distribuir el código
manteniendo la atribución.

La tipografía [Inter](https://rsms.me/inter/) (© The Inter Project Authors) se distribuye con el programa
bajo la [SIL Open Font License 1.1](ajustelab/recursos/fuentes/OFL-Inter.txt).
