"""Construye el ejecutable independiente de ajustelab y su paquete para este sistema.

    python empaquetado/construir.py            # ejecutable + paquete
    python empaquetado/construir.py --probar   # además, abre el ejecutable sin pantalla y hace un ajuste

Resultado en dist/:
    Linux    ajustelab-<versión>-linux-x86_64.AppImage
    Windows  ajustelab-<versión>-windows-x64-instalador.exe (Inno Setup) y …-portable.zip
    macOS    ajustelab-<versión>-macos-<arm64|x86_64>.dmg

Necesita: pyinstaller y pillow; en Windows, Inno Setup (iscc); en Linux, se
descarga appimagetool si no está. Lo usa .github/workflows/ejecutables.yml.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EMPAQUETADO = RAIZ / "empaquetado"
DIST = RAIZ / "dist"
APPIMAGETOOL = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"


def version() -> str:
    texto = (RAIZ / "ajustelab" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'^__version__ = "([^"]+)"', texto, re.M).group(1)


def ejecutar(orden: list, **kw) -> None:
    print("$", " ".join(str(a) for a in orden), flush=True)
    subprocess.run([str(a) for a in orden], check=True, **kw)


def pyinstaller() -> None:
    ejecutar([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
              "--distpath", DIST, "--workpath", RAIZ / "build", EMPAQUETADO / "ajustelab.spec"])


def ejecutable() -> Path:
    if sys.platform == "darwin":
        return DIST / "ajustelab.app" / "Contents" / "MacOS" / "ajustelab"
    return DIST / "ajustelab" / ("ajustelab.exe" if sys.platform == "win32" else "ajustelab")


def probar(orden: list | None = None) -> None:
    """Abre la interfaz sin pantalla, carga un ejemplo, ajusta y comprueba el código de salida."""
    entorno = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "APPIMAGE_EXTRACT_AND_RUN": "1"}
    orden = orden or [ejecutable()]
    r = subprocess.run([str(a) for a in orden] + ["--probar-interfaz"], env=entorno, timeout=300,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout, r.stderr, sep="\n")
    if r.returncode != 0:
        raise SystemExit(f"La prueba del ejecutable ha fallado (código {r.returncode}).")
    print("✓ El ejecutable funciona.")


# --- Linux: AppImage ------------------------------------------------------------
def appimage(v: str) -> Path:
    appdir = RAIZ / "build" / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    destino = appdir / "usr" / "lib" / "ajustelab"
    shutil.copytree(DIST / "ajustelab", destino, symlinks=True)
    apprun = appdir / "AppRun"
    apprun.write_text('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
                      'exec "$HERE/usr/lib/ajustelab/ajustelab" "$@"\n', encoding="utf-8")
    apprun.chmod(apprun.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    sys.path.insert(0, str(RAIZ))
    from ajustelab import escritorio

    (appdir / "ajustelab.desktop").write_text(escritorio.contenido_desktop(["ajustelab"]).replace(
        "TryExec=ajustelab\n", ""), encoding="utf-8")
    shutil.copy(RAIZ / "ajustelab" / "gui" / "recursos" / "icono-256.png", appdir / "ajustelab.png")
    mime = appdir / "usr" / "share" / "mime" / "packages"
    mime.mkdir(parents=True)
    (mime / "ajustelab.xml").write_text(escritorio.contenido_mime(), encoding="utf-8")
    herramienta = shutil.which("appimagetool") or str(RAIZ / "build" / "appimagetool")
    if not Path(herramienta).exists():
        print("Descargando appimagetool…", flush=True)
        urllib.request.urlretrieve(APPIMAGETOOL, herramienta)
        Path(herramienta).chmod(0o755)
    salida = DIST / f"ajustelab-{v}-linux-x86_64.AppImage"
    ejecutar([herramienta, "--no-appstream", appdir, salida],
             env={**os.environ, "ARCH": "x86_64", "APPIMAGE_EXTRACT_AND_RUN": "1"})
    return salida


# --- Windows: instalador (Inno Setup) y zip portable -------------------------------
def windows(v: str) -> list[Path]:
    salidas = []
    portable = DIST / f"ajustelab-{v}-windows-x64-portable.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in (DIST / "ajustelab").rglob("*"):
            z.write(f, Path("ajustelab") / f.relative_to(DIST / "ajustelab"))
    salidas.append(portable)
    iscc = shutil.which("iscc") or next((str(p) for p in (
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe") if p.is_file()), None)
    if iscc is None:
        print("⚠ No está Inno Setup (iscc): solo se hace el zip portable.")
        return salidas
    ejecutar([iscc, f"/DVersion={v}", f"/DOrigen={DIST / 'ajustelab'}", f"/DSalida={DIST}",
              f"/DIcono={RAIZ / 'ajustelab' / 'gui' / 'recursos' / 'icono.ico'}", EMPAQUETADO / "ajustelab.iss"])
    salidas.append(DIST / f"ajustelab-{v}-windows-x64-instalador.exe")
    return salidas


# --- macOS: imagen de disco ---------------------------------------------------------
def dmg(v: str) -> Path:
    arq = "arm64" if platform.machine() in ("arm64", "aarch64") else "x86_64"
    carpeta = RAIZ / "build" / "dmg"
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    # Firma ad hoc del paquete entero (sin certificado de Apple): sin ella, macOS en
    # Apple Silicon no lo abre; con ella, basta «Abrir igualmente» la primera vez.
    ejecutar(["codesign", "--force", "--deep", "--sign", "-", DIST / "ajustelab.app"])
    ejecutar(["codesign", "--verify", "--deep", "--strict", DIST / "ajustelab.app"])
    ejecutar(["ditto", DIST / "ajustelab.app", carpeta / "ajustelab.app"])
    (carpeta / "Aplicaciones").symlink_to("/Applications")
    salida = DIST / f"ajustelab-{v}-macos-{arq}.dmg"
    salida.unlink(missing_ok=True)
    ejecutar(["hdiutil", "create", "-volname", f"ajustelab {v}", "-srcfolder", carpeta, "-ov", "-format", "UDZO",
              salida])
    return salida


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--probar", action="store_true", help="prueba el ejecutable y el paquete sin pantalla")
    p.add_argument("--sin-paquete", action="store_true", help="solo el ejecutable (sin AppImage/instalador/dmg)")
    args = p.parse_args()
    v = version()
    pyinstaller()
    if args.probar:
        probar()
    if args.sin_paquete:
        return 0
    if sys.platform.startswith("linux"):
        salidas = [appimage(v)]
        if args.probar:
            probar([salidas[0]])
    elif sys.platform == "win32":
        salidas = windows(v)
    elif sys.platform == "darwin":
        salidas = [dmg(v)]
    else:
        raise SystemExit(f"Sistema no previsto: {sys.platform}")
    for s in salidas:
        print(f"→ {s.name}  ({s.stat().st_size / 2**20:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
