"""Integración con el escritorio de Windows 10/11, solo con la biblioteca estándar.

* Acceso directo en el menú Inicio (``.lnk``) con el icono de ajustelab y el mismo
  identificador de aplicación (AppUserModelID) que el proceso. Así la ventana se
  agrupa con su acceso directo en la barra de tareas y «Anclar» funciona bien.
* Asociación de ``.ajustelab`` con icono propio: las sesiones se abren con doble
  clic. Se registra en ``HKEY_CURRENT_USER``, sin permisos de administrador.

El acceso directo se crea con COM (IShellLinkW + IPropertyStore) por ``ctypes``,
sin pywin32 ni PowerShell. Este módulo solo se importa en Windows.
"""
from __future__ import annotations

import ctypes
import os
import winreg
from ctypes import POINTER, byref, c_void_p, c_wchar_p, wintypes
from pathlib import Path

APP_ID = "WetZap.ajustelab"
PROGID = "WetZap.ajustelab.sesion"
EXTENSION = ".ajustelab"
CLASES = r"Software\Classes"


# --- COM mínimo -------------------------------------------------------------------
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    # vt + 3 reservados + unión de 16 bytes (en 64 bits: 24 bytes en total)
    _fields_ = [("vt", wintypes.USHORT), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                ("pwszVal", c_wchar_p), ("relleno", c_void_p)]


_ole32 = ctypes.OleDLL("ole32")
_ole32.CLSIDFromString.argtypes = [c_wchar_p, POINTER(GUID)]
_ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, wintypes.DWORD, POINTER(GUID), POINTER(c_void_p)]
_ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
_ole32.CoInitializeEx.restype = ctypes.c_long  # S_FALSE / RPC_E_CHANGED_MODE no son errores aquí


def _guid(texto: str) -> GUID:
    g = GUID()
    _ole32.CLSIDFromString(texto, byref(g))
    return g


CLSID_SHELLLINK = "{00021401-0000-0000-C000-000000000046}"
IID_ISHELLLINKW = "{000214F9-0000-0000-C000-000000000046}"
IID_IPERSISTFILE = "{0000010b-0000-0000-C000-000000000046}"
IID_IPROPERTYSTORE = "{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}"
PKEY_APPUSERMODEL_ID = ("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}", 5)
VT_LPWSTR = 31


class _Interfaz:
    """Puntero a una interfaz COM; los métodos se llaman por su posición en la vtable."""

    def __init__(self, puntero: c_void_p):
        self.p = puntero

    def llamar(self, indice: int, *args_y_tipos):
        tipos = [t for _, t in args_y_tipos]
        valores = [v for v, _ in args_y_tipos]
        vtabla = ctypes.cast(self.p, POINTER(POINTER(c_void_p))).contents
        prototipo = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *tipos)
        return prototipo(vtabla[indice])(self.p, *valores)

    def consultar(self, iid: str) -> "_Interfaz":
        salida = c_void_p()
        g = _guid(iid)
        self.llamar(0, (byref(g), POINTER(GUID)), (byref(salida), POINTER(c_void_p)))
        return _Interfaz(salida)

    def soltar(self) -> None:
        if self.p:
            vtabla = ctypes.cast(self.p, POINTER(POINTER(c_void_p))).contents
            ctypes.WINFUNCTYPE(wintypes.ULONG, c_void_p)(vtabla[2])(self.p)
            self.p = None


def crear_acceso(ruta: Path, destino: str, argumentos: str = "", icono: str = "", descripcion: str = "",
                 carpeta: str = "", app_id: str = APP_ID) -> Path:
    """Crea (o sobrescribe) un acceso directo .lnk."""
    _ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    ruta.parent.mkdir(parents=True, exist_ok=True)
    enlace = c_void_p()
    clsid, iid = _guid(CLSID_SHELLLINK), _guid(IID_ISHELLLINKW)
    _ole32.CoCreateInstance(byref(clsid), None, 0x1, byref(iid), byref(enlace))  # CLSCTX_INPROC_SERVER
    link = _Interfaz(enlace)
    try:
        link.llamar(20, (destino, c_wchar_p))                       # SetPath
        link.llamar(11, (argumentos, c_wchar_p))                    # SetArguments
        link.llamar(7, (descripcion, c_wchar_p))                    # SetDescription
        link.llamar(9, (carpeta or str(Path.home()), c_wchar_p))    # SetWorkingDirectory
        if icono:
            link.llamar(17, (icono, c_wchar_p), (0, ctypes.c_int))  # SetIconLocation
        almacen = link.consultar(IID_IPROPERTYSTORE)
        try:
            clave = PROPERTYKEY(_guid(PKEY_APPUSERMODEL_ID[0]), PKEY_APPUSERMODEL_ID[1])
            valor = PROPVARIANT(vt=VT_LPWSTR, pwszVal=app_id)
            almacen.llamar(6, (byref(clave), POINTER(PROPERTYKEY)), (byref(valor), POINTER(PROPVARIANT)))  # SetValue
            almacen.llamar(7)                                                                             # Commit
        finally:
            almacen.soltar()
        fichero = link.consultar(IID_IPERSISTFILE)
        try:
            fichero.llamar(6, (str(ruta), c_wchar_p), (True, wintypes.BOOL))  # Save
        finally:
            fichero.soltar()
    finally:
        link.soltar()
    return ruta


def fijar_app_id(app_id: str = APP_ID) -> None:
    """Identificador del proceso para la barra de tareas (antes de crear ventanas)."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


# --- carpetas y registro ---------------------------------------------------------
def carpeta_programas() -> Path:
    """Menú Inicio del usuario (…\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs)."""
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _escribir_clave(ruta: str, valores: dict[str, str]) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, ruta, 0, winreg.KEY_SET_VALUE) as k:
        for nombre, valor in valores.items():
            winreg.SetValueEx(k, nombre, 0, winreg.REG_SZ, valor)


def _borrar_arbol(ruta: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    hija = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _borrar_arbol(f"{ruta}\\{hija}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, ruta)
        return True
    except FileNotFoundError:
        return False


def leer_valor(ruta: str, nombre: str = "") -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta) as k:
            return winreg.QueryValueEx(k, nombre)[0]
    except FileNotFoundError:
        return None


def asociar(orden: list[str], icono: str, clases: str = CLASES) -> None:
    """Abre las sesiones .ajustelab con ajustelab, con su icono."""
    from subprocess import list2cmdline

    _escribir_clave(f"{clases}\\{EXTENSION}", {"": PROGID, "Content Type": "application/x-ajustelab"})
    _escribir_clave(f"{clases}\\{EXTENSION}\\OpenWithProgids", {PROGID: ""})
    _escribir_clave(f"{clases}\\{PROGID}", {"": "Sesión de ajustelab", "FriendlyTypeName": "Sesión de ajustelab",
                                            "AppUserModelID": APP_ID})
    _escribir_clave(f"{clases}\\{PROGID}\\DefaultIcon", {"": f'"{icono}",0'})
    _escribir_clave(f"{clases}\\{PROGID}\\shell\\open\\command", {"": list2cmdline(orden) + ' "%1"'})
    _avisar_explorador()


def desasociar(clases: str = CLASES) -> bool:
    quitado = _borrar_arbol(f"{clases}\\{PROGID}")
    if leer_valor(f"{clases}\\{EXTENSION}") == PROGID:
        quitado = _borrar_arbol(f"{clases}\\{EXTENSION}") or quitado
    _avisar_explorador()
    return quitado


def _avisar_explorador() -> None:
    """El Explorador relee las asociaciones e iconos (SHCNE_ASSOCCHANGED)."""
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except (AttributeError, OSError):
        pass
