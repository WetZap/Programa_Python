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


def _carga(rng):
    """Carga de un condensador: tensión (V) y corriente (mA) frente al tiempo, con
    escalas muy distintas: para «Representar» con dos ejes y."""
    t = np.linspace(0, 10, 26)
    tau, V0, R = 2.2, 9.0, 4.7  # s, V, kΩ
    V = V0 * (1 - np.exp(-t / tau)) + rng.normal(0, 0.2, t.size)
    I = V0 / R * np.exp(-t / tau) + rng.normal(0, 0.04, t.size)  # mA
    return pd.DataFrame({"t (s)": t.round(3), "V (V)": V.round(3), "dV": 0.2, "I (mA)": I.round(4), "dI": 0.04})


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


def _medidas(rng):
    """Medidas repetidas: el periodo de un péndulo medido por dos grupos (con
    distinto número de medidas) y las cuentas de un contador Geiger en 1 s."""
    n_a, n_b, n_c = 60, 45, 80
    filas = max(n_a, n_b, n_c)

    def columna(v):
        return np.r_[v, np.full(filas - v.size, np.nan)]

    return pd.DataFrame({
        "T grupo A (s)": columna(rng.normal(2.006, 0.025, n_a).round(3)),
        "T grupo B (s)": columna(rng.normal(2.021, 0.045, n_b).round(3)),
        "Cuentas en 1 s": columna(rng.poisson(4.2, n_c).astype(float)),
    })


def _composicion(rng):
    """Composición de una aleación (fracción en masa) con su incertidumbre:
    columna de etiquetas (texto) para barras y sectores."""
    metales = ["Cu", "Zn", "Pb", "Sn", "Fe", "Ni"]
    f = np.array([0.585, 0.352, 0.031, 0.018, 0.009, 0.005])
    f = f * (1 + rng.normal(0, 0.01, f.size))
    return pd.DataFrame({"Metal": metales, "Fracción": (f / f.sum()).round(4),
                         "dF": np.maximum(0.002, 0.02 * f).round(4)})


def _malus(rng):
    """Ley de Malus: intensidad tras un polarizador frente al ángulo (polar)."""
    th = np.arange(0, 360, 10.0)
    I = 95 * np.cos(np.radians(th - 20)) ** 2 + 4
    return pd.DataFrame({"θ (°)": th, "I (u.a.)": (I + rng.normal(0, 2, th.size)).round(1), "dI": 2.0})


def _dos_tandas(rng):
    """Enfriamiento medido en dos tandas separadas por una pausa: el eje x se
    parte para no dejar un hueco vacío en medio de la gráfica."""
    t = np.r_[np.arange(0, 12.5, 1.0), np.arange(60, 72.5, 1.0)]
    T = 21 + 64 * np.exp(-t / 22) + rng.normal(0, 0.3, t.size)
    return pd.DataFrame({"t (min)": t, "T (°C)": T.round(2), "dT": 0.3})


EJEMPLOS = {
    "carga": ("Carga de un condensador: V e I frente a t (dos ejes)", _carga),
    "descarga": ("Descarga de un condensador (exponencial con fondo)", _descarga),
    "pico": ("Pico espectral (gaussiana con σ = √N)", _pico),
    "pendulo": ("Péndulo amortiguado (oscilación)", _pendulo),
    "rectas": ("Dos tramos rectos (intersección, n = 8)", _rectas),
    "calibracion": ("Tabla de calibración (interpolación)", _calibracion),
    "medidas": ("Medidas repetidas: histograma con ajuste gaussiano", _medidas),
    "composicion": ("Composición de una aleación (barras y sectores)", _composicion),
    "malus": ("Ley de Malus: intensidad frente al ángulo (polar)", _malus),
    "dos_tandas": ("Enfriamiento en dos tandas (eje x partido)", _dos_tandas),
}


def nombres() -> dict[str, str]:
    return {k: v[0] for k, v in EJEMPLOS.items()}


def generar(clave: str, semilla: int = 7) -> tuple[pd.DataFrame, str]:
    nombre, f = EJEMPLOS[clave]
    return f(np.random.default_rng(semilla)), f"Ejemplo sintético: {nombre}"
