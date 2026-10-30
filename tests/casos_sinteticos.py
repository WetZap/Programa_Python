"""Casos sintéticos: para cada modelo del catálogo, x, parámetros verdaderos y σ_y."""
import numpy as np
# clave: (x, parámetros verdaderos, sigma)
L = np.linspace
CASOS = {
 "constante": (L(0,10,20), [3.0], 0.1),
 "proporcional": (L(1,10,15), [2.5], 0.2),
 "lineal": (L(0,10,15), [2.0, -3.0], 0.2),
 "cuadratico": (L(-5,5,20), [0.7, -1.0, 2.0], 0.3),
 "cubico": (L(-3,3,25), [1.0, -2.0, 0.5, 0.4], 0.2),
 "inversa": (L(0.5,5,20), [4.0, 1.0], 0.1),
 "inversa_cuadrado": (L(0.5,5,20), [3.0, 0.5], 0.05),
 "raiz": (L(0,25,20), [2.0, 1.0], 0.2),
 "logaritmica": (L(0.5,50,20), [3.0, 2.0], 0.1),
 "exponencial": (L(0,4,20), [5.0, -0.8], 0.05),
 "exponencial_fondo": (L(0,6,25), [4.0, 1.3, 0.8], 0.05),
 "carga": (L(0,6,25), [5.0, 1.1, 0.3], 0.05),
 "doble_exponencial": (L(0,20,60), [5.0, 0.6, 2.0, 6.0, 0.2], 0.02),
 "arrhenius": (L(250,400,20), [1e4, 3000.0], 0.02),
 "potencia": (L(1,10,20), [2.0, 1.5], 0.2),
 "potencia_fondo": (L(1,10,25), [3.0, -1.2, 0.5], 0.02),
 "gaussiana": (L(-5,5,40), [10.0, 0.7, 1.1, 1.0], 0.2),
 "lorentziana": (L(-5,5,40), [8.0, 0.6, -0.4, 0.5], 0.2),
 "logistica": (L(0,10,30), [5.0, 2.0, 4.0, 1.0], 0.1),
 "seno": (L(0,10,50), [2.0, 3.1, 0.7, 0.5], 0.1),
 "seno_amortiguado": (L(0,10,80), [3.0, 0.3, 4.2, 1.0, 0.2], 0.05),
 "malus": (L(0,np.pi,25), [10.0, 0.4, 0.5], 0.2),
 "malus_grados": (L(0,180,25), [10.0, 25.0, 0.5], 0.2),
}

# Selección: equivalencias aceptadas (mismo modelo con otra parametrización)
EQUIVALENTES = {"carga": "exponencial_fondo", "malus": "seno", "malus_grados": "seno"}


def generar(clave, semilla=0):
    """Datos sintéticos (x, y, σ) del caso ``clave``."""
    from ajustelab import CATALOGO

    x, p, s = CASOS[clave]
    rng = np.random.default_rng(semilla)
    return x, CATALOGO[clave](x, *p) + rng.normal(0, s, x.size), s
