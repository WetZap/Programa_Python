"""Comando de terminal ajustelab-cli."""
from pathlib import Path

import pytest

from ajustelab.cli import main

EJEMPLO = str(Path(__file__).resolve().parents[1] / "ejemplos" / "descarga_rc.csv")


def test_listar_modelos(capsys):
    assert main(["--modelos"]) == 0
    assert "exponencial_fondo" in capsys.readouterr().out


def test_ajuste_con_salidas(tmp_path, capsys):
    g, o = tmp_path / "g.png", tmp_path / "inf.txt"
    assert main([EJEMPLO, "-m", "exponencial_fondo", "-g", str(g), "-o", str(o)]) == 0
    salida = capsys.readouterr().out
    assert "tau = 1.71 ± 0.05" in salida
    assert g.stat().st_size > 10_000 and "χ²_ν" in o.read_text(encoding="utf-8")


def test_expresion_p0_columnas_y_exclusion(capsys):
    assert main([EJEMPLO, "-m", "A*exp(-x/tau) + C", "--p0", "5;1,5;0", "--x", "t", "--y", "V", "--dy-cte", "0,04",
                 "--excluir", "3,4"]) == 0
    salida = capsys.readouterr().out
    assert "n = 14" in salida and "Mínimos cuadrados ponderados" in salida


def test_seleccion(capsys):
    assert main([EJEMPLO, "-s", "--criterio", "bic"]) == 0
    assert "Recomendado: Exponencial con fondo" in capsys.readouterr().out


def test_interpolacion_y_tramos(tmp_path, capsys):
    t = tmp_path / "t.csv"
    assert main([EJEMPLO, "-i", "pchip", "--tramos", str(t)]) == 0
    assert t.read_text(encoding="utf-8").startswith("x_ini,x_fin")


@pytest.mark.parametrize("args", [["no_existe.csv"], [EJEMPLO, "-m", "a*x +"], [EJEMPLO, "--x", "t"]])
def test_errores_devuelven_1(args, capsys):
    assert main(args) == 1
    assert "Error" in capsys.readouterr().err
