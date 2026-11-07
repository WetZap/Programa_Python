"""Punto de entrada de los ejecutables independientes (PyInstaller)."""
import multiprocessing
import sys

from ajustelab.lanzador import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
