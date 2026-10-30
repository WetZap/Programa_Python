"""Hace importable ``casos_sinteticos`` con cualquier modo de importación de pytest
(también al probar el paquete instalado con ``--import-mode=importlib``)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
