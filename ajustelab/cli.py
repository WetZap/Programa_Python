"""Uso de ajustelab desde la terminal (sin interfaz gráfica).

Ejemplos::

    ajustelab-cli medidas.csv                          # ajuste lineal
    ajustelab-cli medidas.csv -m exponencial_fondo -g ajuste.png
    ajustelab-cli medidas.csv -m "A*exp(-x/tau) + C" --p0 "5;1.5;0"
    ajustelab-cli medidas.csv --seleccionar            # prueba todo el catálogo
    ajustelab-cli medidas.dat --x t --y V --dy-cte 0.05 -i pchip --tramos tramos.tex
    ajustelab-cli --modelos                            # lista el catálogo

Las columnas se indican por nombre o por posición (0, 1, ...). Sin indicarlas se
usa la detección automática (x, y, dx, dy).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from . import __version__
from .ajuste import ErrorAjuste, ajustar
from .datos import ErrorDatos, a_datos, leer_tabla
from .interpolacion import METODOS, ErrorInterpolacion, interpolar
from .modelos import CATALOGO, ErrorModelo, obtener
from .seleccion import seleccionar


def _columna(valor: str | None):
    if valor is None:
        return None
    return int(valor) if valor.lstrip("-").isdigit() else valor


def _numero(valor: str) -> float:
    return float(valor.replace(",", "."))


def _figura(ruta: str, datos, resultado=None, interp=None, nivel: float = 0.6827) -> None:
    """Gráfica estática (sin Qt): datos, ajuste con banda y residuos."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    azul, naranja, aqua = "#2a78d6", "#eb6834", "#1baf7a"
    fig = Figure(figsize=(8, 6) if resultado is not None else (8, 4.8), layout="constrained")
    if resultado is not None:
        ax, axr = fig.subplots(2, 1, sharex=True, height_ratios=[3, 1])
    else:
        ax, axr = fig.subplots(1, 1), None
    d = datos.activos()
    ax.errorbar(d.x, d.y, xerr=d.dx if d.tiene_dx else None, yerr=d.dy, fmt="o", ms=5, color=azul, capsize=2,
                elinewidth=1, label="Datos", zorder=3)
    xx = np.linspace(d.x.min(), d.x.max(), 600)
    if resultado is not None:
        if nivel:
            f, lo, hi = resultado.banda(xx, nivel=nivel)
            ax.fill_between(xx, lo, hi, color=naranja, alpha=0.22, linewidth=0, label=f"Banda {nivel * 100:.0f} %")
        else:
            f = resultado.evaluar(xx)
        ax.plot(xx, f, color=naranja, linewidth=2, label=f"Ajuste: {resultado.modelo.nombre}")
        axr.axhline(0, color="0.2", linewidth=0.8)
        for k in (-2, 2):
            axr.axhline(k, color="0.7", linewidth=0.8, linestyle="--")
        axr.plot(resultado.datos.x, resultado.residuos_norm, "o", ms=4, color=azul)
        axr.set_ylabel("(y − f)/σ" if resultado.errores_absolutos else "(y − f)/s")
        axr.set_xlabel(d.nombre_x)
        axr.grid(True, alpha=0.4)
    else:
        ax.set_xlabel(d.nombre_x)
    if interp is not None:
        ax.plot(xx, interp(xx), color=aqua, linewidth=2, label=METODOS[interp.metodo])
    ax.set_ylabel(d.nombre_y)
    ax.grid(True, alpha=0.4)
    ax.legend()
    fig.savefig(ruta, dpi=300)


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ajustelab-cli", description="Ajuste de datos experimentales desde la terminal.",
                                epilog="Interfaz gráfica: ejecuta «ajustelab».")
    p.add_argument("fichero", nargs="?", help="fichero de datos (csv, dat, txt, xlsx, ods, json, npy, mat...)")
    p.add_argument("--version", action="version", version=f"ajustelab {__version__}")
    p.add_argument("--modelos", action="store_true", help="lista los modelos del catálogo y sale")
    g = p.add_argument_group("lectura")
    g.add_argument("--hoja", help="hoja de cálculo (nombre)")
    g.add_argument("--delimitador", help="fuerza el delimitador (por defecto se detecta)")
    g.add_argument("--decimal", choices=[".", ","], help="fuerza el separador decimal")
    g.add_argument("--x", help="columna x (nombre o posición)")
    g.add_argument("--y", help="columna y")
    g.add_argument("--dx", help="columna de σx")
    g.add_argument("--dy", help="columna de σy")
    g.add_argument("--dx-cte", type=_numero, help="σx constante para todos los puntos")
    g.add_argument("--dy-cte", type=_numero, help="σy constante para todos los puntos")
    g.add_argument("--excluir", help="filas a excluir (posiciones desde 0, separadas por comas)")
    g = p.add_argument_group("análisis")
    g.add_argument("-m", "--modelo", default="lineal", help="clave del catálogo o expresión (por defecto: lineal)")
    g.add_argument("--p0", help="valores iniciales separados por «;»")
    g.add_argument("--sin-dx", action="store_true", help="ignora σx aunque exista")
    g.add_argument("-s", "--seleccionar", action="store_true", help="prueba todo el catálogo y recomienda un modelo")
    g.add_argument("--criterio", choices=["aicc", "bic"], default="aicc")
    g.add_argument("--extra", help="modelos adicionales para --seleccionar, separados por «;»")
    g.add_argument("-i", "--interpolar", choices=list(METODOS), help="interpola en lugar de ajustar")
    g = p.add_argument_group("salida")
    g.add_argument("-g", "--grafica", help="guarda la gráfica (png, pdf, svg) a 300 ppp")
    g.add_argument("-o", "--informe", help="guarda el informe de texto")
    g.add_argument("--tramos", help="con --interpolar: exporta los tramos (.txt, .tex o .csv)")
    g.add_argument("--banda", type=float, default=0.6827, help="nivel de la banda de confianza (0 = sin banda)")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except BrokenPipeError:  # p. ej. «ajustelab-cli ... | head»: salida cortada, no es un error
        import os

        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


def _main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows: χ², ± al redirigir
    args = construir_parser().parse_args(argv)

    if args.modelos:
        for clave, m in CATALOGO.items():
            print(f"{clave:<20} {m.nombre:<30} y = {m.expresion}")
        return 0
    if not args.fichero:
        construir_parser().print_usage()
        print("ajustelab-cli: falta el fichero de datos (o usa --modelos).", file=sys.stderr)
        return 2

    try:
        tabla = leer_tabla(args.fichero, hoja=args.hoja, delimitador=args.delimitador, decimal=args.decimal)
        cols = [_columna(v) for v in (args.x, args.y, args.dx, args.dy)]
        if any(c is not None for c in cols[:2]) and None in cols[:2]:
            raise ErrorDatos("Indica a la vez --x y --y.")
        datos = a_datos(tabla, *cols, dx_constante=args.dx_cte, dy_constante=args.dy_cte)
        if args.excluir:
            datos.excluir([int(v) for v in args.excluir.split(",") if v.strip()])
        cabecera = [f"Fichero: {args.fichero}   {datos}", *datos.avisos, ""]

        resultado = interp = None
        if args.interpolar:
            interp = interpolar(datos, args.interpolar)
            texto = interp.resumen()
            if args.tramos:
                ext = Path(args.tramos).suffix.lower()
                formato = {".tex": "latex", ".csv": "csv"}.get(ext, "txt")
                Path(args.tramos).write_text(interp.exportar_tramos(formato), encoding="utf-8")
        elif args.seleccionar:
            extra = [t.strip() for t in (args.extra or "").split(";") if t.strip()]
            sel = seleccionar(datos, extra=extra, criterio=args.criterio, usar_dx=not args.sin_dx)
            resultado = sel.recomendado.resultado if sel.recomendado else None
            texto = sel.resumen() + ("\n\n" + resultado.resumen() if resultado else "")
        else:
            p0 = [_numero(v) for v in args.p0.split(";") if v.strip()] if args.p0 else None
            resultado = ajustar(datos, obtener(args.modelo), p0=p0, usar_dx=not args.sin_dx)
            texto = resultado.resumen()
    except (ErrorDatos, ErrorModelo, ErrorAjuste, ErrorInterpolacion, OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    informe = "\n".join(cabecera) + texto
    print(informe)
    if args.informe:
        Path(args.informe).write_text(informe + "\n", encoding="utf-8")
    if args.grafica:
        _figura(args.grafica, datos, resultado, interp, nivel=args.banda or None)
        print(f"\nGráfica guardada en {args.grafica}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
