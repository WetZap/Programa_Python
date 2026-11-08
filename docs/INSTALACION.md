# Instalación

[← README](../README.md) · **Instalación** · [Guía](GUIA.md) · [Base estadística](ESTADISTICA.md) · [Terminal y Python](PYTHON.md) · [Desarrollo](DESARROLLO.md)

Hay dos formas de tenerlo:

| | Ejecutable (recomendado) | Con Python |
|---|---|---|
| **Qué necesitas** | Nada: lleva Python y todo dentro | Python ≥ 3.10 (los instaladores lo instalan si falta) |
| **Cómo** | Descargar e instalar, como cualquier programa | Una línea en la terminal, pipx o pip |
| **Actualizar** | Descargar la versión nueva | Volver a ejecutar la misma línea |
| **Terminal y Python** | Solo la interfaz (`ajustelab`) | También `ajustelab-cli` y `import ajustelab` |

1. [Ejecutables](#ejecutables)
2. [Linux: instalador de una línea](#linux-instalador-de-una-línea)
3. [Windows 10/11: instalador de una línea](#windows-1011-instalador-de-una-línea)
4. [Con pipx (cualquier sistema)](#con-pipx-cualquier-sistema)
5. [Paso a paso por sistema operativo](#paso-a-paso-por-sistema-operativo)
6. [Para desarrollar](#para-desarrollar-clonando-el-repositorio)
7. [Solución de problemas](#solución-de-problemas)

---

## Ejecutables

En la página de [**Releases**](https://github.com/WetZap/Programa_Python/releases/latest):

| Sistema | Fichero | Cómo se instala |
|---|---|---|
| **Windows 10/11** (64 bits) | `ajustelab-<versión>-windows-x64-instalador.exe` | Ábrelo y sigue los pasos. No pide permisos de administrador; crea el acceso del menú Inicio (y, si quieres, del escritorio), asocia las sesiones `.ajustelab` y se desinstala desde *Configuración → Aplicaciones*. |
| | `…-windows-x64-portable.zip` | Sin instalar: descomprímelo donde quieras y abre `ajustelab.exe`. |
| **macOS** con chip Apple (M1, M2…) | `ajustelab-<versión>-macos-arm64.dmg` | Ábrelo y arrastra *ajustelab* a *Aplicaciones*. |
| **macOS** con Intel | `ajustelab-<versión>-macos-x86_64.dmg` | Igual. (*Menú Apple → Acerca de este Mac* dice qué procesador tienes.) |
| **Linux** x86_64 | `ajustelab-<versión>-linux-x86_64.AppImage` | `chmod +x ajustelab-*.AppImage` y ejecútalo. Para tenerlo en el menú de aplicaciones, con su icono y el doble clic en `.ajustelab`: `./ajustelab-*.AppImage --instalar-escritorio`. |

La AppImage se construye en Ubuntu 22.04 y funciona en cualquier distribución con glibc ≥ 2.35
(Ubuntu 22.04+, Debian 12+, Fedora 36+, Arch, openSUSE Tumbleweed…). Lleva dentro Qt y sus
bibliotecas; del sistema solo usa el servidor gráfico (X11 o Wayland) y OpenGL, que tiene cualquier
escritorio. La CI la abre en contenedores limpios de Ubuntu 22.04, Debian, Fedora, Arch y openSUSE.

### Primera vez: el aviso del sistema

Los ejecutables no están firmados con un certificado de pago (cuestan unos cientos de euros al año), así
que el sistema avisa la primera vez que los abres. Es normal:

- **Windows**: «Windows protegió su PC» → *Más información* → *Ejecutar de todas formas*.
- **macOS**: si dice que Apple no puede comprobar que no tenga software malicioso, pulsa *OK*, ve a
  *Ajustes del Sistema → Privacidad y seguridad*, baja hasta el aviso de *ajustelab* y pulsa *Abrir
  igualmente*. Solo hace falta una vez.
- **Linux**: no hay aviso. Si al abrir la AppImage dice que falta FUSE (`libfuse.so.2`), instala
  `libfuse2` (`fuse2` en Arch, `fuse-libs` en Fedora) o ejecútala con `--appimage-extract-and-run`.

Para comprobar que la descarga está bien: `sha256sum -c --ignore-missing SHA256SUMS.txt` (el fichero está
en la misma Release).

> Puedes tener a la vez el ejecutable y la instalación con Python: van en carpetas distintas. Lo que sí
> comparten es la entrada del menú de aplicaciones: abre la última que hayas instalado.

---

## Linux: instalador de una línea

```bash
curl -fsSL https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.sh | sh
```

Funciona en Arch, Manjaro, EndeavourOS, CachyOS, Debian, Ubuntu, Mint, Pop!_OS, Fedora, openSUSE,
Void y sus derivadas. La CI lo prueba en contenedores limpios de Arch, Debian, Ubuntu 22.04, Fedora y
openSUSE Tumbleweed, abriendo la ventana en X11. Todo queda en tu usuario, sin tocar el Python
del sistema:

1. Busca Python ≥ 3.10 con `venv`; si no lo hay, ofrece instalarlo.
2. Crea un entorno propio en `~/.local/share/ajustelab/venv`. Así se evita el error
   *externally-managed-environment* de Arch, Debian o Fedora.
3. Deja las órdenes `ajustelab` y `ajustelab-cli` en `~/.local/bin`. Si esa carpeta no está en el
   PATH (en Arch no lo está por defecto), ofrece añadirla a tu `.bashrc`, `.zshrc` o a fish.
4. Detecta qué bibliotecas del sistema le faltan a Qt (la típica es `xcb-util-cursor`) y ofrece
   instalarlas con `pacman`, `apt`, `dnf`, `zypper` o `xbps-install`.
5. Añade **ajustelab al menú de aplicaciones** con su icono (GNOME, KDE Plasma, XFCE, Cinnamon, MATE,
   LXQt, COSMIC, o lanzadores como rofi, wofi y fuzzel en Hyprland o Sway). Además, asocia las sesiones
   `.ajustelab` para abrirlas con doble clic.
6. Comprueba que la interfaz arranca.

Siempre pregunta antes de instalar paquetes del sistema. Con `-y` responde que sí a todo:
`curl -fsSL …/instalar.sh | sh -s -- -y`.

| | |
|---|---|
| **Actualizar** | Vuelve a ejecutar la misma línea. También repara el entorno si una actualización del sistema cambió la versión de Python (pasa en Arch). |
| **Desde una copia clonada** | `sh instalar.sh` dentro del repositorio instala esa copia. |
| **Desinstalar** | `curl -fsSL …/instalar.sh \| sh -s -- --desinstalar` (o `sh instalar.sh --desinstalar`). |
| **Más opciones** | `sh instalar.sh --ayuda`: `--sin-menu`, `--sin-dependencias`, `--python RUTA`, `--rama RAMA`. |

Si prefieres leer el script antes de ejecutarlo:
`curl -fsSLO https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.sh`, ábrelo y
luego `sh instalar.sh`.

## Windows 10/11: instalador de una línea

En **PowerShell** (menú Inicio → «PowerShell»; no hace falta abrirlo como administrador):

```powershell
irm https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.ps1 | iex
```

Es el equivalente del instalador de Linux. Todo queda en tu usuario, sin permisos de administrador:

1. Busca Python ≥ 3.10 (lanzador `py` o PATH). Si no lo hay, ofrece instalar Python 3.13 con
   `winget`, sin abrir ninguna web.
2. Crea un entorno propio en `%LOCALAPPDATA%\Programs\ajustelab` e instala ajustelab ahí.
3. Deja las órdenes `ajustelab` y `ajustelab-cli` en su carpeta `bin` y la añade al PATH de tu
   usuario (en una terminal nueva ya funcionan).
4. Crea el acceso directo del **menú Inicio** (y, si quieres, del escritorio) con su icono. Además,
   asocia los ficheros `.ajustelab` para abrirlos con doble clic.
5. Lo registra en **Configuración → Aplicaciones**, desde donde se desinstala como cualquier programa.
6. Comprueba que la interfaz arranca.

| | |
|---|---|
| **Actualizar** | Vuelve a ejecutar la misma línea (si ajustelab está abierto, ofrece cerrarlo). |
| **Desinstalar** | Configuración → Aplicaciones → ajustelab → Desinstalar. |
| **Sin preguntas** | `& ([scriptblock]::Create((irm https://raw.githubusercontent.com/WetZap/Programa_Python/main/instalar.ps1))) -Si` |
| **Desde una copia clonada** | `powershell -ExecutionPolicy Bypass -File instalar.ps1` dentro del repositorio. |

Funciona con Windows PowerShell 5.1 (el que trae Windows) y con PowerShell 7. Si prefieres leer el
script antes, descárgalo con `irm …/instalar.ps1 -OutFile instalar.ps1`, ábrelo y ejecútalo con la
última orden de la tabla.

## Con pipx (cualquier sistema)

[pipx](https://pipx.pypa.io) instala la aplicación aislada y deja los comandos `ajustelab` y
`ajustelab-cli` disponibles en todo el sistema:

```bash
pipx install git+https://github.com/WetZap/Programa_Python
ajustelab --instalar-escritorio      # menú de aplicaciones (Linux) o menú Inicio (Windows)
ajustelab
```

## Paso a paso por sistema operativo

<details>
<summary><b>Windows, a mano</b></summary>

1. Instala Python desde [python.org](https://www.python.org/downloads/) (marca **«Add python.exe to
   PATH»**) o con `winget install Python.Python.3.13`.
2. En *PowerShell*:

   ```powershell
   py -m venv $env:LOCALAPPDATA\Programs\ajustelab\venv
   & $env:LOCALAPPDATA\Programs\ajustelab\venv\Scripts\pip install https://github.com/WetZap/Programa_Python/archive/refs/heads/main.zip
   & $env:LOCALAPPDATA\Programs\ajustelab\venv\Scripts\ajustelab --instalar-escritorio
   ```

3. La última orden crea el acceso directo del menú Inicio y asocia los `.ajustelab`. `ajustelab.exe`
   se abre sin ventana de consola.

</details>

<details>
<summary><b>macOS</b></summary>

1. Instala Python desde [python.org](https://www.python.org/downloads/) o con Homebrew
   (`brew install python`).
2. En la Terminal:

   ```bash
   python3 -m venv ~/ajustelab-venv
   source ~/ajustelab-venv/bin/activate
   pip install git+https://github.com/WetZap/Programa_Python
   ajustelab
   ```

Funciona en Mac con Intel y con Apple Silicon. La interfaz usa el estilo nativo de macOS.

</details>

<details>
<summary><b>Linux, a mano</b></summary>

Es lo mismo que hace el instalador, paso a paso:

```bash
python3 -m venv ~/.local/share/ajustelab/venv
~/.local/share/ajustelab/venv/bin/pip install https://github.com/WetZap/Programa_Python/archive/refs/heads/main.tar.gz
ln -s ~/.local/share/ajustelab/venv/bin/ajustelab ~/.local/bin/
ajustelab --diagnostico            # dice qué paquetes del sistema faltan y con qué orden instalarlos
ajustelab --instalar-escritorio    # entrada en el menú, icono y doble clic en .ajustelab
```

- En Debian/Ubuntu hace falta antes `sudo apt install python3-venv`.
- Qt ≥ 6.5 exige `libxcb-cursor0` (Debian/Ubuntu/openSUSE) o `xcb-util-cursor` (Arch/Fedora) en X11.
  Si falta, aparece el error *«Could not load the Qt platform plugin "xcb"»*. `ajustelab` lo detecta
  y muestra la orden exacta antes de que Qt falle.
- En Wayland funciona de forma nativa. Si tu compositor da problemas, prueba
  `QT_QPA_PLATFORM=xcb ajustelab`.
- Si tu escritorio no informa del modo claro/oscuro (i3, Sway sin portal, algunos XFCE), elige el
  tema a mano en **Ver → Tema**.

</details>

## Para desarrollar (clonando el repositorio)

```bash
git clone https://github.com/WetZap/Programa_Python.git
cd Programa_Python
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[test]"
pytest -m "not lento"
```

---

## Solución de problemas

Lo primero, en una terminal:

```bash
ajustelab --diagnostico
```

Indica la versión de Python y de Qt, la distribución, si la sesión es X11 o Wayland, qué bibliotecas
faltan (con la orden para instalarlas), si la entrada del menú está bien y si `~/.local/bin` está en
el PATH.

| Síntoma | Causa y solución |
|---|---|
| Al hacer clic en el menú no pasa nada, o sale el aviso *«El entorno de ajustelab ya no funciona»* | Una actualización del sistema cambió la versión de Python (habitual en Arch) y el entorno ya no sirve. Vuelve a ejecutar el instalador: lo detecta y lo rehace. |
| *Could not load the Qt platform plugin "xcb"* | Faltan bibliotecas de X11. `ajustelab` muestra antes la orden exacta para tu distribución; el instalador las instala si le dices que sí. |
| `command not found: ajustelab` tras instalar | `~/.local/bin` no está en el PATH: abre una terminal nueva (el instalador ofrece añadirlo) o, en zsh, ejecuta `rehash`. Si la versión es antigua (`ajustelab --version` < 1.1), vuelve a ejecutar el instalador: sustituye las instalaciones anteriores. |
| `error: externally-managed-environment` al usar `pip install` | Tu distribución protege el Python del sistema (PEP 668). Usa el instalador, pipx o un entorno virtual; no hace falta `--break-system-packages`. |
| En Wayland, la ventana aparece con un icono genérico en el dock | En Wayland el icono sale de la entrada del menú: ejecuta `ajustelab --instalar-escritorio`. |
| zsh pregunta `correct 'pip' to '_pip' [nyae]?` | Es la autocorrección de zsh: responde `n`. Para que no vuelva a pasar, usa `python -m pip ...` o añade `unsetopt correct` a `~/.zshrc`. |
| La ventana no sigue el modo oscuro | Tu escritorio no informa del esquema de color: elige el tema en **Ver → Tema**. |
| Windows: `irm` no funciona o dice que la ejecución de scripts está deshabilitada | `irm … \| iex` no ejecuta ningún fichero, así que la directiva de ejecución no le afecta. Si tu organización bloquea PowerShell, usa la instalación a mano o pipx. |
| Windows: `ajustelab` no se reconoce justo después de instalar | Abre una terminal nueva: las que ya estaban abiertas no ven el PATH actualizado. Desde el menú Inicio funciona siempre. |
| Windows: la barra de tareas muestra el icono de Python | Vuelve a crear el acceso directo con `ajustelab --instalar-escritorio` (o reinstala): el acceso y la ventana comparten identificador para agruparse. |
| macOS: *«ajustelab está dañado y no se puede abrir»* | macOS ha marcado la descarga y la firma no le basta. En la Terminal: `xattr -dr com.apple.quarantine /Applications/ajustelab.app` y vuelve a abrirlo. |
| Linux: la AppImage no arranca y habla de FUSE o `libfuse.so.2` | Instala `libfuse2` (`fuse2` en Arch, `fuse-libs` en Fedora) o ejecútala con `--appimage-extract-and-run`. |
| NixOS o Alpine | Los paquetes de Qt de PyPI no funcionan ahí: Alpine usa musl, y NixOS no tiene las bibliotecas en rutas estándar. En NixOS usa `python3Packages.pyside6` o activa `programs.nix-ld`. |
| En Windows, los símbolos χ² o ± salen mal al redirigir la salida de `ajustelab-cli` | Usa `PYTHONIOENCODING=utf-8` o el informe con `-o informe.txt`, que siempre está en UTF-8. |

Para ver todos los avisos de Qt (algunos se ocultan porque solo llenan la terminal), arranca con
`AJUSTELAB_DEPURAR=1 ajustelab`.
