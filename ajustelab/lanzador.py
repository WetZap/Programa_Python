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
  ajustelab --instalar-escritorio    añade ajustelab al menú de aplicaciones (Linux)

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
                   help="Linux: añade ajustelab al menú de aplicaciones, con icono y doble clic en .ajustelab")
    g.add_argument("--desinstalar-escritorio", action="store_true",
                   help="Linux: quita ajustelab del menú de aplicaciones")
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

    if not sistema.es_linux() and not sys.platform.startswith(("freebsd", "openbsd", "netbsd")):
        print("La integración con el menú es para escritorios Linux/BSD (freedesktop).\n"
              "En Windows crea un acceso directo a «ajustelab.exe» de la carpeta Scripts del entorno; en macOS, "
              "ejecuta «ajustelab» desde la Terminal.", file=sys.stderr)
        return 2
    try:
        if instalar:
            escritos = escritorio.instalar()
            print(f"✓ ajustelab añadido al menú de aplicaciones ({escritos[0]}).")
            print(f"  Abre con: {' '.join(escritorio.orden_lanzar())}")
            print("  Las sesiones .ajustelab se abren con doble clic. Si el icono no aparece, cierra y vuelve "
                  "a abrir la sesión del escritorio.")
        else:
            borrados = escritorio.desinstalar()
            print("✓ ajustelab quitado del menú." if borrados else "No había nada que quitar.")
    except (OSError, escritorio.ErrorEscritorio) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


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
