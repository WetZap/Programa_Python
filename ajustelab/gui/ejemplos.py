"""Conjuntos de datos de ejemplo (sintéticos, generados al vuelo) para probar
la aplicación sin tener un fichero a mano. Cada uno ilustra una pestaña."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _descarga(rng):
    t = np.linspace(0.2, 6, 16)
    t_real = t + rng.normal(0, 0.02, t.size)
    V = 4.8 * np.exp(-t_real / 1.7) + 0.35 + rng.normal(0, 0.04, t.size)
    return pd.DataFrame({"t (s)": t.round(4), "V (V)": V.round(4), "dt": 0.02, "dV": 0.04})


def _pico(rng):
    lam = np.linspace(580, 600, 41)
    verdad = 120 * np.exp(-(lam - 589.3) ** 2 / (2 * 1.8**2)) + 15
    dI = np.sqrt(verdad)
    return pd.DataFrame({"lambda (nm)": lam, "I": (verdad + rng.normal(0, dI)).round(1), "dI": dI.round(2)})


def _rectas(rng):
    x = np.r_[np.linspace(0, 5, 8), np.linspace(6, 12, 8)]
    y = np.r_[1.8 * x[:8] + 2, -0.7 * x[8:] + 21] + rng.normal(0, 0.15, 16)
    return pd.DataFrame({"x": x.round(4), "y": y.round(4), "dy": 0.15})


def _pendulo(rng):
    t = np.linspace(0, 12, 70)
    th = 0.35 * np.exp(-0.18 * t) * np.sin(2.6 * t + 0.4) + rng.normal(0, 0.008, t.size)
    return pd.DataFrame({"t (s)": t.round(4), "theta (rad)": th.round(5), "dtheta": 0.008})


def _calibracion(rng):
    T = np.arange(0, 401, 25.0)
    mV = 0.0395 * T + 2.4e-5 * T**2 - 1.1e-8 * T**3  # curva suave, sin ruido apreciable
    return pd.DataFrame({"T (°C)": T, "E (mV)": mV.round(4)})


EJEMPLOS = {
    "descarga": ("Descarga de un condensador (exponencial con fondo)", _descarga),
    "pico": ("Pico espectral (gaussiana con σ = √N)", _pico),
    "pendulo": ("Péndulo amortiguado (oscilación)", _pendulo),
    "rectas": ("Dos tramos rectos (intersección, n = 8)", _rectas),
    "calibracion": ("Tabla de calibración (interpolación)", _calibracion),
}


def nombres() -> dict[str, str]:
    return {k: v[0] for k, v in EJEMPLOS.items()}


def generar(clave: str, semilla: int = 7) -> tuple[pd.DataFrame, str]:
    nombre, f = EJEMPLOS[clave]
    return f(np.random.default_rng(semilla)), f"Ejemplo sintético: {nombre}"
