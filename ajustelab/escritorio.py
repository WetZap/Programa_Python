"""Integración con el escritorio: menú de aplicaciones, icono y doble clic en las
sesiones ``.ajustelab``. Todo para el usuario, sin permisos de administrador.

En **Windows** (ver ``windows.py``): acceso directo en el menú Inicio con el mismo
AppUserModelID que la ventana, y asociación de ``.ajustelab`` en HKEY_CURRENT_USER.

En **Linux y BSD**, según los estándares de freedesktop.org, ``ajustelab
--instalar-escritorio`` instala:

* la entrada del menú de aplicaciones (``ajustelab.desktop``),
* el icono en el tema *hicolor* (SVG y PNG de 16 a 512 px),
* el tipo MIME ``application/x-ajustelab`` para que las sesiones ``.ajustelab``
  se abran con doble clic y tengan icono propio.

Sirve igual en GNOME, KDE Plasma, XFCE, Cinnamon, MATE, LXQt, Budgie, COSMIC… y
en los lanzadores que leen ficheros .desktop (rofi, wofi, fuzzel, Albert…).
La entrada usa la ruta absoluta del ejecutable, así que funciona aunque
``~/.local/bin`` no esté en el PATH de la sesión gráfica.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ID = "ajustelab"
ES_WINDOWS = sys.platform == "win32"
MIME = "application/x-ajustelab"
TAMANOS = (16, 24, 32, 48, 64, 128, 256, 512)
RECURSOS = Path(__file__).resolve().parent / "gui" / "recursos"


class ErrorEscritorio(Exception):
    pass


def datos_usuario() -> Path:
    """$XDG_DATA_HOME o ~/.local/share."""
    valor = os.environ.get("XDG_DATA_HOME", "")
    return Path(valor) if valor and Path(valor).is_absolute() else Path.home() / ".local" / "share"


def ruta_desktop(base: Path | None = None) -> Path:
    return (base or datos_usuario()) / "applications" / f"{ID}.desktop"


def ficheros(base: Path | None = None) -> list[Path]:
    """Todo lo que instala ``instalar`` (para desinstalar sin dejar restos)."""
    base = base or datos_usuario()
    hicolor = base / "icons" / "hicolor"
    return [ruta_desktop(base), base / "mime" / "packages" / f"{ID}.xml",
            hicolor / "scalable" / "apps" / f"{ID}.svg",
            *(hicolor / f"{n}x{n}" / "apps" / f"{ID}.png" for n in TAMANOS)]


def _lanzador_instalador() -> Path | None:
    """Lanzador que deja ``instalar.sh`` junto al entorno (``…/ajustelab/bin/ajustelab``).
    Comprueba que el entorno funciona y, si no, explica cómo repararlo."""
    if sys.prefix == sys.base_prefix:  # no es un entorno virtual
        return None
    ruta = Path(sys.prefix).absolute().parent / "bin" / ID
    try:
        if os.access(ruta, os.X_OK) and "instalar.sh de ajustelab" in ruta.read_text(encoding="utf-8")[:300]:
            return ruta
    except (OSError, UnicodeDecodeError):
        pass
    return None


def orden_lanzar() -> list[str]:
    """Orden absoluta que abre ajustelab con el Python de esta instalación.

    No se resuelven enlaces: en un entorno virtual, ``bin/python`` es un enlace al
    Python del sistema y resolverlo perdería las dependencias del entorno."""
    if getattr(sys, "frozen", False):  # ejecutable independiente (PyInstaller)
        appimage = os.environ.get("APPIMAGE")  # dentro de una AppImage, el fichero .AppImage
        return [appimage if appimage else str(Path(sys.executable).absolute())]
    python = Path(sys.executable).absolute()
    if ES_WINDOWS:
        # Scripts\ajustelab.exe es el lanzador sin consola que crea pip; si no está
        # (instalación con --user), pythonw.exe -m ajustelab tampoco abre consola.
        lanzador = python.with_name(f"{ID}.exe")
        if lanzador.is_file():
            return [str(lanzador)]
        pythonw = python.with_name("pythonw.exe")
        return [str(pythonw if pythonw.is_file() else python), "-m", ID]
    lanzador = _lanzador_instalador()
    if lanzador is not None:
        return [str(lanzador)]
    lanzador = python.with_name(ID)
    if lanzador.is_file() and os.access(lanzador, os.X_OK):
        return [str(lanzador)]
    return [str(python), "-m", ID]


def citar_exec(arg: str) -> str:
    """Cita un argumento para la clave Exec (especificación Desktop Entry, reglas de 1.1 en adelante)."""
    arg = arg.replace("%", "%%")
    if not re.search(r"""[\s"'\\><~|&;$*?#()`]""", arg):
        return arg
    dentro = re.sub(r'(["`$\\])', r"\\\1", arg)
    return '"' + dentro.replace("\\", "\\\\") + '"'  # el escape general de cadenas va primero


def contenido_desktop(orden: list[str]) -> str:
    exec_ = " ".join(citar_exec(a) for a in orden) + " %f"
    return f"""[Desktop Entry]
Type=Application
Version=1.1
Name=ajustelab
GenericName=Ajuste de datos experimentales
GenericName[en]=Experimental data fitting
Comment=Ajusta, compara e interpola datos de laboratorio con incertidumbres y bondad del ajuste
Comment[en]=Fit, compare and interpolate lab data with uncertainties and goodness of fit
Exec={exec_}
TryExec={orden[0]}
Icon={ID}
Terminal=false
Categories=Science;Physics;Math;DataVisualization;
Keywords=fit;ajuste;regresión;regression;chi2;física;physics;laboratorio;interpolación;spline;
MimeType={MIME};
StartupNotify=true
StartupWMClass={ID}
"""


def contenido_mime() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="{MIME}">
    <comment>Sesión de ajustelab</comment>
    <comment xml:lang="es">Sesión de ajustelab</comment>
    <comment xml:lang="en">ajustelab session</comment>
    <sub-class-of type="application/json"/>
    <icon name="{ID}"/>
    <glob pattern="*.ajustelab"/>
  </mime-type>
</mime-info>
"""


def _escribir(ruta: Path, texto: str | None = None, origen: Path | None = None) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if origen is not None:
        shutil.copyfile(origen, ruta)
    else:
        ruta.write_text(texto or "", encoding="utf-8")
    ruta.chmod(0o644)
    return ruta


def _refrescar(base: Path) -> list[str]:
    """Actualiza las cachés del escritorio con las herramientas que existan.
    Ninguna es imprescindible: los escritorios también vigilan estas carpetas."""
    hicolor = base / "icons" / "hicolor"
    ordenes = [
        ["update-mime-database", str(base / "mime")],
        ["update-desktop-database", "-q", str(base / "applications")],
        ["kbuildsycoca6"],
        ["kbuildsycoca5"],
    ]
    # La caché de iconos del usuario solo se actualiza si ya existía: crearla haría
    # que GTK ignorase iconos que otras aplicaciones instalen después sin actualizarla.
    if (hicolor / "icon-theme.cache").is_file():
        ordenes[2:2] = [["gtk-update-icon-cache", "-q", "-t", "-f", str(hicolor)],
                        ["gtk4-update-icon-cache", "-q", "-t", "-f", str(hicolor)]]
    hechas = []
    for o in ordenes:
        if shutil.which(o[0]) is None:
            continue
        if o[0].startswith("gtk") and "gtk-update-icon-cache" in hechas:
            continue  # basta con una de las dos versiones
        try:
            subprocess.run(o, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=60, check=False)
            hechas.append(o[0])
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        os.utime(hicolor)  # los temas releen la carpeta cuando cambia su fecha
    except OSError:
        pass
    return hechas


def _plataforma(plataforma: str | None) -> str:
    return plataforma or ("windows" if ES_WINDOWS else "xdg")


def ruta_entrada(base: Path | None = None, plataforma: str | None = None) -> Path:
    """La entrada del menú: ``ajustelab.lnk`` en Windows, ``ajustelab.desktop`` en Linux."""
    if _plataforma(plataforma) == "windows":
        from . import windows

        return (base or windows.carpeta_programas()) / f"{ID}.lnk"
    return ruta_desktop(base)


def instalar(base: Path | None = None, orden: list[str] | None = None, refrescar: bool = True,
             plataforma: str | None = None, clases: str | None = None) -> list[Path]:
    """Instala la entrada del menú, los iconos y el tipo de fichero. Devuelve los ficheros escritos.

    ``base`` es la carpeta de datos XDG (Linux) o la del menú Inicio (Windows), y
    ``clases`` la clave del registro para la asociación (Windows; para pruebas)."""
    orden = orden or orden_lanzar()
    if _plataforma(plataforma) == "windows":
        return _instalar_windows(base, orden, clases)
    base = base or datos_usuario()
    if not (RECURSOS / "icono.svg").is_file():
        raise ErrorEscritorio(f"No se encuentran los iconos en {RECURSOS}")
    escritos = [_escribir(ruta_desktop(base), contenido_desktop(orden)),
                _escribir(base / "mime" / "packages" / f"{ID}.xml", contenido_mime())]
    hicolor = base / "icons" / "hicolor"
    escritos.append(_escribir(hicolor / "scalable" / "apps" / f"{ID}.svg", origen=RECURSOS / "icono.svg"))
    for n in TAMANOS:
        png = RECURSOS / f"icono-{n}.png"
        if png.is_file():
            escritos.append(_escribir(hicolor / f"{n}x{n}" / "apps" / f"{ID}.png", origen=png))
    if refrescar:
        _refrescar(base)
    return escritos


def _instalar_windows(carpeta: Path | None, orden: list[str], clases: str | None) -> list[Path]:
    from . import windows

    icono = RECURSOS / "icono.ico"
    if not icono.is_file():
        raise ErrorEscritorio(f"No se encuentra {icono}")
    lnk = ruta_entrada(carpeta, "windows")
    try:
        windows.crear_acceso(lnk, orden[0], subprocess.list2cmdline(orden[1:]), str(icono),
                             "Ajuste de datos experimentales con base estadística")
        windows.asociar(orden, str(icono), clases or windows.CLASES)
    except OSError as e:
        raise ErrorEscritorio(f"No se pudo crear el acceso directo o la asociación: {e}") from e
    return [lnk]


def desinstalar(base: Path | None = None, refrescar: bool = True, plataforma: str | None = None,
                clases: str | None = None) -> list[Path]:
    """Quita lo instalado por ``instalar``. Devuelve los ficheros borrados."""
    if _plataforma(plataforma) == "windows":
        from . import windows

        lnk = ruta_entrada(base, "windows")
        borrados = []
        if lnk.is_file():
            lnk.unlink()
            borrados.append(lnk)
        windows.desasociar(clases or windows.CLASES)
        return borrados
    base = base or datos_usuario()
    borrados = []
    for ruta in ficheros(base):
        if ruta.is_file() or ruta.is_symlink():
            ruta.unlink()
            borrados.append(ruta)
    if refrescar and borrados:
        _refrescar(base)
    return borrados


def lanzador_valido(ruta: Path | None = None, clases: str | None = None) -> bool:
    """¿La entrada del menú apunta a un ejecutable que existe?"""
    if ES_WINDOWS and (ruta is None or ruta.suffix == ".lnk"):
        from . import windows

        orden = windows.leer_valor(f"{clases or windows.CLASES}\\{windows.PROGID}\\shell\\open\\command")
        if not orden:
            return False
        primero = orden[1:].split('"', 1)[0] if orden.startswith('"') else orden.split(" ", 1)[0]
        return Path(primero).is_file()
    ruta = ruta or ruta_desktop()
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.search(r"^TryExec=(.+)$", texto, re.M)
    if not m:
        m = re.search(r"^Exec=(.+)$", texto, re.M)
        if not m:
            return False
        try:
            primero = shlex.split(m.group(1).replace("\\\\", "\\"))[0]
        except (ValueError, IndexError):
            return False
    else:
        primero = m.group(1).strip()
    return Path(primero).is_file()
