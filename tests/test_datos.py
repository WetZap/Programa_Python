"""Tests del lector de datos: formatos de texto, hojas de cálculo y binarios."""
import json

import numpy as np
import pandas as pd
import pytest

from ajustelab.datos import Datos, ErrorDatos, a_datos, cargar, leer_tabla, leer_texto

X = [1.0, 2.0, 3.0]
Y = [2.5, 4.1, 6.2]


def _comprobar(df, ncols=None):
    assert np.allclose(df.iloc[:, 0], X)
    assert np.allclose(df.iloc[:, 1], Y)
    if ncols is not None:
        assert df.shape[1] == ncols


@pytest.mark.parametrize(
    "texto, delim, dec",
    [
        ("x,y,dx,dy\n1,2.5,0.1,0.2\n2,4.1,0.1,0.2\n3,6.2,0.1,0.3\n", ",", "."),
        ("x,y,dx,dy,\n1,2.5,0.1,0.2,\n2,4.1,0.1,0.2,\n3,6.2,0.1,0.3,\n", ",", "."),  # formato del script antiguo
        ("x;y;dx;dy\n1;2,5;0,1;0,2\n2;4,1;0,1;0,2\n3;6,2;0,1;0,3\n", ";", ","),  # Excel en español
        ("x\ty\tdx\tdy\n1\t2,5\t0,1\t0,2\n2\t4,1\t0,1\t0,2\n3\t6,2\t0,1\t0,3\n", "\t", ","),
        ("# x y dx dy\n1 2.5 0.1 0.2\n2 4.1 0.1 0.2\n\n3 6.2 0.1 0.3\n", "espacios", "."),  # gnuplot
        ("1 2,5 0,1 0,2\n2 4,1 0,1 0,2\n3 6,2 0,1 0,3\n", "espacios", ","),
        ("1|2.5|0.1|0.2\n2|4.1|0.1|0.2\n3|6.2|0.1|0.3\n", "|", "."),
        ('"x","y","dx","dy"\n"1","2,5","0,1","0,2"\n"2","4,1","0,1","0,2"\n"3","6,2","0,1","0,3"\n', ",", ","),
    ],
)
def test_dialectos(texto, delim, dec):
    df = leer_texto(texto)
    _comprobar(df, 4)
    assert df.attrs["delimitador"] == delim
    assert df.attrs["decimal"] == dec


def test_csv_comillas_decimal_coma():
    # coma como delimitador Y como decimal, protegida por comillas
    df = leer_texto('"1,0","2,5"\n"2,0","4,1"\n"3,0","6,2"\n')
    _comprobar(df, 2)


def test_metadatos_y_cabecera():
    texto = "Equipo: X\nFecha: 30/10/2026\n\nt (s),V (V)\n1,2.5\n2,4.1\n3,6.2\n"
    df = leer_texto(texto)
    _comprobar(df, 2)
    assert list(df.columns) == ["t (s)", "V (V)"]


def test_fortran_y_nan():
    df = leer_texto("1.0D0 2.5D0\n2.0d0 4.1D+0\n3.0D0 6.2D0\n4 nan\n")
    assert np.allclose(df.iloc[:3, 1], Y)
    assert np.isnan(df.iloc[3, 1])


def test_tektronix_recupera_filas_con_metadatos():
    texto = (
        "Record Length,4,,1,2.5,\n"
        "Sample Interval,1e-8,,2,4.1,\n"
        ",,,3,6.2,\n"
        ",,,4,8.0,\n"
    )
    df = leer_texto(texto)
    assert df.shape == (4, 2)
    assert np.allclose(df.iloc[:3, 1], Y)


def test_sin_datos():
    with pytest.raises(ErrorDatos):
        leer_texto("solo texto\nsin números\n")


# --- ficheros -------------------------------------------------------------
@pytest.fixture
def tabla():
    return pd.DataFrame({"x": X, "y": Y, "dy": [0.2, 0.2, 0.3]})


@pytest.mark.parametrize("ext", [".xlsx", ".ods"])
def test_hojas_calculo(tmp_path, tabla, ext):
    ruta = tmp_path / f"datos{ext}"
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame([["Práctica 3"]]).to_excel(w, index=False, header=False, startrow=0)
        tabla.to_excel(w, index=False, startrow=3)
    df = leer_tabla(ruta)
    _comprobar(df, 3)
    assert list(df.columns) == ["x", "y", "dy"]


def test_xlsx_decimal_coma_como_texto(tmp_path):
    ruta = tmp_path / "coma.xlsx"
    pd.DataFrame({"x": ["1", "2", "3"], "y": ["2,5", "4,1", "6,2"]}).to_excel(ruta, index=False)
    _comprobar(leer_tabla(ruta), 2)


def test_binarios(tmp_path, tabla):
    m = tabla.to_numpy()
    np.save(tmp_path / "a.npy", m)
    _comprobar(leer_tabla(tmp_path / "a.npy"), 3)
    # Guardado por filas ([x; y; dy], típico de np.savetxt) con más puntos que
    # columnas: se transpone. (Una matriz cuadrada es ambigua y no se toca.)
    larga = np.vstack([np.arange(8.0), 2 * np.arange(8.0), np.full(8, 0.1)])
    np.save(tmp_path / "t.npy", larga)
    df = leer_tabla(tmp_path / "t.npy")
    assert df.shape == (8, 3) and np.allclose(df.iloc[:, 1], 2 * np.arange(8.0))
    np.savez(tmp_path / "b.npz", x=np.array(X), y=np.array(Y))
    _comprobar(leer_tabla(tmp_path / "b.npz"), 2)
    from scipy.io import savemat

    savemat(tmp_path / "c.mat", {"x": np.array(X), "y": np.array(Y)})
    _comprobar(leer_tabla(tmp_path / "c.mat"), 2)
    (tmp_path / "d.json").write_text(json.dumps({"x": X, "y": Y}))
    _comprobar(leer_tabla(tmp_path / "d.json"), 2)


def test_codificacion_latin1(tmp_path):
    ruta = tmp_path / "l.txt"
    ruta.write_bytes("tensión;corriente\n1;2,5\n2;4,1\n3;6,2\n".encode("cp1252"))
    df = leer_tabla(ruta)
    _comprobar(df, 2)
    assert df.columns[0] == "tensión"


# --- asignación de columnas ------------------------------------------------
def test_convenio_posicional():
    df = pd.DataFrame(np.column_stack([X, Y, [0.1] * 3, [0.2] * 3]))
    d = a_datos(df)
    assert np.allclose(d.dx, 0.1) and np.allclose(d.dy, 0.2)
    d3 = a_datos(df.iloc[:, :3])
    assert d3.dx is None and np.allclose(d3.dy, 0.1)


def test_emparejado_por_nombre():
    df = pd.DataFrame({"t": X, "V": Y, "dV": [0.2] * 3, "t_err": [0.01] * 3})
    d = a_datos(df)
    assert d.nombre_x == "t" and d.nombre_y == "V"
    assert np.allclose(d.dy, 0.2) and np.allclose(d.dx, 0.01)


def test_constantes_y_nan(tmp_path):
    ruta = tmp_path / "c.csv"
    ruta.write_text("x,y\n1,2.5\n2,4.1\n3,6.2\n4,\n")
    d = cargar(ruta, dy_constante=0.05)
    assert d.n == 3 and d.filas_descartadas == 1
    assert np.allclose(d.dy, 0.05)


def test_validacion():
    with pytest.raises(ErrorDatos):
        Datos(X, Y, dy=[0.1, 0.0, 0.1])  # dy = 0
    with pytest.raises(ErrorDatos):
        Datos(X, Y, dy=[0.1, -0.1, 0.1])
    with pytest.raises(ErrorDatos):
        Datos(X, Y[:2])
    d = Datos(X, Y, dx=[0.0, 0.1, 0.0])  # dx = 0 sí está permitido
    d.excluir(1)
    assert d.n == 2 and d.activos().n_total == 2


# --- columnas de etiquetas (texto) ----------------------------------------------------
def test_columna_de_etiquetas_con_coma_decimal():
    df = leer_texto("Metal;Fracción;dF\nPb;0,25;0,01\nCu;0,40;0,02\nFe;0,35;0,01\n")
    assert list(df.columns) == ["Metal", "Fracción", "dF"]
    assert list(df["Metal"]) == ["Pb", "Cu", "Fe"] and df["Fracción"].tolist() == [0.25, 0.40, 0.35]
    sin_cabecera = leer_texto("Pb;0,25\nCu;0,40\nFe;0,35\n")
    assert list(sin_cabecera.iloc[:, 0]) == ["Pb", "Cu", "Fe"]
    d = a_datos(df)  # las etiquetas no entran en el reparto automático de x, y, σ
    assert d.nombre_x == "Fracción" and d.nombre_y == "dF"
    with pytest.raises(ErrorDatos, match="texto"):
        a_datos(df, "Metal", "Fracción")


def test_etiquetas_con_espacios_y_fechas():
    df = leer_texto("Muestra,Fecha,T\nM 1,2026-01-05,20.1\nM 2,2026-01-06,21.3\nM 3,2026-01-07,19.8\n")
    assert list(df["Muestra"]) == ["M 1", "M 2", "M 3"] and df["Fecha"].iloc[0] == "2026-01-05"
    assert df["T"].dtype == float


def test_ficheros_numericos_se_leen_igual():
    """La lectura con etiquetas solo gana si lee más filas: «0,2;4,5» no se parte por la coma."""
    df = leer_texto("t;V\n0,2000;4,5634\n0,5867;3,7189\n0,9733;2,9903\n")
    assert list(df.columns) == ["t", "V"] and df["V"].tolist() == [4.5634, 3.7189, 2.9903]


def test_hoja_y_json_con_etiquetas(tmp_path):
    original = pd.DataFrame({"Grupo": ["A", "B", "C"], "valor": [1.5, 2.5, 3.5]})
    ruta = tmp_path / "grupos.xlsx"
    original.to_excel(ruta, index=False)
    df = leer_tabla(ruta)
    assert list(df["Grupo"]) == ["A", "B", "C"] and df["valor"].tolist() == [1.5, 2.5, 3.5]
    ruta = tmp_path / "grupos.json"
    original.to_json(ruta, orient="columns")
    df = leer_tabla(ruta)
    assert list(df["Grupo"]) == ["A", "B", "C"] and df["valor"].tolist() == [1.5, 2.5, 3.5]
