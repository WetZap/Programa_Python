# CLAUDE.md — guía del proyecto ajustelab

Para quien modifique el código (personas o asistentes de IA). Léela entera antes de tocar nada: resume
decisiones que no se ven en el código y errores que ya se cometieron.

## Qué es

`ajustelab`: ajuste, estadística, interpolación y gráficas para el laboratorio de Física (UGR). Núcleo en
Python puro (NumPy, SciPy, SymPy, pandas) y una interfaz PySide6 + matplotlib. Repositorio
`WetZap/Programa_Python`; autor Jorge del Río López (WetZap). Documentación de usuario en `README.md`
(corto) y `docs/` (`INSTALACION`, `GUIA`, `ESTADISTICA`, `PYTHON`, `DESARROLLO`).

## Reglas de trabajo

- **Todo en español**: interfaz, mensajes, nombres de funciones y variables, comentarios, documentación,
  commits y PR. Términos técnicos sin traducción (spline, AICc) se dejan como están.
- **Funciona en todos los sistemas y escritorios**: Windows 10/11, macOS (Intel y Apple Silicon), Linux
  (X11 y Wayland; GNOME, KDE, XFCE, Hyprland…). Antes de un cambio que afecte a un sistema concreto,
  **se consulta al autor**.
- **Ramas y PR**: nunca se sube a `main`. Rama nueva (`gui/…`, `nucleo/…`), PR, CI en verde; **el autor
  fusiona**. Commits con `git -c user.name=WetZap -c user.email=jorgerlvdg2016@gmail.com commit` (ese
  correo, solo para la autoría).
- La API de GitHub se usa por REST (`gh api repos/WetZap/Programa_Python/...`); GraphQL no está
  disponible en el entorno de Claude.
- Versión en **dos sitios**: `ajustelab/__init__.py` (`__version__`) y `pyproject.toml`. La etiqueta
  `vX.Y.Z` debe coincidir (lo comprueba `ejecutables.yml`).

## Comprobar un cambio

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -m "not lento" -q -p no:cacheprovider; echo "EXIT=$?"
python -m pyflakes ajustelab tests          # sin avisos
```

- Mira el **código de salida de pytest**, sin tuberías (`| tail` lo oculta). Qt puede dar una violación
  de segmento **al cerrar el proceso**, después del resumen: si el resumen dice `passed` y `EXIT=0`,
  está bien.
- `pytest -m lento`: validaciones Monte Carlo (~2 min). `pytest -m gui`: solo la interfaz.
- En `tests/test_gui.py`: fixtures `app` y `ventana`; `esperar(app, w)` deja terminar los trabajos en
  segundo plano y el temporizador de 200 ms; `_px`, `_evento` y `arrastrar` simulan el ratón sobre el
  lienzo de matplotlib. Los diálogos modales se sustituyen con `monkeypatch` (`exec`, `QFileDialog`…).
- Rendimiento: probar con 50 000–200 000 filas cuando se toque la tabla, la lectura o el dibujo.

## Arquitectura

**Núcleo** (`ajustelab/`, sin Qt): `datos` (lectura y `guardar_tabla`), `modelos`, `ajuste`,
`estadistica` (`formatear` = redondeo PDG), `seleccion`, `interpolacion` (`evaluar`, `informe`,
`valores_x`, `monte_carlo`), `interseccion`, `histograma`, `cli`. `__init__.py` importa de forma perezosa
(PEP 562): `ajustelab --version` no debe cargar SciPy.

**Arranque y sistema**: `lanzador.py` (orden `ajustelab`, `--diagnostico`, `--probar-interfaz`,
`--instalar-escritorio`), `sistema.py` (bibliotecas de Qt que faltan), `escritorio.py` (`.desktop`,
iconos, MIME; en el ejecutable apunta a `$APPIMAGE` o a `sys.executable`), `windows.py`.
`getattr(sys, "frozen", False)` distingue el ejecutable de PyInstaller.

**Interfaz** (`ajustelab/gui/`):

- `app.py`: `VentanaPrincipal`, menús, sesiones, deshacer (`QUndoStack` en `w.pila`) y `lanzar(Trabajo,
  al_terminar, texto, canal=…)` para cálculos en segundo plano (un trabajo nuevo en el mismo canal
  descarta el anterior).
- `tabla.py`: `ModeloTabla` (valores en `_v`, texto en `_t`, `excluidas`, `rango_x`; cada cambio pasa por
  `_registrar` para poder deshacerlo) y `PanelDatos` (columnas y rango escrito).
- `grafica.py`: **solo matplotlib, sin Qt**. `OpcionesGrafica` (dataclass; `a_dict`/`desde_dict`
  toleran sesiones antiguas), `Escena`, `dibujar(fig, escena, opciones, colores, oscuro)`. Las posiciones
  movibles son tuplas `(x, y, "ejes"|"figura")`; `fig._ajustelab` guarda lo que el lienzo necesita
  (movibles, destacados, ejes, límites, cortes). `CLAVES_ESTILO` = lo que guardan las plantillas;
  `reiniciar_contenido()` borra textos, límites, notas y marcas al abrir otros datos.
- `lienzo.py`: el widget `Grafica` (herramientas Región, Rango, Cortar, Marcar; arrastrar y editar;
  menú contextual). `from .grafica import Grafica` sigue funcionando por compatibilidad.
- Pestañas: `Panel` base en `paneles.py` (`escena`, `recalcular`, `estado`/`restaurar`, `texto_informe`),
  `PanelAjuste` en `paneles.py`, y `panel_seleccion.py`, `panel_interpolacion.py`, `panel_interseccion.py`,
  `representar.py` (+ `tabla_series.py`, `graficas.py` para histograma, barras, sectores, cajas y polar).
- `personalizar.py`: diálogo por pestañas, `DialogoMarca`, plantillas (QSettings).
- `util.py`: `numero()` (None si no es número) y `numero_estricto()` (lanza `ValueError`); ambos admiten
  coma decimal. Úsalos en vez de `float()` en los campos de texto.
- `sesion.py`: JSON `.ajustelab` con `VERSION`; añadir claves nuevas sin romper las sesiones viejas.

## Ejecutables

`empaquetado/` (PyInstaller en modo carpeta) + `.github/workflows/ejecutables.yml`. Detalles en
`docs/DESARROLLO.md`. Lo que no es evidente:

- La AppImage se construye en **Ubuntu 22.04** (glibc 2.35 como mínimo). Se instalan antes las
  bibliotecas xcb/Wayland para que PyInstaller las meta dentro.
- El instalador de Windows va a `%LOCALAPPDATA%\Programs\WetZap\ajustelab`: **no** a
  `Programs\ajustelab`, que es la carpeta de `instalar.ps1`.
- `ajustelab.iss` va en UTF-8 **con** BOM (Inno Setup); `instalar.ps1` **sin** BOM (`irm | iex`).
- `ajustelab.exe` es de ventana: `sys.stdout` puede ser `None` (`lanzador._consola_windows` lo resuelve).
- El `.dmg` va firmado ad hoc (`codesign --sign -`), sin certificado de Apple: la primera vez hay que
  pulsar *Abrir igualmente*. Windows avisa con SmartScreen. Ningún ejecutable está firmado.
- `--probar-interfaz` (abre la ventana, carga un ejemplo y ajusta) es la prueba de humo de los
  ejecutables y de los instaladores.

## Trampas conocidas

- `QFormLayout`: para ocultar una fila usa `setRowVisible`; ocultar el widget deja el hueco.
- Lectura de texto: no quitar los tabuladores iniciales de una línea (son celdas vacías).
- Pasos de CI con `shell: powershell` (5.1): el script va en ASCII, porque lo lee como CP1252.
- Con muchos puntos, nada de bucles por punto en Python al dibujar o al convertir coordenadas;
  `grafica._errorbar` tiene un camino rápido a partir de 3000 puntos.
- Al dividir módulos grandes, revisar los imports con `pyflakes` y las importaciones circulares
  (`lienzo` importa de `grafica`; `grafica` solo da `Grafica` de forma perezosa, con `__getattr__`).
- Capturas de `docs/capturas/`: se hacen con `QT_QPA_PLATFORM=offscreen`, `VentanaPrincipal` a
  1400×860, tema claro (u oscuro), y `w.grab().save(...)`; QSettings en una carpeta temporal para no
  heredar ajustes.

## Al terminar un cambio

1. Tests con `EXIT=0` y `pyflakes` limpio.
2. Documentar lo nuevo en `docs/GUIA.md` (y en el README si es una función destacada), con captura si
   se ve en la interfaz.
3. Commit, PR con resumen de cambios y pruebas, y esperar la CI (`tests` y, si toca `empaquetado/`,
   `ejecutables`).
