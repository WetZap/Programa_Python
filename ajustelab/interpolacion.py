"""Interpolación y splines de suavizado.

Interpolar ≠ ajustar
--------------------
Un interpolante pasa **exactamente** por todos los puntos, así que ignora las
incertidumbres: solo tiene sentido con datos sin ruido apreciable (tablas,
curvas de calibración, simulaciones). Con datos experimentales ruidosos usa
``metodo="suavizado"`` o, mejor aún, un modelo con :func:`ajustelab.ajustar`.

Métodos (``METODOS``)
---------------------
lineal       lineal a trozos.
natural      spline cúbico con f'' = 0 en los extremos.
not-a-knot   spline cúbico; la 3.ª derivada es continua en el 2.º y penúltimo nodo
             (reproduce exactamente un cúbico; es el defecto de SciPy).
clamped      spline cúbico con f' fijada en los extremos (``derivadas_extremos``).
periodico    spline cúbico periódico (requiere y[0] = y[-1]).
pchip        cúbico de Hermite monótono: no sobreoscila; ideal para datos monótonos.
akima        Akima: robusto frente a puntos aislados que se salen de la tendencia.
makima       Akima modificado (menos ondulaciones en tramos planos).
suavizado    spline cúbico penalizado que NO pasa por los puntos: minimiza
             Σ w(y − f)² + λ∫f''², con w = 1/σ_y² si hay σ_y y λ elegido por
             validación cruzada generalizada (GCV) salvo que se fije.
polinomio    polinomio global de grado n−1 (Lagrange). Solo para pocos puntos
             (fenómeno de Runge).

Todos se representan como ``scipy.interpolate.PPoly``, de modo que evaluación,
derivadas, integrales, raíces y exportación de tramos son comunes. La
incertidumbre de cualquier magnitud derivada (valor, derivada, integral, raíz...)
se propaga por Monte Carlo perturbando los datos con sus σ.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.interpolate import (Akima1DInterpolator, CubicSpline, PchipInterpolator, PPoly, make_interp_spline,
                               make_smoothing_spline)

from .datos import Datos

__all__ = ["METODOS", "Interpolacion", "ResultadoMC", "Tramo", "ErrorInterpolacion", "interpolar", "valores_x"]

METODOS: dict[str, str] = {
    "lineal": "Lineal a trozos",
    "natural": "Spline cúbico natural",
    "not-a-knot": "Spline cúbico not-a-knot",
    "clamped": "Spline cúbico con derivadas en los extremos",
    "periodico": "Spline cúbico periódico",
    "pchip": "PCHIP (monótono)",
    "akima": "Akima",
    "makima": "Akima modificado",
    "suavizado": "Spline de suavizado",
    "polinomio": "Polinomio interpolador global",
}

_MINIMO_PUNTOS = {"suavizado": 5, "periodico": 3}
MAX_EVALUACIONES = 10_000

# Para el resumen del informe: qué es cada método, en una frase
_DESCRIPCION = {
    "lineal": "interpolación lineal a trozos",
    "natural": "un spline cúbico natural (segunda derivada nula en los extremos)",
    "not-a-knot": "un spline cúbico con condición not-a-knot (tercera derivada continua en el segundo y el "
                  "penúltimo nodo)",
    "clamped": "un spline cúbico con la derivada fijada en los extremos",
    "periodico": "un spline cúbico periódico",
    "pchip": "el interpolante cúbico monótono PCHIP (Fritsch–Carlson), que no oscila entre los nodos",
    "akima": "el interpolante de Akima",
    "makima": "el interpolante de Akima modificado",
    "suavizado": "un spline cúbico de suavizado",
    "polinomio": "el polinomio interpolador global",
}


def valores_x(texto: str) -> np.ndarray:
    """Valores de x escritos a mano: ``17``, ``1; 2; 5`` (o separados por espacios)
    o un rango ``inicio:fin:paso`` (``inicio:fin`` da 11 puntos). Admite coma decimal."""
    texto = texto.strip()
    if not texto:
        raise ErrorInterpolacion("Escribe un valor de x, una lista (1; 2; 5) o un rango (0:10:0,5).")
    salida: list[float] = []
    for trozo in texto.replace("\n", ";").split(";"):
        for parte in trozo.split():
            numeros = parte.replace(",", ".").split(":")
            try:
                v = [float(n) for n in numeros]
            except ValueError:
                raise ErrorInterpolacion(f"«{parte}» no es un número ni un rango inicio:fin:paso.") from None
            if len(v) == 1:
                salida.append(v[0])
            elif len(v) in (2, 3):
                a, b = v[0], v[1]
                if len(v) == 2:
                    salida.extend(np.linspace(a, b, 11))
                    continue
                paso = v[2]
                if paso == 0 or (b - a) / paso < 0:
                    raise ErrorInterpolacion(f"El paso de «{parte}» no lleva de {a:g} a {b:g}.")
                n = int(np.floor((b - a) / paso + 1e-9)) + 1
                if n > MAX_EVALUACIONES:
                    raise ErrorInterpolacion(f"«{parte}» da {n} puntos (máximo {MAX_EVALUACIONES}).")
                salida.extend(a + paso * np.arange(n))
            else:
                raise ErrorInterpolacion(f"«{parte}»: un rango es inicio:fin o inicio:fin:paso.")
    if len(salida) > MAX_EVALUACIONES:
        raise ErrorInterpolacion(f"Demasiados puntos ({len(salida)}; máximo {MAX_EVALUACIONES}).")
    return np.array(salida, dtype=float)


def _unidad(nombre: str) -> str:
    """«V (V)» → «V»; sin unidad entre paréntesis al final, cadena vacía."""
    import re

    m = re.search(r"\(([^()]*)\)\s*$", nombre)
    return m.group(1).strip() if m else ""


def _simbolo(nombre: str) -> str:
    """«V (V)» → «V» (el nombre sin la unidad final)."""
    import re

    return re.sub(r"\s*\([^()]*\)\s*$", "", nombre).strip() or nombre


def _lista(frases: list[str]) -> str:
    return frases[0] if len(frases) == 1 else ", ".join(frases[:-1]) + " y " + frases[-1]


def _tex(texto: str) -> str:
    """Escapa para LaTeX lo que no esté ya entre $…$."""
    if "$" in texto:
        return texto
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_")):
        texto = texto.replace(a, b)
    return texto


class ErrorInterpolacion(ValueError):
    """La interpolación no se puede construir o evaluar."""


# ---------------------------------------------------------------------------
# Preparación de datos
# ---------------------------------------------------------------------------
def _fusionar_duplicados(x, y, dy, dx):
    """Ordena por x y promedia (ponderado si hay σ_y) los puntos con x repetida."""
    o = np.argsort(x, kind="stable")
    x, y = x[o], y[o]
    dy = None if dy is None else dy[o]
    dx = None if dx is None else dx[o]
    ux, inv, cuenta = np.unique(x, return_inverse=True, return_counts=True)
    if ux.size == x.size:
        return x, y, dy, dx, 0
    w = np.ones_like(y) if dy is None else 1 / dy**2
    sw = np.bincount(inv, w)
    y_m = np.bincount(inv, w * y) / sw
    dy_m = None if dy is None else 1 / np.sqrt(sw)
    dx_m = None if dx is None else np.sqrt(np.bincount(inv, dx**2)) / cuenta
    return ux, y_m, dy_m, dx_m, int(x.size - ux.size)


# ---------------------------------------------------------------------------
# Construcción de un PPoly para cada método
# ---------------------------------------------------------------------------
def _construir(x, y, metodo: str, dy=None, derivadas_extremos=None, suavizado=None) -> PPoly:
    if metodo == "lineal":
        return PPoly.from_spline(make_interp_spline(x, y, k=1))
    if metodo == "natural":
        return CubicSpline(x, y, bc_type="natural")
    if metodo == "not-a-knot":
        return CubicSpline(x, y, bc_type="not-a-knot")
    if metodo == "clamped":
        if derivadas_extremos is None:
            raise ErrorInterpolacion("El spline 'clamped' necesita derivadas_extremos=(f'(x0), f'(xn)).")
        d0, d1 = derivadas_extremos
        return CubicSpline(x, y, bc_type=((1, float(d0)), (1, float(d1))))
    if metodo == "periodico":
        return CubicSpline(x, y, bc_type="periodic")
    if metodo == "pchip":
        return PchipInterpolator(x, y)
    if metodo in ("akima", "makima"):
        return Akima1DInterpolator(x, y, method=metodo)
    if metodo == "suavizado":
        w = None if dy is None else 1 / dy**2
        return PPoly.from_spline(make_smoothing_spline(x, y, w=w, lam=suavizado))
    if metodo == "polinomio":
        h = x[-1] - x[0]
        grado = x.size - 1
        c = np.polyfit((x - x[0]) / h, y, grado)  # en variable reescalada t ∈ [0, 1]
        c = c / h ** np.arange(grado, -1, -1)  # coeficientes en potencias de (x − x0)
        return PPoly(c[:, None], np.array([x[0], x[-1]]))
    raise ErrorInterpolacion(f"Método '{metodo}' desconocido. Opciones: {', '.join(METODOS)}.")


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------
@dataclass
class ResultadoMC:
    """Propagación Monte Carlo: valor con los datos nominales y dispersión."""

    nominal: np.ndarray | float
    media: np.ndarray | float
    sigma: np.ndarray | float
    muestras: np.ndarray = field(repr=False)
    validas: int = 0
    total: int = 0


@dataclass
class Tramo:
    """C(x) = Σ c_j (x − x_ini)^(grado − j), para x_ini ≤ x ≤ x_fin."""

    x_ini: float
    x_fin: float
    coeficientes: np.ndarray  # de mayor a menor potencia

    @property
    def grado(self) -> int:
        return self.coeficientes.size - 1

    def __call__(self, x):
        return np.polyval(self.coeficientes, np.asarray(x, float) - self.x_ini)


@dataclass
class Interpolacion:
    metodo: str
    x: np.ndarray
    y: np.ndarray
    dy: np.ndarray | None
    dx: np.ndarray | None
    pp: PPoly = field(repr=False)
    opciones: dict = field(default_factory=dict, repr=False)
    nombre_x: str = "x"
    nombre_y: str = "y"
    extrapolar: bool = False
    avisos: list[str] = field(default_factory=list)

    # -- evaluación ---------------------------------------------------------
    @property
    def rango(self) -> tuple[float, float]:
        return float(self.x[0]), float(self.x[-1])

    def __call__(self, x) -> np.ndarray:
        """Valor interpolado. Fuera de [x0, xn] devuelve NaN salvo ``extrapolar=True``."""
        return self.pp(np.asarray(x, float), extrapolate=self.extrapolar)

    def derivada(self, x, orden: int = 1) -> np.ndarray:
        return self.pp.derivative(orden)(np.asarray(x, float), extrapolate=self.extrapolar)

    def integral(self, a: float | None = None, b: float | None = None) -> float:
        """∫_a^b f dx (por defecto en todo el rango)."""
        a = self.x[0] if a is None else a
        b = self.x[-1] if b is None else b
        lo, hi = self.rango
        if not self.extrapolar and (min(a, b) < lo or max(a, b) > hi):
            raise ErrorInterpolacion(f"[{a}, {b}] se sale del rango [{lo}, {hi}] (activa extrapolar).")
        return float(self.pp.integrate(a, b, extrapolate=self.extrapolar))

    def inversa(self, y0: float) -> np.ndarray:
        """Todos los x del rango con f(x) = y0, ordenados."""
        raices = self.pp.solve(float(y0), discontinuity=False, extrapolate=False)
        raices = raices[np.isfinite(raices)]
        lo, hi = self.rango
        raices = list(raices[(raices >= lo) & (raices <= hi)])
        # Raíces justo en los extremos que el redondeo puede perder
        tol = 1e-10 * max(np.ptp(self.y), abs(y0), 1e-300)
        for extremo in (lo, hi):
            if abs(self.pp(extremo) - y0) <= tol:
                raices.append(extremo)
        if not raices:
            return np.array([])
        raices = np.sort(raices)
        distintas = [raices[0]]
        for r in raices[1:]:
            if r - distintas[-1] > 1e-9 * (hi - lo):
                distintas.append(r)
        return np.array(distintas)

    def extremos(self) -> list[tuple[float, float, str]]:
        """Máximos y mínimos locales interiores: [(x, f(x), 'máximo'|'mínimo')]."""
        lo, hi = self.rango
        if self.pp.c.shape[0] >= 3:  # grado ≥ 2: ceros de la derivada
            cand = self.pp.derivative().roots(discontinuity=False, extrapolate=False)
        else:  # lineal a trozos: los extremos están en los nodos
            cand = self.x[1:-1]
        cand = np.unique(cand[np.isfinite(cand) & (cand > lo) & (cand < hi)])
        salida = []
        eps = 1e-7 * (hi - lo)
        for xc in cand:
            f0, fi, fd = self.pp([xc, xc - eps, xc + eps])
            if f0 >= fi and f0 >= fd and (f0 > fi or f0 > fd):
                salida.append((float(xc), float(f0), "máximo"))
            elif f0 <= fi and f0 <= fd and (f0 < fi or f0 < fd):
                salida.append((float(xc), float(f0), "mínimo"))
        return salida

    # -- incertidumbre ------------------------------------------------------
    def reconstruir(self, x, y) -> "Interpolacion":
        """Misma interpolación (método y opciones) con otros datos."""
        pp = _construir(x, y, self.metodo, dy=self.dy, **self.opciones)
        return Interpolacion(self.metodo, x, y, self.dy, self.dx, pp, self.opciones, self.nombre_x,
                             self.nombre_y, self.extrapolar)

    def monte_carlo(self, funcion: Callable[["Interpolacion"], float | np.ndarray], n: int = 1000,
                    semilla: int = 0) -> ResultadoMC:
        """Propaga σ_y (y σ_x si hay) a ``funcion(interpolacion)`` por Monte Carlo.

        Ejemplos: ``f.monte_carlo(lambda g: g(2.5))``, ``lambda g: g.integral()``,
        ``lambda g: g.inversa(0.5)[0]``. Las muestras que fallan o dan NaN se descartan.
        """
        if self.dy is None and self.dx is None:
            raise ErrorInterpolacion("Sin incertidumbres en los datos no se puede propagar el error.")
        rng = np.random.default_rng(semilla)
        nominal = np.asarray(funcion(self), dtype=float)
        muestras = []
        for _ in range(n):
            y = self.y + (rng.normal(0, self.dy) if self.dy is not None else 0)
            x = self.x + (rng.normal(0, self.dx) if self.dx is not None else 0)
            o = np.argsort(x)
            x, y = x[o], y[o]
            if np.any(np.diff(x) <= 0):
                continue
            try:
                v = np.asarray(funcion(self.reconstruir(x, y)), dtype=float)
            except (ValueError, IndexError, ErrorInterpolacion):
                continue
            if v.shape == nominal.shape and np.all(np.isfinite(v)):
                muestras.append(v)
        if len(muestras) < 10:
            raise ErrorInterpolacion("Casi todas las muestras Monte Carlo han fallado.")
        m = np.array(muestras)
        return ResultadoMC(nominal=nominal[()], media=m.mean(axis=0)[()], sigma=m.std(axis=0, ddof=1)[()],
                           muestras=m, validas=len(muestras), total=n)

    def sigma(self, x, n: int = 1000, semilla: int = 0) -> np.ndarray:
        """Incertidumbre (1σ) del valor interpolado en x."""
        return self.monte_carlo(lambda g: g(x), n=n, semilla=semilla).sigma

    @property
    def con_errores(self) -> bool:
        return self.dy is not None or self.dx is not None

    def evaluar(self, xs, n: int = 1000, semilla: int = 0):
        """Tabla con x, f(x), σ_f, f'(x) y σ_f' (σ por Monte Carlo si los datos tienen
        incertidumbre; NaN si no). Fuera del rango, sin extrapolar, todo NaN."""
        import pandas as pd

        xs = np.atleast_1d(np.asarray(xs, dtype=float))
        f = np.atleast_1d(self(xs))
        d1 = np.atleast_1d(self.derivada(xs))
        sf = np.full(xs.shape, np.nan)
        sd = np.full(xs.shape, np.nan)
        validos = np.isfinite(f)
        if self.con_errores and validos.any():
            xv = xs[validos]
            r = self.monte_carlo(lambda g: np.concatenate([g(xv), g.derivada(xv)]), n=n, semilla=semilla)
            sig = np.atleast_1d(r.sigma)
            sf[validos], sd[validos] = sig[: xv.size], sig[xv.size:]
        return pd.DataFrame({"x": xs, "f": f, "sigma_f": sf, "derivada": d1, "sigma_derivada": sd})

    def informe(self, xs=None, latex: bool = False, n: int = 500) -> str:
        """Resumen para pegar en un informe en lugar de los tramos: qué método, con
        cuántos puntos y en qué rango, cuánto vale la incertidumbre de la curva y,
        si se dan ``xs``, una tabla corta de valores interpolados."""
        from .estadistica import formatear

        lo, hi = self.rango
        nx, ny = self.nombre_x, self.nombre_y
        sx, sy, ux, uy = _simbolo(nx), _simbolo(ny), _unidad(nx), _unidad(ny)
        tramos = self.tramos()
        grado = max(t.grado for t in tramos)
        T = _tex if latex else (lambda t: t)

        def num(v, cifras=4, unidad=""):
            texto = f"${v:.{cifras}g}$" if latex else f"{v:.{cifras}g}"
            return f"{texto} {T(unidad)}" if unidad else texto

        metodo = _DESCRIPCION.get(self.metodo, METODOS[self.metodo])
        if self.metodo == "clamped" and self.opciones.get("derivadas_extremos"):
            d0, d1 = self.opciones["derivadas_extremos"]
            metodo += f" ({num(d0)} y {num(d1)})"
        if self.metodo == "suavizado":
            lam = self.opciones.get("suavizado")
            metodo += (f" con penalización λ = {num(lam)}" if lam is not None
                       else " con la penalización elegida por validación cruzada generalizada (GCV)")
        verbo = "Se ha ajustado" if self.metodo == "suavizado" else "Se ha interpolado"
        piezas = [f"{verbo} {T(sy)} en función de {T(sx)} con {metodo} a partir de {self.x.size} puntos "
                  f"experimentales, con {T(sx)} entre {num(lo)} y {num(hi, unidad=ux)}"
                  + (f" ({len(tramos)} tramos de grado {grado})." if len(tramos) > 1 else ".")]
        if self.metodo == "suavizado":
            res = self.y - self(self.x)
            piezas.append("La curva no pasa por los puntos: la desviación cuadrática media de los residuos es "
                          f"{num(float(np.sqrt(np.mean(res ** 2))), 2, uy)}.")
        if self.con_errores:
            malla = np.linspace(lo, hi, 101)
            try:
                s = np.atleast_1d(self.monte_carlo(lambda g: g(malla), n=n).sigma)
                piezas.append(f"Su incertidumbre se ha propagado por Monte Carlo ({n} réplicas de los datos dentro "
                              f"de sus incertidumbres): en el rango de los datos vale entre {num(float(s.min()), 2)} "
                              f"y {num(float(s.max()), 2, uy)} (mediana {num(float(np.median(s)), 2)}).")
            except ErrorInterpolacion:
                pass
        ext = self.extremos()
        if ext:
            piezas.append("Tiene " + _lista([f"un {t} en {T(sx)} = {num(xe, unidad=ux)} "
                                              f"({T(sy)} = {num(ye, unidad=uy)})" for xe, ye, t in ext[:4]]) + ".")
        texto = " ".join(piezas)
        if xs is None or len(np.atleast_1d(xs)) == 0:
            return texto + "\n"
        tabla = self.evaluar(xs, n=n)

        def valor(v, e):
            if not np.isfinite(v):
                return "—"
            return formatear(v, e, latex=latex) if np.isfinite(e) and e > 0 else f"{v:.6g}"

        simples = sx.isidentifier() and sy.isidentifier()
        if latex:
            derivada = rf"$\mathrm{{d}}{sy}/\mathrm{{d}}{sx}$" if simples else r"$\mathrm{d}y/\mathrm{d}x$"
            filas = [rf"    ${r.x:.6g}$ & ${valor(r.f, r.sigma_f)}$ & ${valor(r.derivada, r.sigma_derivada)}$ \\"
                     for r in tabla.itertuples()]
            return "\n".join([texto, "", r"\begin{table}[h]", r"  \centering",
                              r"  \begin{tabular}{ccc}", r"    \toprule",
                              rf"    {T(nx)} & {T(ny)} & {derivada} \\", r"    \midrule",
                              *filas, r"    \bottomrule", r"  \end{tabular}",
                              rf"  \caption{{Valores interpolados ({METODOS[self.metodo].lower()}).}}",
                              r"\end{table}"]) + "\n"
        derivada = f"d{sy}/d{sx}" if simples else "dy/dx"
        filas = [f"  {r.x:<12.6g} {valor(r.f, r.sigma_f):<26} {valor(r.derivada, r.sigma_derivada)}"
                 for r in tabla.itertuples()]
        return "\n".join([texto, "", f"  {nx:<12} {ny:<26} {derivada}", *filas]) + "\n"

    # -- tramos -------------------------------------------------------------
    def tramos(self) -> list[Tramo]:
        c, xs = self.pp.c, self.pp.x
        grado = c.shape[0] - 1
        salida = []
        for i in range(c.shape[1]):
            if xs[i + 1] <= xs[i]:
                continue  # tramos degenerados de longitud 0 (vienen de B-splines)
            coef = c[:, i].copy()
            # Anula el ruido de redondeo: términos cuya contribución en el tramo es
            # < 1e-12 de la mayor (|c_j|·h^pot tiene las unidades de y).
            h = xs[i + 1] - xs[i]
            aporte = np.abs(coef) * h ** np.arange(grado, -1, -1)
            coef[aporte < 1e-12 * aporte.max(initial=0)] = 0.0
            # recorta coeficientes de mayor grado nulos (p. ej. lineal guardado como cúbico)
            while coef.size > 1 and coef[0] == 0:
                coef = coef[1:]
            salida.append(Tramo(float(xs[i]), float(xs[i + 1]), coef))
        return salida

    def exportar_tramos(self, formato: str = "txt", cifras: int = 15) -> str:
        """Expresión de cada tramo en ``txt``, ``latex`` o ``csv``."""
        tramos = self.tramos()
        g = max(t.grado for t in tramos)
        v = self.nombre_x if self.nombre_x.isidentifier() else "x"

        def num(a):
            return f"{a:.{cifras}g}"

        if formato == "csv":
            cab = ",".join(["x_ini", "x_fin"] + [f"c{g - j}" for j in range(g + 1)])
            filas = [",".join([num(t.x_ini), num(t.x_fin)] + [num(a) for a in np.pad(t.coeficientes, (g - t.grado, 0))])
                     for t in tramos]
            return "\n".join([cab, *filas]) + "\n"

        def poli(t: Tramo, latex: bool) -> str:
            terminos = []
            for j, a in enumerate(t.coeficientes):
                pot = t.grado - j
                if a == 0:
                    continue
                base = f"({v} - {num(t.x_ini)})" if t.x_ini != 0 else v
                if pot == 0:
                    terminos.append(num(a))
                elif pot == 1:
                    terminos.append(f"{num(a)}{' ' if latex else '*'}{base}")
                else:
                    terminos.append(f"{num(a)}{' ' if latex else '*'}{base}{'^{' + str(pot) + '}' if latex else '**' + str(pot)}")
            return " + ".join(terminos).replace("+ -", "- ") or "0"

        if formato == "latex":
            filas = [rf"  {poli(t, True)} & {num(t.x_ini)} \le {v} \le {num(t.x_fin)} \\" for t in tramos]
            return "\n".join([rf"f({v}) = \begin{{cases}}", *filas, r"\end{cases}"]) + "\n"
        if formato == "txt":
            lineas = [f"# {METODOS[self.metodo]} — {len(tramos)} tramos",
                      f"# Tramo i:  C_i({v}) = Σ c_j·({v} − x_i)^j   para x_i ≤ {v} ≤ x_(i+1)"]
            lineas += [f"Tramo {i}: [{num(t.x_ini)}, {num(t.x_fin)}]   C({v}) = {poli(t, False)}"
                       for i, t in enumerate(tramos)]
            return "\n".join(lineas) + "\n"
        raise ErrorInterpolacion("Formato debe ser 'txt', 'latex' o 'csv'.")

    def resumen(self) -> str:
        lo, hi = self.rango
        lineas = [f"Interpolación: {METODOS[self.metodo]}",
                  f"Puntos: {self.x.size}   rango [{lo:.6g}, {hi:.6g}]   tramos: {len(self.tramos())}",
                  f"∫ f d{self.nombre_x} en el rango = {self.integral():.6g}"]
        ext = self.extremos()
        if ext:
            lineas.append("Extremos: " + ", ".join(f"{t} en ({xe:.6g}, {ye:.6g})" for xe, ye, t in ext))
        if self.avisos:
            lineas += ["Avisos:"] + [f"  - {a}" for a in self.avisos]
        return "\n".join(lineas)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def interpolar(
    datos: Datos,
    metodo: str = "natural",
    *,
    derivadas_extremos: tuple[float, float] | None = None,
    suavizado: float | None = None,
    extrapolar: bool = False,
) -> Interpolacion:
    """Construye una interpolación de los puntos incluidos de ``datos``.

    derivadas_extremos : (f'(x0), f'(xn)) para ``clamped``.
    suavizado : para ``suavizado``, la penalización de curvatura λ (por defecto se
        elige por GCV). Mayor λ ⇒ curva más suave.
    """
    metodo = metodo.lower()
    if metodo not in METODOS:
        raise ErrorInterpolacion(f"Método '{metodo}' desconocido. Opciones: {', '.join(METODOS)}.")
    d = datos.activos()
    x, y, dy, dx, fusionados = _fusionar_duplicados(d.x, d.y, d.dy, d.dx if d.tiene_dx else None)
    avisos = []
    if fusionados:
        avisos.append(f"{fusionados} puntos con x repetida se han promediado" + (" (ponderado por 1/σ²)." if dy is not None else "."))
    minimo = _MINIMO_PUNTOS.get(metodo, 2)
    if x.size < minimo:
        raise ErrorInterpolacion(f"'{metodo}' necesita al menos {minimo} puntos distintos (hay {x.size}).")
    if metodo == "periodico" and y[0] != y[-1]:
        tol = 3 * np.hypot(dy[0], dy[-1]) if dy is not None else 1e-9 * max(np.ptp(y), 1e-300)
        if abs(y[0] - y[-1]) > tol:
            raise ErrorInterpolacion("El spline periódico requiere y[0] = y[-1].")
        y = y.copy()
        y[0] = y[-1] = (y[0] + y[-1]) / 2
        avisos.append("Se han igualado el primer y el último valor para la condición periódica.")
    if metodo == "polinomio" and x.size > 10:
        avisos.append(f"Polinomio de grado {x.size - 1}: riesgo alto de oscilaciones de Runge entre nodos. "
                      "Usa un spline.")
    if metodo != "suavizado" and dy is not None:
        avisos.append("Un interpolante pasa por todos los puntos e ignora σ_y; con datos ruidosos usa "
                      "'suavizado' o un ajuste a un modelo.")
    opciones = {}
    if metodo == "clamped":
        opciones["derivadas_extremos"] = derivadas_extremos
    if metodo == "suavizado":
        opciones["suavizado"] = suavizado
    try:
        pp = _construir(x, y, metodo, dy=dy, **opciones)
    except ValueError as e:
        raise ErrorInterpolacion(str(e)) from e
    return Interpolacion(metodo, x, y, dy, dx, pp, opciones, d.nombre_x, d.nombre_y, extrapolar, avisos)
