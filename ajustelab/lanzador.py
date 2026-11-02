"""Orden ``ajustelab``: abre la interfaz o atiende las opciones de sistema.

Las opciones de sistema (diagnóstico, integración con el escritorio) no cargan
la interfaz, así que funcionan aunque Qt no pueda arrancar.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from . import __version__

# Opciones propias de Qt (un guion) que llevan valor: se pasan tal cual a Qt.
_QT_CON_VALOR = {"-platform", "-platformpluginpath", "-platformtheme", "-plugin", "-qwindowgeometry",
                 "-qwindowtitle", "-qwindowicon", "-style", "-stylesheet", "-name", "-display", "-geometry",
                 "-session", "-title", "-qmljsdebugger"}

EPILOGO = """\
ejemplos:
  ajustelab                          abre la ventana
  ajustelab medidas.csv              abre la ventana con un fichero
  ajustelab practica.ajustelab       recupera una sesión guardada
  ajustelab --diagnostico            comprueba Python, Qt y las bibliotecas del sistema
  ajustelab --instalar-escritorio    añade ajustelab al menú de aplicaciones o al menú Inicio

  QT_QPA_PLATFORM=xcb ajustelab      fuerza X11 (XWayland) si Wayland da problemas
  ajustelab-cli --help               versión de terminal, sin ventana
"""


def separar_argumentos(args: list[str]) -> tuple[list[str], list[str]]:
    """Separa las opciones de Qt (``-platform xcb``, ``-style Fusion``…) de las nuestras."""
    propios, qt = [], []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and not a.startswith("--") and a not in ("-", "-h", "-V"):
            qt.append(a)
            if a in _QT_CON_VALOR and "=" not in a and i + 1 < len(args):
                qt.append(args[i + 1])
                i += 1
        else:
            propios.append(a)
        i += 1
    return propios, qt


def _analizador() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ajustelab", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOGO, add_help=False,
        description="Ajuste de datos experimentales con base estadística (interfaz gráfica).")
    p._positionals.title = "argumentos"
    p._optionals.title = "opciones"
    p.add_argument("fichero", nargs="?", help="datos (csv, dat, txt, xlsx…) o sesión .ajustelab que abrir")
    p.add_argument("-h", "--help", action="help", help="muestra esta ayuda y sale")
    p.add_argument("-V", "--version", action="version", version=f"ajustelab {__version__}",
                   help="muestra la versión y sale")
    g = p.add_argument_group("sistema")
    g.add_argument("--diagnostico", action="store_true",
                   help="comprueba Python, PySide6/Qt, la sesión gráfica y las bibliotecas del sistema")
    g.add_argument("--probar-interfaz", action="store_true",
                   help="crea la ventana, hace un ajuste de ejemplo y sale (comprueba la instalación)")
    g.add_argument("--instalar-escritorio", action="store_true",
                   help="añade ajustelab al menú de aplicaciones (Linux) o al menú Inicio (Windows), con icono "
                        "y doble clic en las sesiones .ajustelab")
    g.add_argument("--desinstalar-escritorio", action="store_true",
                   help="quita lo que añade --instalar-escritorio")
    g.add_argument("--paquetes-sistema", action="store_true", help=argparse.SUPPRESS)  # lo usa instalar.sh
    return p


def _avisar(mensaje: str) -> None:
    """Muestra el aviso en la terminal y, si se lanzó desde el menú (sin terminal),
    como notificación del escritorio para que el fallo no sea silencioso."""
    print(f"ajustelab: {mensaje}", file=sys.stderr)
    if sys.stderr is not None and not sys.stderr.isatty() and shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "-a", "ajustelab", "-i", "dialog-warning",
                              "ajustelab no puede abrir la ventana", mensaje],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def _escritorio(instalar: bool) -> int:
    from . import escritorio, sistema

    if sys.platform == "darwin":
        print("En macOS, ejecuta «ajustelab» desde la Terminal (la integración con el Dock aún no existe).",
              file=sys.stderr)
        return 2
    if not (escritorio.ES_WINDOWS or sistema.es_linux() or sys.platform.startswith(("freebsd", "openbsd", "netbsd"))):
        print("Este sistema no tiene un menú de aplicaciones compatible.", file=sys.stderr)
        return 2
    menu = "menú Inicio" if escritorio.ES_WINDOWS else "menú de aplicaciones"
    try:
        if instalar:
            escritos = escritorio.instalar()
            print(f"✓ ajustelab añadido al {menu} ({escritos[0]}).")
            print(f"  Abre con: {' '.join(escritorio.orden_lanzar())}")
            if escritorio.ES_WINDOWS:
                print("  Las sesiones .ajustelab se abren con doble clic.")
            else:
                print("  Las sesiones .ajustelab se abren con doble clic. Si el icono no aparece, cierra y vuelve "
                      "a abrir la sesión del escritorio.")
        else:
            borrados = escritorio.desinstalar()
            print(f"✓ ajustelab quitado del {menu}." if borrados else "No había nada que quitar.")
    except (OSError, escritorio.ErrorEscritorio) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


def _pid_padre(pid: int) -> int | None:
    """PID del padre de ``pid`` en Windows (instantánea de procesos de toolhelp)."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    instantanea = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not instantanea or instantanea == wintypes.HANDLE(-1).value:
        return None
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(instantanea, ctypes.byref(e))
        while ok:
            if e.th32ProcessID == pid:
                return int(e.th32ParentProcessID)
            ok = k32.Process32NextW(instantanea, ctypes.byref(e))
    finally:
        k32.CloseHandle(instantanea)
    return None


def _consola_windows() -> None:
    """En Windows, «ajustelab.exe» es un programa de ventana sin consola: lo que se
    imprima con --version, --help o --diagnostico se perdería. Se engancha a la
    consola de la terminal que lo lanzó (la del padre o, si el padre es el
    lanzador de pip, la del abuelo)."""
    if os.name != "nt" or (sys.stdout is not None and sys.stderr is not None):
        return
    import ctypes

    k32 = ctypes.windll.kernel32
    if not k32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
        abuelo = _pid_padre(os.getppid())
        if not abuelo or not k32.AttachConsole(abuelo):
            return
    try:
        consola = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115 — vive lo que el proceso
    except OSError:
        return
    sys.stdout = sys.stderr = consola
    print()  # la terminal ya ha mostrado el prompt


def _paquetes_sistema() -> int:
    """Imprime en una línea los paquetes que faltan en esta distribución (para
    instalar.sh). Sin salida si no falta nada o la distribución no se reconoce."""
    from . import sistema

    if not sistema.es_linux():
        return 0
    fam = sistema.familia()
    lista = sistema.paquetes(sistema.bibliotecas_que_faltan(), fam)
    if lista:
        print(" ".join(lista))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    propios, qt = separar_argumentos(argv[1:])
    if any(a.startswith("-") for a in propios):
        _consola_windows()
    args = _analizador().parse_args(propios)

    if args.diagnostico:
        from . import sistema

        texto, codigo = sistema.diagnostico()
        print(texto)
        return codigo
    if args.paquetes_sistema:
        return _paquetes_sistema()
    if args.instalar_escritorio or args.desinstalar_escritorio:
        return _escritorio(args.instalar_escritorio)

    os.environ.setdefault("RESOURCE_NAME", "ajustelab")  # WM_CLASS en X11: agrupa la ventana con su icono
    from . import sistema

    aviso = sistema.aviso_arranque()
    if aviso:
        _avisar(aviso)  # se intenta abrir igualmente: el aviso puede ser una falsa alarma
    if args.probar_interfaz:
        from .gui.app import probar

        return probar([argv[0], *qt])
    from .gui.app import main as abrir

    return abrir([argv[0], *qt], fichero=args.fichero)


if __name__ == "__main__":
    sys.exit(main())
