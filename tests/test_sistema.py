"""Diagnóstico del sistema, integración con el escritorio y lanzador.

Se ejecutan en los tres sistemas de la CI: las funciones reciben rutas y
entornos explícitos, así que no tocan el escritorio real de quien las ejecuta.
"""
import configparser
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ajustelab import escritorio, lanzador, sistema

AUTOMATIZADAS = ("arch", "debian", "fedora", "suse", "void", "gentoo")


# --- distribución -------------------------------------------------------------
@pytest.mark.parametrize("texto, esperada", [
    ('ID=arch\nPRETTY_NAME="Arch Linux"', "arch"),
    ('ID=endeavouros\nID_LIKE=arch', "arch"),
    ('ID="manjaro"\nID_LIKE="arch"', "arch"),
    ('ID=cachyos\nID_LIKE="arch"', "arch"),
    ('ID=ubuntu\nID_LIKE=debian', "debian"),
    ('ID=linuxmint\nID_LIKE="ubuntu debian"', "debian"),
    ('ID=pop\nID_LIKE="ubuntu debian"', "debian"),
    ('ID=fedora', "fedora"),
    ('ID="rocky"\nID_LIKE="rhel centos fedora"', "fedora"),
    ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"', "suse"),
    ('ID=void', "void"),
    ('ID=gentoo', "gentoo"),
    ('ID=nixos', "nixos"),
    ('ID=alpine', "alpine"),
    ('ID=desconocida', None),
])
def test_familia(tmp_path, texto, esperada):
    ruta = tmp_path / "os-release"
    ruta.write_text(texto + "\n# comentario\nVERSION_ID='1.0'\n", encoding="utf-8")
    info = sistema.os_release((str(ruta),))
    assert sistema.familia(info) == esperada
    assert info["VERSION_ID"] == "1.0"


def test_os_release_ausente():
    assert sistema.os_release(("/no/existe",)) == {}


def test_tabla_de_paquetes_completa():
    sonames = [b[0] for b in sistema.BIBLIOTECAS_QT]
    assert len(sonames) == len(set(sonames))
    for soname, uso, por_familia in sistema.BIBLIOTECAS_QT:
        assert uso in ("base", "x11", "wayland")
        assert re.fullmatch(r"lib[\w.+-]+\.so\.\d+", soname), soname
        for fam in AUTOMATIZADAS:
            assert por_familia.get(fam), f"{soname}: falta el paquete de {fam}"
    assert "libxcb-cursor.so.0" in sonames  # el error más habitual de Qt ≥ 6.5 en X11


def test_paquetes_y_orden():
    faltan = [b for b in sistema.BIBLIOTECAS_QT if b[0] in ("libxcb-cursor.so.0", "libEGL.so.1", "libGL.so.1")]
    assert sistema.paquetes(faltan, "arch") == ["libglvnd", "xcb-util-cursor"]  # sin repetir
    assert sistema.paquetes(faltan, "debian") == ["libegl1", "libgl1", "libxcb-cursor0"]
    assert sistema.orden("arch", ["xcb-util-cursor"]) == "sudo pacman -S --needed xcb-util-cursor"
    assert sistema.orden("debian", ["libxcb-cursor0"]) == "sudo apt install libxcb-cursor0"
    assert sistema.orden("fedora", ["x"], con_sudo=False) == "dnf install x"
    assert sistema.orden("nixos", ["x"]) is None and sistema.orden("arch", []) is None
    assert sistema.paquetes(faltan, None) == []


@pytest.mark.parametrize("entorno, usos", [
    ({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}, ("base", "wayland")),
    ({"XDG_SESSION_TYPE": "wayland"}, ("base", "wayland")),
    ({"DISPLAY": ":0"}, ("base", "x11")),
    ({"WAYLAND_DISPLAY": "wayland-0", "QT_QPA_PLATFORM": "xcb"}, ("base", "x11")),
    ({"DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland;xcb"}, ("base", "wayland")),
    ({"QT_QPA_PLATFORM": "offscreen"}, ("base",)),
])
def test_usos_necesarios(entorno, usos):
    assert sistema.usos_necesarios(entorno) == usos


def test_aviso_arranque():
    sin_cursor = lambda so: so != "libxcb-cursor.so.0"  # noqa: E731
    todo = lambda so: True  # noqa: E731
    aviso = sistema.aviso_arranque({"DISPLAY": ":0"}, sin_cursor)
    assert aviso and "libxcb-cursor.so.0" in aviso and "xcb" in aviso
    # En Wayland no se usa xcb: no hay falsa alarma
    assert sistema.aviso_arranque({"WAYLAND_DISPLAY": "wayland-0"}, sin_cursor) is None
    assert sistema.aviso_arranque({"DISPLAY": ":0"}, todo) is None
    assert sistema.aviso_arranque({"QT_QPA_PLATFORM": "offscreen"}, lambda so: False) is None
    assert "sesión gráfica" in sistema.aviso_arranque({}, todo)


def test_diagnostico():
    texto, codigo = sistema.diagnostico()
    assert texto.startswith("ajustelab ") and "Python" in texto and "PySide6" in texto
    assert codigo in (0, 1)


# --- escritorio -------------------------------------------------------------------
def _decodificar_exec(valor: str) -> list[str]:
    """Inverso de citar_exec, según la especificación Desktop Entry 1.5: primero el
    escape general de cadenas (\\s, \\n, \\t, \\r, \\\\) y luego las comillas de Exec,
    donde dentro de "…" una barra escapa a " ` $ y \\."""
    general = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
    texto = re.sub(r"\\(.)", lambda m: general.get(m[1], "\\" + m[1]), valor)
    args, actual, dentro, i, hay = [], "", False, 0, False
    while i < len(texto):
        c = texto[i]
        if dentro:
            if c == "\\" and i + 1 < len(texto) and texto[i + 1] in '"`$\\':
                actual += texto[i + 1]
                i += 1
            elif c == '"':
                dentro = False
            else:
                actual += c
        elif c == '"':
            dentro, hay = True, True
        elif c == " ":
            if actual or hay:
                args.append(actual)
            actual, hay = "", False
        else:
            actual += c
        i += 1
    if actual or hay:
        args.append(actual)
    return [a.replace("%%", "%") for a in args]


@pytest.mark.parametrize("ruta", [
    "/home/ana/.local/share/ajustelab/bin/ajustelab",
    "/home/ana maría/.local/bin/ajustelab",
    "/home/o'neil/$raro/`x`/\"comillas\"/100%/barra\\invertida/ajustelab",
])
def test_citar_exec_ida_y_vuelta(ruta):
    citado = escritorio.citar_exec(ruta)
    assert _decodificar_exec(citado + " %f")[0] == ruta
    if " " not in ruta and "'" not in ruta:
        assert citado == ruta  # las rutas normales no se citan


def test_instalar_y_desinstalar(tmp_path):
    orden = [str(tmp_path / "con espacio" / "ajustelab")]
    Path(orden[0]).parent.mkdir()
    Path(orden[0]).write_text("#!/bin/sh\n", encoding="utf-8")
    escritos = escritorio.instalar(tmp_path, orden, refrescar=False, plataforma="xdg")
    assert set(escritos) == set(escritorio.ficheros(tmp_path))
    desktop = escritorio.ruta_desktop(tmp_path)
    cp = configparser.ConfigParser(interpolation=None, strict=True)
    cp.optionxform = str
    cp.read(desktop, encoding="utf-8")
    e = cp["Desktop Entry"]
    assert e["Type"] == "Application" and e["Icon"] == "ajustelab" and e["Terminal"] == "false"
    assert e["StartupWMClass"] == "ajustelab" and e["MimeType"] == "application/x-ajustelab;"
    assert _decodificar_exec(e["Exec"]) == [orden[0], "%f"]
    assert "Science;" in e["Categories"]
    for n in escritorio.TAMANOS:
        assert (tmp_path / "icons" / "hicolor" / f"{n}x{n}" / "apps" / "ajustelab.png").stat().st_size > 100
    mime = (tmp_path / "mime" / "packages" / "ajustelab.xml").read_text(encoding="utf-8")
    assert 'glob pattern="*.ajustelab"' in mime and "application/x-ajustelab" in mime
    assert escritorio.lanzador_valido(desktop) or escritorio.ES_WINDOWS
    if shutil.which("desktop-file-validate"):
        r = subprocess.run(["desktop-file-validate", str(desktop)], capture_output=True, text=True)
        assert r.returncode == 0 and not r.stdout.strip(), r.stdout
    Path(orden[0]).unlink()
    if not escritorio.ES_WINDOWS:
        assert not escritorio.lanzador_valido(desktop)  # el diagnóstico detecta una entrada rota
    borrados = escritorio.desinstalar(tmp_path, refrescar=False, plataforma="xdg")
    assert set(borrados) == set(escritos) and not desktop.exists()
    assert escritorio.desinstalar(tmp_path, refrescar=False, plataforma="xdg") == []


def test_orden_lanzar(tmp_path, monkeypatch):
    orden = escritorio.orden_lanzar()
    assert Path(orden[0]).is_absolute() and Path(orden[0]).exists()
    # Instalación hecha por instalar.sh: se usa su lanzador, que vigila el entorno
    venv = tmp_path / "ajustelab" / "venv"
    venv.mkdir(parents=True)
    lanzador_sh = tmp_path / "ajustelab" / "bin" / "ajustelab"
    lanzador_sh.parent.mkdir()
    lanzador_sh.write_text("#!/bin/sh\n# Lanzador generado por instalar.sh de ajustelab\n", encoding="utf-8")
    lanzador_sh.chmod(0o755)
    monkeypatch.setattr(sys, "prefix", str(venv))
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    if os.name == "posix":
        assert escritorio.orden_lanzar() == [str(lanzador_sh)]
    else:  # en Windows se usa el lanzador sin consola de pip o pythonw.exe
        assert escritorio.orden_lanzar()[0].lower().endswith(("ajustelab.exe", "pythonw.exe", "python.exe"))
    lanzador_sh.write_text("#!/bin/sh\necho otro\n", encoding="utf-8")  # sin la marca: no se usa
    assert escritorio.orden_lanzar() != [str(lanzador_sh)]


# --- lanzador -------------------------------------------------------------------
@pytest.mark.parametrize("args, propios, qt", [
    (["datos.csv"], ["datos.csv"], []),
    (["-platform", "xcb", "datos.csv"], ["datos.csv"], ["-platform", "xcb"]),
    (["-style=Fusion", "--diagnostico"], ["--diagnostico"], ["-style=Fusion"]),
    (["-V"], ["-V"], []),
    (["-h"], ["-h"], []),
    (["-reverse", "x.ajustelab"], ["x.ajustelab"], ["-reverse"]),
])
def test_separar_argumentos(args, propios, qt):
    assert lanzador.separar_argumentos(args) == (propios, qt)


def test_version_y_ayuda(capsys):
    with pytest.raises(SystemExit) as e:
        lanzador.main(["ajustelab", "-V"])
    assert e.value.code == 0 and "ajustelab 1." in capsys.readouterr().out
    with pytest.raises(SystemExit):
        lanzador.main(["ajustelab", "--help"])
    salida = capsys.readouterr().out
    assert "--diagnostico" in salida and "--instalar-escritorio" in salida and "--paquetes-sistema" not in salida


CLAVE_PRUEBAS = r"Software\ajustelab-pruebas\Classes"


@pytest.fixture
def windows_aislado(tmp_path, monkeypatch):
    """En Windows, menú Inicio en una carpeta temporal y asociación en una clave de pruebas."""
    if not escritorio.ES_WINDOWS:
        yield None
        return
    from ajustelab import windows

    monkeypatch.setattr(windows, "carpeta_programas", lambda: tmp_path / "Programs")
    monkeypatch.setattr(windows, "CLASES", CLAVE_PRUEBAS)
    yield windows
    windows._borrar_arbol(r"Software\ajustelab-pruebas")


def test_opciones_de_sistema(capsys, tmp_path, monkeypatch, windows_aislado):
    assert lanzador.main(["ajustelab", "--diagnostico"]) in (0, 1)
    assert "diagnóstico" in capsys.readouterr().out
    assert lanzador.main(["ajustelab", "--paquetes-sistema"]) == 0
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    codigo = lanzador.main(["ajustelab", "--instalar-escritorio"])
    if sistema.es_linux() or escritorio.ES_WINDOWS:
        entrada = escritorio.ruta_entrada(None if escritorio.ES_WINDOWS else tmp_path)
        assert codigo == 0 and entrada.is_file()
        assert lanzador.main(["ajustelab", "--desinstalar-escritorio"]) == 0
        assert not entrada.exists()
    else:
        assert codigo == 2


@pytest.mark.skipif(not escritorio.ES_WINDOWS, reason="solo en Windows")
def test_windows_acceso_y_asociacion(tmp_path, windows_aislado):
    """Acceso directo con su AppUserModelID y asociación de .ajustelab (comprobados con el Shell)."""
    w = windows_aislado
    orden = escritorio.orden_lanzar()
    lnk, = escritorio.instalar(tmp_path / "Programs", orden, plataforma="windows", clases=CLAVE_PRUEBAS)
    assert lnk.is_file() and lnk.name == "ajustelab.lnk"
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:AJ_LNK); "
              "$i = (New-Object -ComObject Shell.Application).NameSpace($env:AJ_DIR).ParseName('ajustelab.lnk'); "
              "Write-Output $s.TargetPath; Write-Output $s.IconLocation; "
              "Write-Output $i.ExtendedProperty('System.AppUserModel.ID')")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                       text=True, env={**os.environ, "AJ_LNK": str(lnk), "AJ_DIR": str(lnk.parent)}, timeout=120)
    destino, icono, app_id = (r.stdout.strip().splitlines() + ["", "", ""])[:3]
    assert Path(destino) == Path(orden[0]), r.stderr
    assert icono.lower().startswith(str(escritorio.RECURSOS / "icono.ico").lower())
    assert app_id == w.APP_ID
    assert w.leer_valor(f"{CLAVE_PRUEBAS}\\.ajustelab") == w.PROGID
    comando = w.leer_valor(f"{CLAVE_PRUEBAS}\\{w.PROGID}\\shell\\open\\command")
    assert comando.endswith('"%1"') and Path(orden[0]).name.lower() in comando.lower()
    assert "icono.ico" in w.leer_valor(f"{CLAVE_PRUEBAS}\\{w.PROGID}\\DefaultIcon")
    assert escritorio.lanzador_valido(lnk, clases=CLAVE_PRUEBAS)
    assert escritorio.desinstalar(tmp_path / "Programs", plataforma="windows", clases=CLAVE_PRUEBAS) == [lnk]
    assert not lnk.exists() and w.leer_valor(f"{CLAVE_PRUEBAS}\\.ajustelab") is None


def test_diagnostico_redirigido():
    """Redirigida (fichero, tubería), la salida va en UTF-8 aunque el sistema use cp1252."""
    entorno = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    r = subprocess.run([sys.executable, "-m", "ajustelab", "--diagnostico"], capture_output=True, env=entorno,
                       timeout=120)
    assert r.returncode in (0, 1), r.stderr.decode("utf-8", "replace")
    texto = r.stdout.decode("utf-8")
    assert "diagnóstico" in texto and ("✓" in texto or "✗" in texto)


def test_importar_es_ligero():
    """«import ajustelab» no carga SciPy ni SymPy (carga perezosa) y la API sigue igual."""
    codigo = ("import sys, ajustelab; pesados = [m for m in ('scipy', 'sympy', 'pandas') if m in sys.modules]; "
              "print(pesados); from ajustelab import ajustar, CATALOGO, Datos; "
              "print(callable(ajustar), len(CATALOGO) > 20, 'cargar' in dir(ajustelab))")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert r.stdout.split() == ["[]", "True", "True", "True"]
    import ajustelab

    with pytest.raises(AttributeError):
        ajustelab.no_existe  # noqa: B018


@pytest.mark.gui
def test_probar_interfaz():
    entorno = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "ajustelab", "--probar-interfaz"], capture_output=True,
                       text=True, env=entorno, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "La interfaz funciona" in r.stdout and "offscreen" in r.stdout
