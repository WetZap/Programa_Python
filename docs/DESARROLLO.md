# Desarrollo

[← README](../README.md) · [Instalación](INSTALACION.md) · [Guía](GUIA.md) · [Base estadística](ESTADISTICA.md) · [Terminal y Python](PYTHON.md) · **Desarrollo**

Las contribuciones son bienvenidas mediante *fork* y *pull request*. Las convenciones del proyecto (y lo
que conviene saber antes de tocar el código) están en [`CLAUDE.md`](../CLAUDE.md).

## Preparar el entorno

```bash
git clone https://github.com/WetZap/Programa_Python.git
cd Programa_Python
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[test]"
```

## Tests

```bash
pytest -m "not lento"      # rápido (~1-2 min): todo menos las validaciones Monte Carlo largas
pytest                     # completo (~4 min)
pytest -m gui              # solo la interfaz (sin pantalla)
```

Los tests de la interfaz usan `QT_QPA_PLATFORM=offscreen`, así que no abren ventanas. En algunas
máquinas Qt puede fallar **al cerrar** el proceso, después de que pytest haya terminado: mira el
resumen de pytest y su código de salida (`echo $?`), no lo que salga después.

El instalador de Linux se comprueba con `shellcheck -s sh instalar.sh`. El de Windows pasa
PSScriptAnalyzer.

## Integración continua

| Workflow | Cuándo | Qué hace |
|---|---|---|
| [`tests.yml`](../.github/workflows/tests.yml) | Cada push y PR | Tests en Ubuntu, Windows y macOS con Python 3.10, 3.13 y 3.14; `instalar.sh` en contenedores limpios de Arch, Debian, Ubuntu 22.04, Fedora y openSUSE (abriendo la ventana en X11); `instalar.ps1` con Windows PowerShell 5.1 y PowerShell 7, también con `irm \| iex`. |
| [`ejecutables.yml`](../.github/workflows/ejecutables.yml) | PR que tocan `empaquetado/`, etiquetas `v*` y a mano | Construye los ejecutables de Windows, macOS (Apple Silicon e Intel) y Linux, y los prueba: instala, abre y desinstala el de Windows; monta el `.dmg` y abre la app; abre la AppImage en X11 en cinco distribuciones. Con una etiqueta, publica la Release. |

## Ejecutables

Se hacen con [PyInstaller](https://pyinstaller.org) (modo carpeta, que arranca más rápido que un único
fichero) y se empaquetan con las herramientas de cada sistema:

```bash
pip install . pyinstaller pillow
python empaquetado/construir.py --probar     # ejecutable + paquete de este sistema, y lo prueba sin pantalla
```

| Fichero | Qué es |
|---|---|
| `empaquetado/ajustelab.spec` | Qué entra en el ejecutable. Deja fuera tkinter, GTK, IPython, pytest y las traducciones de Qt que no son español ni inglés. |
| `empaquetado/construir.py` | Llama a PyInstaller y hace el paquete: AppImage (descarga `appimagetool`), instalador de Inno Setup y zip portable, o `.dmg` firmado ad hoc. Con `--probar` abre el ejecutable con `--probar-interfaz`. |
| `empaquetado/ajustelab.iss` | Instalador de Windows (Inno Setup 6): por usuario, sin administrador, en `%LOCALAPPDATA%\Programs\WetZap\ajustelab`. |
| `empaquetado/notas_release.md` | Texto de la Release (descargas y avisos de la primera vez). |

Cada sistema construye solo su paquete: PyInstaller no compila para otro sistema. La AppImage se hace
en Ubuntu 22.04 para que funcione con glibc ≥ 2.35; si se construye en un sistema más nuevo, solo
funcionará en sistemas igual de nuevos.

### Publicar una versión

1. Sube la versión en `ajustelab/__init__.py` y en `pyproject.toml` (las dos iguales).
2. Fusiona en `main` con la CI en verde.
3. Crea y sube la etiqueta: `git tag v1.7.0 && git push origin v1.7.0`.

`ejecutables.yml` comprueba que la etiqueta coincide con la versión, construye y prueba todo, y publica
la Release con los ficheros y `SHA256SUMS.txt`. Si la Release ya existe, sustituye los ficheros.

## Estructura del proyecto

```
Programa_Python/
├── ajustelab/
│   ├── datos.py           # lectura multiformato, asignación de columnas y guardar tablas
│   ├── modelos.py         # modelos (SymPy), catálogo y valores iniciales
│   ├── ajuste.py          # WLS / varianza efectiva / OLS, arranque múltiple
│   ├── estadistica.py     # bondad, tests, bandas, AICc/BIC, redondeo, informe
│   ├── seleccion.py       # selección automática de modelo
│   ├── interpolacion.py   # splines, PCHIP, Akima, suavizado, Monte Carlo, evaluar y resumen
│   ├── interseccion.py    # corte de dos curvas con covarianza
│   ├── histograma.py      # intervalos, errores √N, ajuste de distribuciones y test χ²
│   ├── fuentes.py         # tipografía Inter (Qt y matplotlib)
│   ├── cli.py             # ajustelab-cli
│   ├── lanzador.py        # orden ajustelab: opciones de sistema y arranque de la interfaz
│   ├── sistema.py         # diagnóstico: distro, sesión X11/Wayland, bibliotecas de Qt
│   ├── escritorio.py      # menú de aplicaciones, icono y tipo de fichero (freedesktop y Windows)
│   ├── windows.py         # acceso directo con AppUserModelID y asociación de .ajustelab
│   ├── recursos/fuentes/  # Inter 4.1 (subconjunto latino, griego y matemático) y su licencia OFL
│   └── gui/               # interfaz PySide6
│       ├── app.py         #   ventana, menús, paneles acoplables, deshacer, sesiones
│       ├── tabla.py       #   tabla editable (con deshacer), columnas y rango escrito
│       ├── guardar_datos.py #  diálogo para guardar la tabla o una parte
│       ├── grafica.py     #   dibujo con matplotlib (sin Qt): opciones, marcas, cuadro de resultados
│       ├── lienzo.py      #   widget de la gráfica: herramientas, arrastrar, menú contextual
│       ├── graficas.py    #   histograma, barras, sectores, cajas / violín y polar
│       ├── paneles.py     #   base de las pestañas y pestaña Ajuste
│       ├── panel_seleccion.py, panel_interpolacion.py, panel_interseccion.py
│       ├── representar.py #   pestaña Representar (tipo de gráfica, cortes del eje x)
│       ├── tabla_series.py #  tabla de series de Representar
│       ├── personalizar.py #  diálogo Personalizar, marcas y plantillas de estilo
│       ├── dialogos.py    #   exportar gráfica (vista previa, formatos, CSV)
│       ├── sesion.py      #   ficheros .ajustelab
│       ├── util.py, tema.py, estilo.py, iconos.py, widgets.py, ejemplos.py, acerca.py, trabajos.py
│       └── recursos/      #   icono de la aplicación y sorpresa (ver LEEME.txt)
├── tests/                 # pytest (núcleo, Monte Carlo, interfaz, terminal)
├── ejemplos/              # datos sintéticos y demos
├── empaquetado/           # ejecutables: PyInstaller, AppImage, Inno Setup, .dmg
├── docs/                  # esta documentación y las capturas
├── instalar.sh            # instalador para Linux (con Python)
├── instalar.ps1           # instalador para Windows (con Python)
├── legacy/ProgramasUtiles.py   # script original, conservado como referencia
├── .github/workflows/     # tests.yml y ejecutables.yml
├── CLAUDE.md              # guía del proyecto para quien lo modifique (personas o IA)
└── pyproject.toml
```
