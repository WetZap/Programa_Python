"""Lectura de datos experimentales en los formatos habituales de laboratorio.

Formatos soportados
-------------------
* Texto: .csv .tsv .txt .dat .prn .asc .lvm .xy .out (y sin extensión).
  Se autodetectan codificación, delimitador (``,`` ``;`` tabulador ``|`` o
  espacios), separador decimal (``.`` o ``,``), líneas de comentario
  (``#``, ``%``, ``//``, ``!``), cabeceras de metadatos (osciloscopios,
  LabVIEW...), cabecera de columnas (también en comentario, estilo gnuplot),
  delimitador final sobrante (``x,y,dx,dy,``) y exponentes Fortran (``1.0D-3``).
* Hojas de cálculo: .xlsx .xlsm .xls .ods (se busca el bloque numérico).
* Otros: .json .npy .npz .mat (MATLAB) .parquet .feather.

Uso típico
----------
>>> tabla = leer_tabla("medidas.dat")          # DataFrame con lo detectado
>>> datos = a_datos(tabla)                      # asignación automática x, y, dx, dy
>>> datos = cargar("medidas.dat", dy_constante=0.05)   # todo en uno
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "Datos",
    "ErrorDatos",
    "leer_tabla",
    "leer_texto",
    "hojas",
    "a_datos",
    "cargar",
    "EXTENSIONES",
]

EXT_TEXTO = {".csv", ".tsv", ".txt", ".dat", ".prn", ".asc", ".lvm", ".xy", ".out", ""}
EXT_HOJA = {".xlsx", ".xlsm", ".xls", ".ods"}
EXT_OTROS = {".json", ".npy", ".npz", ".mat", ".parquet", ".feather"}
EXTENSIONES = sorted((EXT_TEXTO | EXT_HOJA | EXT_OTROS) - {""})

_PREFIJOS_COMENTARIO = ("#", "%", "//", "!")
_DELIMITADORES: tuple[str | None, ...] = (",", ";", "\t", "|", None)  # None = espacios
_NULOS = {"", "nan", "na", "n/a", "null", "none", "-", "--", "?"}
_RE_FORTRAN = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+))[dD]([+-]?\d+)$")

# Estados de _a_numero
_FALLO, _NUMERO, _NULO = 0, 1, 2


class ErrorDatos(ValueError):
    """Error de lectura o validación de datos, con mensaje pensado para el usuario."""


# ---------------------------------------------------------------------------
# Contenedor de datos
# ---------------------------------------------------------------------------
@dataclass
class Datos:
    """Datos (x, y) con incertidumbres opcionales y máscara de puntos incluidos.

    ``dx`` y ``dy`` son desviaciones típicas (1σ). ``incluidos`` permite excluir
    puntos del ajuste sin borrarlos (la GUI lo usará al hacer clic en un punto).
    """

    x: np.ndarray
    y: np.ndarray
    dx: np.ndarray | None = None
    dy: np.ndarray | None = None
    nombre_x: str = "x"
    nombre_y: str = "y"
    incluidos: np.ndarray | None = None
    filas_descartadas: int = 0
    origen: str | None = None
    avisos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.x = np.asarray(self.x, dtype=float).ravel()
        self.y = np.asarray(self.y, dtype=float).ravel()
        n = self.x.size
        if self.y.size != n:
            raise ErrorDatos(f"x tiene {n} valores e y tiene {self.y.size}.")
        if n < 2:
            raise ErrorDatos("Se necesitan al menos 2 puntos.")
        if not (np.all(np.isfinite(self.x)) and np.all(np.isfinite(self.y))):
            raise ErrorDatos("x e y deben ser finitos (sin NaN ni infinitos).")
        self.dx = self._validar_error(self.dx, "dx", n, permitir_cero=True)
        self.dy = self._validar_error(self.dy, "dy", n, permitir_cero=False)
        if self.incluidos is None:
            self.incluidos = np.ones(n, dtype=bool)
        else:
            self.incluidos = np.asarray(self.incluidos, dtype=bool).ravel()
            if self.incluidos.size != n:
                raise ErrorDatos("La máscara 'incluidos' no tiene la longitud de los datos.")

    @staticmethod
    def _validar_error(e, nombre: str, n: int, permitir_cero: bool) -> np.ndarray | None:
        if e is None:
            return None
        e = np.broadcast_to(np.asarray(e, dtype=float), (n,)).copy()
        if not np.all(np.isfinite(e)):
            raise ErrorDatos(f"'{nombre}' contiene NaN o infinitos.")
        if np.any(e < 0):
            raise ErrorDatos(f"'{nombre}' contiene incertidumbres negativas.")
        if not permitir_cero and np.any(e == 0):
            filas = np.flatnonzero(e == 0)
            if filas.size == n:
                raise ErrorDatos(
                    f"Todas las '{nombre}' son 0. Si no tienes incertidumbres, no asignes esa columna."
                )
            raise ErrorDatos(
                f"'{nombre}' = 0 en las filas {filas.tolist()} (peso infinito en el ajuste). "
                "Corrige esos valores o excluye esos puntos."
            )
        return e

    # -- propiedades --------------------------------------------------------
    @property
    def n(self) -> int:
        """Número de puntos incluidos."""
        return int(self.incluidos.sum())

    @property
    def n_total(self) -> int:
        return self.x.size

    @property
    def tiene_dx(self) -> bool:
        return self.dx is not None and bool(np.any(self.dx > 0))

    @property
    def tiene_dy(self) -> bool:
        return self.dy is not None

    # -- operaciones --------------------------------------------------------
    def activos(self) -> "Datos":
        """Copia con solo los puntos incluidos."""
        m = self.incluidos
        return Datos(
            x=self.x[m],
            y=self.y[m],
            dx=None if self.dx is None else self.dx[m],
            dy=None if self.dy is None else self.dy[m],
            nombre_x=self.nombre_x,
            nombre_y=self.nombre_y,
            origen=self.origen,
        )

    def excluir(self, indices: int | Iterable[int]) -> None:
        self.incluidos[np.atleast_1d(np.asarray(indices, dtype=int))] = False

    def incluir(self, indices: int | Iterable[int] | None = None) -> None:
        if indices is None:
            self.incluidos[:] = True
        else:
            self.incluidos[np.atleast_1d(np.asarray(indices, dtype=int))] = True

    def __repr__(self) -> str:
        errores = ", ".join(n for n, e in (("dx", self.dx), ("dy", self.dy)) if e is not None) or "sin errores"
        return f"Datos(n={self.n}/{self.n_total}, {self.nombre_x} vs {self.nombre_y}, {errores})"


# ---------------------------------------------------------------------------
# Utilidades de parseo
# ---------------------------------------------------------------------------
def _a_numero(tok, decimal: str) -> tuple[float, int]:
    """Convierte un token (str o número) a float. Devuelve (valor, estado)."""
    if tok is None:
        return np.nan, _NULO
    if isinstance(tok, (bool, np.bool_)):
        return np.nan, _FALLO
    if isinstance(tok, (int, float, np.integer, np.floating)):
        v = float(tok)
        return (v, _NULO) if np.isnan(v) else (v, _NUMERO)
    t = str(tok).strip().strip('"').strip("'").strip()
    if t.lower() in _NULOS:
        return np.nan, _NULO
    if "_" in t:  # float() aceptaría "1_000"; no es un formato de datos real
        return np.nan, _FALLO
    if decimal == ",":
        if "." in t:  # mezcla de separadores (miles) -> no lo interpretamos
            return np.nan, _FALLO
        t = t.replace(",", ".")
    elif "," in t:
        return np.nan, _FALLO
    m = _RE_FORTRAN.match(t)
    if m:
        t = f"{m.group(1)}e{m.group(2)}"
    try:
        return float(t), _NUMERO
    except ValueError:
        return np.nan, _FALLO


def _partir(linea: str, delim: str | None) -> list[str]:
    if delim is None:
        toks = linea.split()
    else:
        toks = next(csv.reader([linea], delimiter=delim, skipinitialspace=True), [])
        toks = [t.strip() for t in toks]
    # Un delimitador final sobrante (x,y,dx,dy,) genera una columna vacía que se
    # elimina después en _construir_tabla.
    return toks


def _fila_numerica(toks: Sequence, decimal: str) -> list[float] | None:
    """Fila de floats si todos los tokens son números o nulos (y hay ≥1 número)."""
    valores, hay_numero = [], False
    for t in toks:
        v, estado = _a_numero(t, decimal)
        if estado == _FALLO:
            return None
        hay_numero |= estado == _NUMERO
        valores.append(v)
    return valores if hay_numero else None


def _moda(valores: list[int]) -> int:
    return Counter(valores).most_common(1)[0][0]


def _detectar_dialecto(lineas: list[str], delimitador=None, decimal=None) -> tuple[str | None, str, int]:
    """Elige (delimitador, decimal, ncols) que maximiza filas numéricas consistentes."""
    muestra = lineas[-150:]
    delims = (delimitador,) if delimitador is not None else _DELIMITADORES
    decimales = (decimal,) if decimal is not None else (".", ",")
    mejor, mejor_puntos = None, (-1.0, -1)
    for d in delims:
        d = None if d in (" ", "espacios", "whitespace") else d
        for dec in decimales:
            ncols = [len(f) for f in (_fila_numerica(_partir(l, d), dec) for l in muestra) if f is not None]
            if not ncols:
                continue
            nc = _moda(ncols)
            puntos = (sum(n == nc for n in ncols) / len(muestra), nc)
            if puntos > mejor_puntos:  # estricto: en empate gana el candidato anterior
                mejor, mejor_puntos = (d, dec, nc), puntos
    if mejor is None:
        raise ErrorDatos("No se ha encontrado ningún bloque de datos numéricos.")
    return mejor


def _nombres_unicos(nombres: list[str]) -> list[str]:
    vistos: Counter = Counter()
    salida = []
    for i, n in enumerate(nombres):
        n = str(n).strip() or f"col{i + 1}"
        vistos[n] += 1
        salida.append(n if vistos[n] == 1 else f"{n}_{vistos[n]}")
    return salida


def _construir_tabla(filas: list[list[float]], cabecera: list[str] | None, info: dict) -> pd.DataFrame:
    ncols = max(len(f) for f in filas)
    matriz = np.full((len(filas), ncols), np.nan)
    for i, f in enumerate(filas):
        matriz[i, : len(f)] = f
    nombres = _nombres_unicos(cabecera if cabecera and len(cabecera) == ncols else [f"col{i + 1}" for i in range(ncols)])
    df = pd.DataFrame(matriz, columns=nombres)
    df = df.loc[:, df.notna().any(axis=0)]  # columnas vacías (p. ej. osciloscopios Tektronix)
    df.attrs.update(info)
    return df


def _es_cabecera(toks: Sequence, ncols: int, decimal: str) -> bool:
    """Una cabecera tiene ncols campos, ninguno numérico y al menos uno de texto."""
    if len(toks) != ncols:
        return False
    estados = [_a_numero(t, decimal)[1] for t in toks]
    return _NUMERO not in estados and _FALLO in estados


# ---------------------------------------------------------------------------
# Lectores
# ---------------------------------------------------------------------------
def _decodificar(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def leer_texto(texto: str, *, delimitador: str | None = None, decimal: str | None = None) -> pd.DataFrame:
    """Lee datos tabulares desde una cadena (fichero de texto o portapapeles)."""
    lineas: list[tuple[bool, str]] = []  # (es_comentario, contenido)
    for bruta in texto.splitlines():
        s = bruta.strip()
        if not s:
            continue
        if s.startswith(_PREFIJOS_COMENTARIO):
            lineas.append((True, s.lstrip("#%/!").strip()))
        else:
            lineas.append((False, s))
    utiles = [s for c, s in lineas if not c]
    if not utiles:
        raise ErrorDatos("El texto no contiene líneas de datos.")

    delim, dec, ncols = _detectar_dialecto(utiles, delimitador, decimal)

    # Bloque contiguo más largo de filas numéricas con ncols columnas
    # (los comentarios intercalados no rompen el bloque).
    filas_validas: dict[int, list[float]] = {}
    bloque: list[int] = []
    actual: list[int] = []
    for i, (es_com, s) in enumerate(lineas):
        if es_com:
            continue
        fila = _fila_numerica(_partir(s, delim), dec)
        if fila is not None and len(fila) == ncols:
            filas_validas[i] = fila
            actual.append(i)
            if len(actual) > len(bloque):
                bloque = list(actual)
        else:
            actual = []

    # Columnas que realmente tienen datos en el bloque. Algunos equipos
    # (osciloscopios Tektronix) ponen metadatos en otras columnas de las primeras
    # filas: se recuperan esas filas si las columnas de datos son numéricas.
    cols_datos = [j for j in range(ncols) if any(not np.isnan(filas_validas[i][j]) for i in bloque)]
    while bloque and bloque[0] > 0 and not lineas[bloque[0] - 1][0]:
        i = bloque[0] - 1
        toks = _partir(lineas[i][1], delim)
        if len(toks) > max(cols_datos) and all(_a_numero(toks[j], dec)[1] == _NUMERO for j in cols_datos):
            fila = [np.nan] * ncols
            for j in cols_datos:
                fila[j] = _a_numero(toks[j], dec)[0]
            filas_validas[i] = fila
            bloque.insert(0, i)
        else:
            break

    cabecera = None
    if bloque and bloque[0] > 0:
        es_com, s = lineas[bloque[0] - 1]
        for d in (delim, None):
            toks = _partir(s, d)
            if _es_cabecera(toks, ncols, dec):
                cabecera = toks
                break

    info = {
        "delimitador": "espacios" if delim is None else delim,
        "decimal": dec,
        "cabecera": cabecera is not None,
        # líneas no comentario que no son datos (sin contar la cabecera de columnas)
        "filas_ignoradas": len(utiles) - len(bloque) - (1 if cabecera and not lineas[bloque[0] - 1][0] else 0),
    }
    return _construir_tabla([filas_validas[i] for i in bloque], cabecera, info)


def _leer_hoja(ruta: Path, hoja, decimal: str | None) -> pd.DataFrame:
    try:
        crudo = pd.read_excel(ruta, sheet_name=0 if hoja is None else hoja, header=None, dtype=object)
    except ImportError as e:  # falta openpyxl / xlrd / odfpy
        raise ErrorDatos(f"Falta una dependencia para leer '{ruta.suffix}': {e}") from e
    filas = [[None if (isinstance(c, float) and np.isnan(c)) else c for c in fila] for fila in crudo.itertuples(index=False)]
    # Quitar celdas vacías finales de cada fila
    for f in filas:
        while f and (f[-1] is None or (isinstance(f[-1], str) and not f[-1].strip())):
            f.pop()
    if decimal is None:
        textos = [c for f in filas for c in f if isinstance(c, str) and re.fullmatch(r"\s*[+-]?\d+,\d+\s*", c)]
        decimal = "," if textos else "."
    convertidas = [_fila_numerica(f, decimal) if f else None for f in filas]
    longitudes = [len(v) for v in convertidas if v is not None]
    if not longitudes:
        raise ErrorDatos("La hoja no contiene un bloque de datos numéricos.")
    ncols = _moda(longitudes)
    # Racha contigua más larga (las filas totalmente vacías se saltan sin romperla)
    mejor, actual, ini_mejor, ini_actual = [], [], 0, 0
    for i, (f, v) in enumerate(zip(filas, convertidas)):
        if v is not None and len(v) <= ncols:
            if not actual:
                ini_actual = i
            actual.append(v + [np.nan] * (ncols - len(v)))
            if len(actual) > len(mejor):
                mejor, ini_mejor = list(actual), ini_actual
        elif f:
            actual = []
    cabecera = None
    j = ini_mejor - 1
    while j >= 0 and not filas[j]:
        j -= 1
    if j >= 0:
        cand = [str(c) if c is not None else "" for c in filas[j]]
        cand += [""] * (ncols - len(cand))
        if _es_cabecera(cand[:ncols], ncols, decimal):
            cabecera = cand[:ncols]
    hoja_nombre = hoja if hoja is not None else hojas(ruta)[0]
    return _construir_tabla(mejor, cabecera, {"hoja": hoja_nombre, "decimal": decimal, "cabecera": cabecera is not None})


def _tabla_desde_arrays(arrays: dict[str, np.ndarray]) -> pd.DataFrame:
    """Columnas a partir de vectores 1D de igual longitud o de una matriz 2D."""
    arrays = {k: np.squeeze(np.asarray(v)) for k, v in arrays.items()}
    arrays = {k: v for k, v in arrays.items() if v.dtype.kind in "iuf" and v.ndim in (1, 2) and v.size > 1}
    if not arrays:
        raise ErrorDatos("No hay arrays numéricos 1D/2D en el fichero.")
    vectores = {k: v for k, v in arrays.items() if v.ndim == 1}
    if vectores:
        longitud = _moda([v.size for v in vectores.values()])
        cols = {k: v for k, v in vectores.items() if v.size == longitud}
        return pd.DataFrame({k: v.astype(float) for k, v in cols.items()})
    nombre, m = next(iter(arrays.items()))
    if m.shape[0] <= 6 and m.shape[1] > m.shape[0]:  # guardado por filas: [x; y; dy]
        m = m.T
    return pd.DataFrame(m.astype(float), columns=[f"{nombre}[{i}]" for i in range(m.shape[1])])


def leer_tabla(ruta: str | Path, *, hoja=None, delimitador: str | None = None, decimal: str | None = None) -> pd.DataFrame:
    """Lee un fichero de datos y devuelve un DataFrame numérico.

    ``df.attrs`` contiene lo que se ha detectado (delimitador, decimal, cabecera...).
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ErrorDatos(f"No existe el fichero '{ruta}'.")
    ext = ruta.suffix.lower()
    if ext in EXT_HOJA:
        df = _leer_hoja(ruta, hoja, decimal)
    elif ext == ".json":
        with open(ruta, encoding="utf-8") as fh:
            obj = json.load(fh)
        df = pd.DataFrame(obj).apply(pd.to_numeric, errors="coerce")
        df = df.loc[:, df.notna().any(axis=0)]
    elif ext == ".npy":
        arr = np.load(ruta, allow_pickle=False)
        df = _tabla_desde_arrays({"col": arr}) if arr.ndim == 2 else pd.DataFrame({"col1": arr.astype(float)})
    elif ext == ".npz":
        with np.load(ruta, allow_pickle=False) as z:
            df = _tabla_desde_arrays({k: z[k] for k in z.files})
    elif ext == ".mat":
        from scipy.io import loadmat

        try:
            contenido = loadmat(ruta)
        except NotImplementedError as e:  # MATLAB v7.3 = HDF5
            raise ErrorDatos("Fichero .mat v7.3 (HDF5): guárdalo con -v7 o expórtalo a CSV.") from e
        df = _tabla_desde_arrays({k: v for k, v in contenido.items() if not k.startswith("__")})
    elif ext in (".parquet", ".feather"):
        try:
            df = pd.read_parquet(ruta) if ext == ".parquet" else pd.read_feather(ruta)
        except ImportError as e:
            raise ErrorDatos("Para .parquet/.feather instala 'pyarrow'.") from e
        df = df.apply(pd.to_numeric, errors="coerce")
    else:  # texto (incluye extensiones desconocidas)
        df = leer_texto(_decodificar(ruta.read_bytes()), delimitador=delimitador, decimal=decimal)
    if df.empty or df.shape[1] == 0:
        raise ErrorDatos(f"No se han encontrado datos numéricos en '{ruta.name}'.")
    df.attrs["origen"] = str(ruta)
    return df


def hojas(ruta: str | Path) -> list[str]:
    """Nombres de las hojas de un .xlsx/.xls/.ods."""
    return list(pd.ExcelFile(ruta).sheet_names)


# ---------------------------------------------------------------------------
# Asignación de columnas
# ---------------------------------------------------------------------------
_RE_ERR_PREFIJO = re.compile(r"^(?:d|s|e|u|δ|Δ|σ|err_?|error_?|sigma_?|inc_?)(.+)$", re.IGNORECASE)
_RE_ERR_SUFIJO = re.compile(r"^(.+?)[ _]?(?:err|error|sigma|unc|inc)$", re.IGNORECASE)


def _emparejar_errores(columnas: list[str]) -> dict[str, str]:
    """{columna_error: columna_valor} si el nombre de la columna de error referencia a otra."""
    pares = {}
    for c in columnas:
        for patron in (_RE_ERR_PREFIJO, _RE_ERR_SUFIJO):
            m = patron.match(c.strip())
            if m and m.group(1) in columnas and m.group(1) != c:
                pares[c] = m.group(1)
                break
    return pares


def _columna(tabla: pd.DataFrame, ref) -> str:
    if isinstance(ref, (int, np.integer)):
        if not -tabla.shape[1] <= ref < tabla.shape[1]:
            raise ErrorDatos(f"Columna {ref} fuera de rango (hay {tabla.shape[1]}).")
        return tabla.columns[ref]
    if ref not in tabla.columns:
        raise ErrorDatos(f"No existe la columna '{ref}'. Columnas: {list(tabla.columns)}")
    return ref


def a_datos(
    tabla: pd.DataFrame,
    x: int | str | None = None,
    y: int | str | None = None,
    dx: int | str | None = None,
    dy: int | str | None = None,
    *,
    dx_constante: float | None = None,
    dy_constante: float | None = None,
) -> Datos:
    """Convierte una tabla en :class:`Datos`.

    Columnas por posición (int) o nombre (str). Si no se indica ninguna:
    1) si hay columnas cuyo nombre es el error de otra (``V``/``dV``, ``t``/``t_err``)
       se emparejan; 2) si no, convenio posicional: 2 cols → x,y; 3 → x,y,dy;
       ≥4 → x,y,dx,dy. ``*_constante`` asigna una incertidumbre igual a todos los
       puntos (p. ej. la resolución del instrumento) y tiene prioridad sobre la columna.
    Las filas con NaN en las columnas usadas se descartan (se cuentan en
    ``Datos.filas_descartadas``).
    """
    cols = list(tabla.columns)
    avisos: list[str] = []
    if x is None and y is None and dx is None and dy is None:
        pares = _emparejar_errores([str(c) for c in cols])
        valores = [c for c in cols if c not in pares]
        if pares and len(valores) >= 2:
            x, y = valores[0], valores[1]
            inverso = {v: e for e, v in pares.items()}
            dx, dy = inverso.get(x), inverso.get(y)
            avisos.append(f"Columnas asignadas por nombre: x={x}, y={y}, dx={dx}, dy={dy}.")
        else:
            n = len(cols)
            if n < 2:
                raise ErrorDatos("La tabla tiene menos de 2 columnas.")
            x, y = 0, 1
            dy = 2 if n == 3 else (3 if n >= 4 else None)
            dx = 2 if n >= 4 else None
            if n > 4:
                avisos.append(f"La tabla tiene {n} columnas; se usan las 4 primeras (x, y, dx, dy).")
    elif x is None or y is None:
        raise ErrorDatos("Indica a la vez las columnas x e y.")

    cx, cy = _columna(tabla, x), _columna(tabla, y)
    cdx = None if dx is None or dx_constante is not None else _columna(tabla, dx)
    cdy = None if dy is None or dy_constante is not None else _columna(tabla, dy)
    usadas = [c for c in (cx, cy, cdx, cdy) if c is not None]
    limpia = tabla[usadas].dropna()
    descartadas = len(tabla) - len(limpia)
    if descartadas:
        avisos.append(f"Se han descartado {descartadas} filas con valores vacíos.")

    def col(c):
        return None if c is None else limpia[c].to_numpy(dtype=float)

    datos = Datos(
        x=col(cx),
        y=col(cy),
        dx=dx_constante if dx_constante is not None else col(cdx),
        dy=dy_constante if dy_constante is not None else col(cdy),
        nombre_x=str(cx),
        nombre_y=str(cy),
        filas_descartadas=descartadas,
        origen=tabla.attrs.get("origen"),
        avisos=avisos,
    )
    return datos


def cargar(ruta: str | Path, x=None, y=None, dx=None, dy=None, *, hoja=None, delimitador=None, decimal=None,
           dx_constante=None, dy_constante=None) -> Datos:
    """Atajo: :func:`leer_tabla` + :func:`a_datos`."""
    tabla = leer_tabla(ruta, hoja=hoja, delimitador=delimitador, decimal=decimal)
    return a_datos(tabla, x, y, dx, dy, dx_constante=dx_constante, dy_constante=dy_constante)
