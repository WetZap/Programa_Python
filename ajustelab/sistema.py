"""Información del sistema para diagnosticar e instalar ajustelab en Linux.

Este módulo **no importa Qt**: tiene que funcionar justo cuando la interfaz no
puede arrancar. Sirve a ``ajustelab --diagnostico``, al aviso que se muestra si
faltan bibliotecas al abrir la aplicación y al instalador ``instalar.sh``, que le
pregunta qué paquetes del sistema hay que instalar en cada distribución.
"""
from __future__ import annotations

import ctypes
import os
import platform
import shlex
import shutil
import sys
from pathlib import Path

# --- distribución -------------------------------------------------------------
# Cada familia se reconoce por ID o ID_LIKE de /etc/os-release.
_FAMILIAS = {
    "arch": {"arch", "archarm", "manjaro", "manjaro-arm", "endeavouros", "garuda", "cachyos", "artix", "arcolinux"},
    "debian": {"debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin", "kali", "raspbian", "neon",
               "deepin", "mx", "pureos", "tuxedo", "kubuntu", "xubuntu", "lubuntu"},
    "fedora": {"fedora", "rhel", "centos", "rocky", "almalinux", "nobara", "ol", "ultramarine", "bazzite"},
    "suse": {"opensuse", "opensuse-tumbleweed", "opensuse-leap", "opensuse-slowroll", "suse", "sles", "sled"},
    "void": {"void"},
    "gentoo": {"gentoo", "funtoo"},
    "nixos": {"nixos"},
    "alpine": {"alpine", "postmarketos"},
}

# Orden para instalar paquetes; {paquetes} se sustituye. Gentoo y NixOS no se
# automatizan (compilación / configuración declarativa).
ORDEN_INSTALAR = {
    "arch": "pacman -S --needed {paquetes}",
    "debian": "apt install {paquetes}",
    "fedora": "dnf install {paquetes}",
    "suse": "zypper install {paquetes}",
    "void": "xbps-install -S {paquetes}",
    "gentoo": "emerge --ask --noreplace {paquetes}",
}

# Bibliotecas que el Qt de los paquetes de PyPI (PySide6) toma del sistema.
# (soname, uso, {familia: paquete})   uso ∈ {"base", "x11", "wayland"}
BIBLIOTECAS_QT: list[tuple[str, str, dict[str, str]]] = [
    ("libEGL.so.1", "base", {"debian": "libegl1", "arch": "libglvnd", "fedora": "libglvnd-egl", "suse": "libglvnd",
                             "void": "libglvnd", "gentoo": "media-libs/libglvnd"}),
    ("libGL.so.1", "base", {"debian": "libgl1", "arch": "libglvnd", "fedora": "libglvnd-glx", "suse": "libglvnd",
                            "void": "libglvnd", "gentoo": "media-libs/libglvnd"}),
    ("libfontconfig.so.1", "base", {"debian": "libfontconfig1", "arch": "fontconfig", "fedora": "fontconfig",
                                    "suse": "libfontconfig1", "void": "fontconfig", "gentoo": "media-libs/fontconfig"}),
    ("libxkbcommon.so.0", "base", {"debian": "libxkbcommon0", "arch": "libxkbcommon", "fedora": "libxkbcommon",
                                   "suse": "libxkbcommon0", "void": "libxkbcommon", "gentoo": "x11-libs/libxkbcommon"}),
    ("libdbus-1.so.3", "base", {"debian": "libdbus-1-3", "arch": "dbus", "fedora": "dbus-libs", "suse": "libdbus-1-3",
                                "void": "dbus-libs", "gentoo": "sys-apps/dbus"}),
    ("libglib-2.0.so.0", "base", {"debian": "libglib2.0-0", "arch": "glib2", "fedora": "glib2",
                                  "suse": "libglib-2_0-0", "void": "glib", "gentoo": "dev-libs/glib"}),
    # openSUSE separa gthread de glib; en las demás viene en el mismo paquete
    ("libgthread-2.0.so.0", "base", {"debian": "libglib2.0-0", "arch": "glib2", "fedora": "glib2",
                                     "suse": "libgthread-2_0-0", "void": "glib", "gentoo": "dev-libs/glib"}),
    ("libX11.so.6", "base", {"debian": "libx11-6", "arch": "libx11", "fedora": "libX11", "suse": "libX11-6",
                             "void": "libX11", "gentoo": "x11-libs/libX11"}),
    ("libfreetype.so.6", "base", {"debian": "libfreetype6", "arch": "freetype2", "fedora": "freetype",
                                  "suse": "libfreetype6", "void": "freetype", "gentoo": "media-libs/freetype"}),
    # X11 (y XWayland): «xcb» es el plugin de Qt para X11
    ("libxcb-cursor.so.0", "x11", {"debian": "libxcb-cursor0", "arch": "xcb-util-cursor", "fedora": "xcb-util-cursor",
                                   "suse": "libxcb-cursor0", "void": "xcb-util-cursor",
                                   "gentoo": "x11-libs/xcb-util-cursor"}),
    ("libxkbcommon-x11.so.0", "x11", {"debian": "libxkbcommon-x11-0", "arch": "libxkbcommon-x11",
                                      "fedora": "libxkbcommon-x11", "suse": "libxkbcommon-x11-0",
                                      "void": "libxkbcommon-x11", "gentoo": "x11-libs/libxkbcommon"}),
    ("libxcb-icccm.so.4", "x11", {"debian": "libxcb-icccm4", "arch": "xcb-util-wm", "fedora": "xcb-util-wm",
                                  "suse": "libxcb-icccm4", "void": "xcb-util-wm", "gentoo": "x11-libs/xcb-util-wm"}),
    ("libxcb-keysyms.so.1", "x11", {"debian": "libxcb-keysyms1", "arch": "xcb-util-keysyms",
                                    "fedora": "xcb-util-keysyms", "suse": "libxcb-keysyms1",
                                    "void": "xcb-util-keysyms", "gentoo": "x11-libs/xcb-util-keysyms"}),
    ("libxcb-render-util.so.0", "x11", {"debian": "libxcb-render-util0", "arch": "xcb-util-renderutil",
                                        "fedora": "xcb-util-renderutil", "suse": "libxcb-render-util0",
                                        "void": "xcb-util-renderutil", "gentoo": "x11-libs/xcb-util-renderutil"}),
    ("libxcb-image.so.0", "x11", {"debian": "libxcb-image0", "arch": "xcb-util-image", "fedora": "xcb-util-image",
                                  "suse": "libxcb-image0", "void": "xcb-util-image",
                                  "gentoo": "x11-libs/xcb-util-image"}),
    ("libxcb-shape.so.0", "x11", {"debian": "libxcb-shape0", "arch": "libxcb", "fedora": "libxcb",
                                  "suse": "libxcb-shape0", "void": "libxcb", "gentoo": "x11-libs/libxcb"}),
    ("libX11-xcb.so.1", "x11", {"debian": "libx11-xcb1", "arch": "libx11", "fedora": "libX11-xcb",
                                "suse": "libX11-xcb1", "void": "libX11", "gentoo": "x11-libs/libX11"}),
    ("libxcb-util.so.1", "x11", {"debian": "libxcb-util1", "arch": "xcb-util", "fedora": "xcb-util",
                                 "suse": "libxcb-util1", "void": "xcb-util", "gentoo": "x11-libs/xcb-util"}),
    # Las demás partes de libxcb: un paquete en Arch/Fedora/Void, uno por biblioteca en Debian/openSUSE
    *((f"libxcb{sufijo}.so.{v}", "x11", {"debian": f"libxcb{sufijo}{v}", "suse": f"libxcb{sufijo}{v}",
                                         "arch": "libxcb", "fedora": "libxcb", "void": "libxcb",
                                         "gentoo": "x11-libs/libxcb"})
      for sufijo, v in (("", 1), ("-randr", 0), ("-render", 0), ("-shm", 0), ("-sync", 1), ("-xfixes", 0),
                        ("-xkb", 1))),
    # Wayland
    ("libwayland-client.so.0", "wayland", {"debian": "libwayland-client0", "arch": "wayland",
                                           "fedora": "libwayland-client", "suse": "libwayland-client0",
                                           "void": "wayland", "gentoo": "dev-libs/wayland"}),
    ("libwayland-cursor.so.0", "wayland", {"debian": "libwayland-cursor0", "arch": "wayland",
                                           "fedora": "libwayland-cursor", "suse": "libwayland-cursor0",
                                           "void": "wayland", "gentoo": "dev-libs/wayland"}),
    ("libwayland-egl.so.1", "wayland", {"debian": "libwayland-egl1", "arch": "wayland",
                                        "fedora": "libwayland-egl", "suse": "libwayland-egl1",
                                        "void": "wayland", "gentoo": "dev-libs/wayland"}),
]


def es_linux() -> bool:
    return sys.platform.startswith("linux")


def os_release(rutas: tuple[str, ...] = ("/etc/os-release", "/usr/lib/os-release")) -> dict[str, str]:
    """Contenido de os-release como diccionario (vacío si no existe)."""
    for ruta in rutas:
        try:
            texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        info = {}
        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            try:
                partes = shlex.split(valor)
            except ValueError:
                partes = [valor.strip("\"'")]
            info[clave.strip()] = partes[0] if partes else ""
        return info
    return {}


def familia(info: dict[str, str] | None = None) -> str | None:
    """Familia de la distribución: arch, debian, fedora, suse, void, gentoo, nixos, alpine o None."""
    info = os_release() if info is None else info
    ids = [info.get("ID", "").lower()] + info.get("ID_LIKE", "").lower().split()
    for i in ids:
        for fam, nombres in _FAMILIAS.items():
            if i in nombres or (fam == "suse" and i.startswith("opensuse")):
                return fam
    return None


def nombre_distro(info: dict[str, str] | None = None) -> str:
    info = os_release() if info is None else info
    return info.get("PRETTY_NAME") or info.get("NAME") or platform.system()


# --- sesión gráfica y bibliotecas ---------------------------------------------------
def sesion(entorno: dict[str, str] | None = None) -> str:
    """«wayland», «x11» o «ninguna» (consola, SSH sin -X, contenedor...)."""
    e = os.environ if entorno is None else entorno
    if e.get("WAYLAND_DISPLAY") or e.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return "wayland"
    if e.get("DISPLAY"):
        return "x11"
    return "ninguna"


def _se_carga(soname: str) -> bool:
    try:
        ctypes.CDLL(soname)
        return True
    except OSError:
        return False


def bibliotecas_que_faltan(usos: tuple[str, ...] = ("base", "x11", "wayland"),
                           cargar=_se_carga) -> list[tuple[str, str, dict[str, str]]]:
    """Bibliotecas de ``BIBLIOTECAS_QT`` con uso en ``usos`` que no se pueden cargar."""
    return [b for b in BIBLIOTECAS_QT if b[1] in usos and not cargar(b[0])]


def usos_necesarios(entorno: dict[str, str] | None = None) -> tuple[str, ...]:
    """Qué bibliotecas hacen falta para abrir la ventana en la sesión actual.

    En Wayland, Qt usa su plugin nativo y solo recurre a X11 (XWayland) si falla;
    si ``QT_QPA_PLATFORM`` está fijado, manda ese."""
    e = os.environ if entorno is None else entorno
    plataforma = e.get("QT_QPA_PLATFORM", "").split(";")[0].strip().lower()
    if plataforma in ("offscreen", "minimal", "vnc", "eglfs", "linuxfb"):
        return ("base",)
    if plataforma == "xcb":
        return ("base", "x11")
    if plataforma.startswith("wayland") or sesion(e) == "wayland":
        return ("base", "wayland")
    return ("base", "x11")


def paquetes(faltan, fam: str | None) -> list[str]:
    """Paquetes de la familia ``fam`` que aportan las bibliotecas ``faltan`` (sin repetir)."""
    salida: list[str] = []
    for _, _, por_familia in faltan:
        p = por_familia.get(fam or "")
        if p and p not in salida:
            salida.append(p)
    return salida


def orden(fam: str | None, lista: list[str], con_sudo: bool = True) -> str | None:
    """Orden de terminal que instala ``lista`` en la familia ``fam`` (None si no se sabe)."""
    if not lista or fam not in ORDEN_INSTALAR:
        return None
    texto = ORDEN_INSTALAR[fam].format(paquetes=" ".join(lista))
    return ("sudo " + texto) if con_sudo else texto


def aviso_arranque(entorno: dict[str, str] | None = None, cargar=_se_carga) -> str | None:
    """Mensaje si se prevé que la ventana no pueda abrirse, o None.

    Solo se comprueba lo que Qt necesita en *esta* sesión para no dar falsas alarmas."""
    if not es_linux() and entorno is None:
        return None
    e = os.environ if entorno is None else entorno
    usos = usos_necesarios(e)
    if usos == ("base",):
        return None
    if sesion(e) == "ninguna" and not e.get("QT_QPA_PLATFORM"):
        return ("No hay sesión gráfica (DISPLAY y WAYLAND_DISPLAY están vacías): ajustelab necesita "
                "un escritorio. Por SSH, usa «ssh -X» o la versión de terminal, ajustelab-cli.")
    faltan = bibliotecas_que_faltan(usos, cargar)
    if not faltan:
        return None
    nombres = ", ".join(b[0] for b in faltan)
    texto = f"Faltan bibliotecas del sistema que necesita Qt: {nombres}."
    o = orden(familia(), paquetes(faltan, familia()))
    if o:
        texto += f"\nInstálalas con:\n    {o}"
    else:
        texto += "\nInstala los paquetes de tu distribución que las contienen."
    if "x11" in usos and any(b[1] == "x11" for b in faltan) and sesion(e) == "x11":
        texto += '\n(Es el error «Could not load the Qt platform plugin "xcb"».)'
    return texto


# --- diagnóstico completo -----------------------------------------------------
def _version_qt() -> tuple[str, str | None]:
    """(texto, error): versión de PySide6/Qt o el error al cargarlo."""
    try:
        import PySide6
        from PySide6 import QtCore
    except Exception as e:  # noqa: BLE001 — se informa de cualquier fallo de carga
        return "no se puede cargar", f"{type(e).__name__}: {e}"
    return f"{PySide6.__version__} (Qt {QtCore.qVersion()})", None


def _en_path(directorio: Path) -> bool:
    return any(Path(p).expanduser() == directorio for p in os.environ.get("PATH", "").split(os.pathsep) if p)


def diagnostico() -> tuple[str, int]:
    """Informe de texto y código de salida (0 = todo bien, 1 = hay problemas)."""
    from . import __version__
    from . import escritorio

    lineas = [f"ajustelab {__version__} — diagnóstico", ""]
    problemas: list[str] = []
    notas: list[str] = []
    soluciones: list[str] = []

    def fila(nombre, valor):
        lineas.append(f"  {nombre:<11} {valor}")

    fila("Python", f"{platform.python_version()} ({sys.executable})")
    qt, error_qt = _version_qt()
    fila("PySide6", qt)
    if error_qt:
        problemas.append(f"PySide6 no carga: {error_qt}")

    if es_linux():
        info = os_release()
        fam = familia(info)
        fila("Sistema", f"{nombre_distro(info)} · familia {fam or 'desconocida'} · {platform.machine()}")
        libc = platform.libc_ver()[0]
        if fam == "alpine" or (libc and libc != "glibc"):
            problemas.append("La distribución usa musl en lugar de glibc: PySide6 no publica paquetes para ella.")
            soluciones.append("Usa una distribución con glibc, o los paquetes de Qt/PySide6 de tu distribución.")
        if fam == "nixos":
            problemas.append("En NixOS los paquetes de PyPI con bibliotecas nativas no encuentran las del sistema.")
            soluciones.append("Usa python3Packages.pyside6 de nixpkgs, o activa programs.nix-ld.")
        e = os.environ
        fila("Sesión", f"{sesion()} · escritorio {e.get('XDG_CURRENT_DESKTOP') or 'desconocido'} · "
                       f"QT_QPA_PLATFORM={e.get('QT_QPA_PLATFORM') or '(sin fijar)'}")

        faltan_todas = bibliotecas_que_faltan()
        hay_sesion = sesion() != "ninguna" or bool(e.get("QT_QPA_PLATFORM"))
        criticas = [b for b in faltan_todas if b[1] in usos_necesarios()] if hay_sesion else []
        if not hay_sesion:
            notas.append("No hay sesión gráfica: desde aquí solo funciona ajustelab-cli (por SSH, usa «ssh -X»).")
        if not faltan_todas:
            fila("Bibliotecas", "todas presentes (X11 y Wayland)")
        else:
            fila("Bibliotecas", "faltan " + ", ".join(f"{b[0]} ({b[1]})" for b in faltan_todas))
            o = orden(fam, paquetes(faltan_todas, fam))
            if criticas:
                problemas.append("Faltan bibliotecas necesarias para abrir la ventana en esta sesión.")
            else:
                notas.append("Faltan bibliotecas que solo se usan en otro tipo de sesión (X11/Wayland).")
            soluciones.append(o or "Instala los paquetes de tu distribución que contienen esas bibliotecas.")

        ruta_menu = escritorio.ruta_desktop()
        if ruta_menu.is_file():
            ok = escritorio.lanzador_valido(ruta_menu)
            fila("Menú", f"instalado ({ruta_menu})" + ("" if ok else " — apunta a un ajustelab que ya no existe"))
            if not ok:
                problemas.append("La entrada del menú apunta a una instalación que ya no existe.")
                soluciones.append("ajustelab --instalar-escritorio")
        else:
            fila("Menú", "no instalado (ajustelab --instalar-escritorio)")

        local_bin = Path.home() / ".local" / "bin"
        en_path = _en_path(local_bin)
        fila("PATH", f"{local_bin} {'está' if en_path else 'NO está'} en el PATH")
        donde = shutil.which("ajustelab")
        fila("Comando", donde or "«ajustelab» no se encuentra en el PATH")
    elif sys.platform == "win32":
        fila("Sistema", f"Windows {platform.release()} (versión {platform.version()}) · {platform.machine()}")
        ruta_menu = escritorio.ruta_entrada()
        if ruta_menu.is_file():
            ok = escritorio.lanzador_valido(ruta_menu)
            fila("Menú Inicio", f"instalado ({ruta_menu})" + ("" if ok else " — apunta a un ajustelab que ya no existe"))
            if not ok:
                problemas.append("El acceso directo apunta a una instalación que ya no existe.")
                soluciones.append("ajustelab --instalar-escritorio  (o vuelve a ejecutar instalar.ps1)")
        else:
            fila("Menú Inicio", "no instalado (ajustelab --instalar-escritorio)")
        donde = shutil.which("ajustelab")
        fila("Comando", donde or "«ajustelab» no está en el PATH (abre una terminal nueva tras instalar)")
    else:
        fila("Sistema", f"{platform.system()} {platform.release()} · {platform.machine()}")

    lineas.append("")
    if problemas:
        lineas.append("Problemas:")
        lineas += [f"  ✗ {p}" for p in problemas]
    else:
        lineas.append("✓ No se detectan problemas.")
    lineas += [f"  · {n}" for n in notas]
    if soluciones:
        lineas.append("Solución:" if problemas else "Recomendado:")
        lineas += [f"  {s}" for s in dict.fromkeys(soluciones)]
    return "\n".join(lineas), (1 if problemas else 0)
