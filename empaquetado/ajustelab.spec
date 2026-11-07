# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller para los ejecutables independientes de ajustelab.

    pyinstaller --noconfirm --clean empaquetado/ajustelab.spec

Deja en dist/ la carpeta «ajustelab» (Windows y Linux) o «ajustelab.app» (macOS).
Los instaladores (.exe con Inno Setup, .dmg, AppImage) se hacen después: ver
empaquetado/construir.py y .github/workflows/ejecutables.yml.
"""
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

raiz = Path(SPECPATH).resolve().parent
version = re.search(r'^__version__ = "([^"]+)"', (raiz / "ajustelab" / "__init__.py").read_text(encoding="utf-8"),
                    re.M).group(1)
recursos = raiz / "ajustelab" / "gui" / "recursos"
icono = str(recursos / ("icono.ico" if sys.platform == "win32" else "icono-512.png"))

a = Analysis(
    [str(Path(SPECPATH) / "ajustelab_app.py")],
    pathex=[str(raiz)],
    datas=collect_data_files("ajustelab"),  # iconos, la imagen de «Acerca de» y la fuente Inter
    hiddenimports=[
        # Formatos de exportación (matplotlib los carga al guardar) y de lectura de hojas
        "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_agg", "matplotlib.backends.backend_pdf",
        "matplotlib.backends.backend_svg", "matplotlib.backends.backend_ps", "openpyxl", "odf", "xlrd",
    ],
    excludes=["tkinter", "matplotlib.backends.backend_tkagg", "matplotlib.backends._backend_tk",
              "matplotlib.backends.backend_gtk3agg", "matplotlib.backends.backend_gtk4agg", "gi", "IPython",
              "jupyter", "notebook", "pytest", "PyQt5", "PyQt6", "PySide2", "sphinx", "lxml", "brotli", "_brotli"],
    noarchive=False,
)

# Lo que no hace falta y solo ocupa: el tema GTK de Qt (arrastra GTK entero; la
# interfaz usa el estilo Fusion) y las traducciones de Qt a idiomas que no son el
# español ni el inglés.
_SOBRA = re.compile(r"(platformthemes[/\\]libqgtk3|libgtk-3\.|libgdk-3\.|libatk-|libatk-bridge|libatspi|"
                    r"libgdk_pixbuf|libpango|libcairo|libepoxy|translations[/\\](?!.*_(es|en)\.qm$).+\.qm$)")
a.binaries = [b for b in a.binaries if not _SOBRA.search(b[0])]
a.datas = [d for d in a.datas if not _SOBRA.search(d[0])]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ajustelab",
    console=False,  # sin ventana de consola (--version y --diagnostico se enganchan a la de quien lo lanza)
    icon=icono,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ajustelab", strip=False, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ajustelab.app",
        icon=icono,
        bundle_identifier="io.github.wetzap.ajustelab",
        version=version,
        info_plist={
            "CFBundleName": "ajustelab",
            "CFBundleDisplayName": "ajustelab",
            "CFBundleShortVersionString": version,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # sigue el modo oscuro del sistema
            "LSApplicationCategoryType": "public.app-category.education",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Sesión de ajustelab",
                "CFBundleTypeExtensions": ["ajustelab"],
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
            }, {
                "CFBundleTypeName": "Datos",
                "CFBundleTypeExtensions": ["csv", "tsv", "txt", "dat", "xlsx", "xls", "ods", "json"],
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
            }],
        },
    )
