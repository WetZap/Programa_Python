"""Selección automática del modelo que mejor describe los datos.

Procedimiento
-------------
1. Se ajustan todos los candidatos (por defecto :data:`CANDIDATOS_AUTO`, más los
   modelos propios que se pasen en ``extra``).
2. **Exclusión** (el ajuste no es utilizable): error o no convergencia,
   parámetros degenerados, covarianza no finita, datos fuera del dominio,
   ν < ``nu_min`` o resultado físicamente implausible (pico fuera del rango,
   frecuencia por encima de Nyquist...).
3. **Clasificación** de los válidos por AICc (o BIC):
   AICc = χ² + 2k + 2k(k+1)/(n−k−1),  BIC = χ² + k·ln n,
   con ΔAICc respecto al mejor y pesos de Akaike w ∝ exp(−Δ/2).
   No se usa el χ² a secas porque siempre gana el modelo con más parámetros.
4. **Recomendación**: entre los modelos compatibles con los datos (p ≥ 0.01 y
   test de rachas p ≥ 0.05) se toma el de menor criterio; si otros quedan a
   Δ < 2 (estadísticamente indistinguibles) se elige el de **menos parámetros**.

La clasificación es estadística: si la teoría predice un modelo concreto, ese
es el que hay que usar aunque otro tenga mejor AICc.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .ajuste import METODO_OLS, METODO_VE, ErrorAjuste, ResultadoAjuste, ajustar
from .datos import Datos
from .estadistica import Bondad
from .modelos import ErrorModelo, Modelo, clave_de, obtener

__all__ = ["CANDIDATOS_AUTO", "Candidato", "Seleccion", "seleccionar"]

#: Modelos que compiten en la selección automática. Quedan fuera los
#: equivalentes a otro (``carga`` ≡ ``exponencial_fondo``) y los muy
#: específicos (Malus), que se pueden añadir con ``extra``.
CANDIDATOS_AUTO: tuple[str, ...] = (
    "constante", "proporcional", "lineal", "cuadratico", "cubico",
    "inversa", "inversa_cuadrado", "raiz", "logaritmica",
    "exponencial", "exponencial_fondo", "doble_exponencial", "arrhenius",
    "potencia", "potencia_fondo",
    "gaussiana", "lorentziana", "logistica", "seno", "seno_amortiguado",
)


@dataclass
class Candidato:
    clave: str
    modelo: Modelo
    resultado: ResultadoAjuste | None = None
    bondad: Bondad | None = None
    valido: bool = False
    motivo: str = ""  # por qué se ha excluido
    advertencias: list[str] = field(default_factory=list)
    criterio: float = math.inf
    delta: float = math.inf
    peso: float = 0.0

    @property
    def compatible(self) -> bool:
        """Compatible con los datos: p ≥ 0.01 (si hay σ) y rachas p ≥ 0.05."""
        if not self.valido or self.bondad is None:
            return False
        b = self.bondad
        ok_chi2 = not np.isfinite(b.p_valor) or b.p_valor >= 0.01
        ok_rachas = not np.isfinite(b.rachas.p) or b.rachas.p >= 0.05
        return ok_chi2 and ok_rachas


@dataclass
class Seleccion:
    candidatos: list[Candidato]
    recomendado: Candidato | None
    criterio: str
    datos: Datos
    avisos: list[str] = field(default_factory=list)

    @property
    def validos(self) -> list[Candidato]:
        return [c for c in self.candidatos if c.valido]

    @property
    def excluidos(self) -> list[Candidato]:
        return [c for c in self.candidatos if not c.valido]

    def __getitem__(self, clave: str) -> Candidato:
        for c in self.candidatos:
            if c.clave == clave:
                return c
        raise KeyError(clave)

    def tabla(self) -> pd.DataFrame:
        """Tabla de clasificación (válidos ordenados, luego excluidos)."""
        filas = []
        for c in self.candidatos:
            b = c.bondad
            filas.append({
                "clave": c.clave,
                "modelo": c.modelo.nombre,
                "k": c.modelo.k,
                "chi2_red": b.chi2_red if b else np.nan,
                "p": b.p_valor if b else np.nan,
                "rachas_p": b.rachas.p if b else np.nan,
                self.criterio.upper(): c.criterio if c.valido else np.nan,
                "delta": c.delta if c.valido else np.nan,
                "peso": c.peso if c.valido else np.nan,
                "recomendado": c is self.recomendado,
                "estado": "válido" if c.valido else f"excluido: {c.motivo}",
                "advertencias": "; ".join(c.advertencias),
            })
        return pd.DataFrame(filas)

    def resumen(self, maximo: int = 12) -> str:
        nombre_crit = "AICc" if self.criterio == "aicc" else "BIC"
        lineas = [f"Selección de modelo por {nombre_crit}  (n = {self.datos.n}, {len(self.validos)} válidos de "
                  f"{len(self.candidatos)})", ""]
        cab = f"  {'':2}{'Modelo':<26}{'k':>2}{'χ²_ν':>9}{'p':>9}{'rachas p':>10}{'Δ' + nombre_crit:>9}{'peso':>7}"
        lineas += [cab, "  " + "─" * (len(cab) - 2)]
        for c in self.validos[:maximo]:
            b = c.bondad
            marca = "★" if c is self.recomendado else ("·" if c.compatible else "✗")
            lineas.append(f"  {marca:<2}{c.modelo.nombre[:25]:<26}{c.modelo.k:>2}{b.chi2_red:>9.3g}{b.p_valor:>9.2g}"
                          f"{b.rachas.p:>10.2g}{c.delta:>9.2f}{c.peso:>7.3f}")
        if len(self.validos) > maximo:
            lineas.append(f"  ... y {len(self.validos) - maximo} más")
        lineas.append("  ★ recomendado   · compatible   ✗ incompatible (p < 0.01 o rachas p < 0.05)")
        if self.excluidos:
            lineas += ["", "Excluidos:"] + [f"  - {c.modelo.nombre}: {c.motivo}" for c in self.excluidos]
        if self.recomendado is not None:
            r = self.recomendado
            lineas += ["", f"Recomendado: {r.modelo.nombre}   y = {r.modelo.expresion}"]
            lineas += [f"  {n} = {v:.6g} ± {e:.2g}" for n, (v, e) in r.resultado.parametros.items()]
            if r.advertencias:
                lineas += [f"  ! {a}" for a in r.advertencias]
        if self.avisos:
            lineas += ["", "Avisos:"] + [f"  - {a}" for a in self.avisos]
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.resumen()


def _evaluar(clave: str, modelo: Modelo, datos: Datos, nu_min: int, criterio: str, **kw_ajuste) -> Candidato:
    c = Candidato(clave=clave, modelo=modelo)
    d = datos.activos()
    if d.n - modelo.k < nu_min:
        c.motivo = f"ν = {d.n - modelo.k} < {nu_min} (pocos puntos para {modelo.k} parámetros)"
        return c
    if not modelo.dominio_valido(d.x):
        c.motivo = f"datos fuera del dominio ({modelo.texto_dominio})"
        return c
    try:
        res = ajustar(datos, modelo, **kw_ajuste)
    except (ErrorAjuste, ValueError, np.linalg.LinAlgError, FloatingPointError) as e:
        c.motivo = f"error en el ajuste: {e}"
        return c
    c.resultado = res
    if any("degenerados" in a for a in res.avisos):
        c.motivo = "parámetros degenerados (no determinados por los datos)"
        return c
    if not res.convergido:
        c.motivo = "no converge"
        return c
    if not np.all(np.isfinite(res.cov)):
        c.motivo = "covarianza no finita"
        return c
    implausible = modelo.comprobar_plausibilidad(res.p, d.x)
    if implausible:
        c.motivo = f"implausible: {implausible}"
        return c

    b = res.bondad()
    c.bondad = b
    c.valido = True
    c.criterio = b.aicc if criterio == "aicc" else b.bic
    no_signif = [n for n, v, e in zip(res.nombres, res.p, res.sigma_p) if abs(v) < e]
    if no_signif:
        c.advertencias.append(f"{', '.join(no_signif)} compatible(s) con 0 (|p| < σ)")
    if np.isfinite(b.p_valor) and b.p_valor < 0.01:
        c.advertencias.append(f"incompatible con los datos (p = {b.p_valor:.2g})")
    if np.isfinite(b.rachas.p) and b.rachas.p < 0.05:
        c.advertencias.append(f"residuos con estructura (rachas p = {b.rachas.p:.2g})")
    for i in range(modelo.k):
        for j in range(i + 1, modelo.k):
            if abs(b.correlacion[i, j]) > 0.99:
                c.advertencias.append(f"{res.nombres[i]}–{res.nombres[j]} casi degenerados (ρ = {b.correlacion[i, j]:+.3f})")
    return c


def seleccionar(
    datos: Datos,
    modelos: Iterable[str | Modelo] | None = None,
    *,
    extra: Iterable[str | Modelo] = (),
    criterio: str = "aicc",
    nu_min: int = 2,
    umbral_delta: float = 2.0,
    usar_dx: bool = True,
    n_inicios: int = 6,
    progreso: Callable[[int, int, str], None] | None = None,
) -> Seleccion:
    """Ajusta todos los candidatos y recomienda uno.

    Parámetros
    ----------
    modelos : claves del catálogo, expresiones o :class:`Modelo`. Por defecto
        :data:`CANDIDATOS_AUTO`.
    extra : modelos que se añaden a la lista (p. ej. tu modelo teórico).
    criterio : ``"aicc"`` (por defecto) o ``"bic"`` (penaliza más los parámetros).
    nu_min : grados de libertad mínimos para considerar un modelo.
    umbral_delta : Δ por debajo del cual dos modelos se consideran indistinguibles.
    progreso : ``progreso(i, total, nombre)`` para una barra de progreso.
    """
    criterio = criterio.lower()
    if criterio not in ("aicc", "bic"):
        raise ValueError("criterio debe ser 'aicc' o 'bic'.")

    lista: list[tuple[str, Modelo]] = []
    for m in list(modelos if modelos is not None else CANDIDATOS_AUTO) + list(extra):
        try:
            modelo = obtener(m) if isinstance(m, str) else m
        except ErrorModelo as e:
            raise ErrorModelo(f"Modelo '{m}': {e}") from e
        clave = clave_de(modelo) or (m if isinstance(m, str) else modelo.nombre)
        if all(clave != c for c, _ in lista):
            lista.append((clave, modelo))

    candidatos = []
    for i, (clave, modelo) in enumerate(lista):
        if progreso:
            progreso(i, len(lista), modelo.nombre)
        candidatos.append(_evaluar(clave, modelo, datos, nu_min, criterio, usar_dx=usar_dx, n_inicios=n_inicios))
    if progreso:
        progreso(len(lista), len(lista), "")

    validos = sorted((c for c in candidatos if c.valido), key=lambda c: c.criterio)
    excluidos = [c for c in candidatos if not c.valido]
    avisos: list[str] = []
    recomendado = None
    if validos:
        mejor = validos[0].criterio
        for c in validos:
            c.delta = c.criterio - mejor
        pesos = np.exp(-0.5 * np.array([c.delta for c in validos]))
        for c, w in zip(validos, pesos / pesos.sum()):
            c.peso = float(w)

        compatibles = [c for c in validos if c.compatible]
        grupo = compatibles or validos
        if not compatibles:
            avisos.append("Ningún modelo es compatible con los datos (χ² o test de rachas). Revisa las "
                          "incertidumbres, busca puntos atípicos o prueba un modelo propio.")
        minimo = min(c.criterio for c in grupo)
        cercanos = [c for c in grupo if c.criterio - minimo < umbral_delta]
        recomendado = min(cercanos, key=lambda c: (c.modelo.k, c.criterio))
        if len(cercanos) > 1:
            nombres = ", ".join(c.modelo.nombre for c in cercanos)
            avisos.append(f"Indistinguibles (Δ < {umbral_delta:g}): {nombres}. Se recomienda el de menos "
                          "parámetros; elige según la física del experimento.")
        if recomendado is not validos[0]:
            avisos.append(f"El de menor {criterio.upper()} es '{validos[0].modelo.nombre}', pero se recomienda "
                          f"'{recomendado.modelo.nombre}' por " + ("compatibilidad con los datos."
                          if validos[0] not in grupo else "parsimonia (menos parámetros)."))
    else:
        avisos.append("Ningún modelo ha producido un ajuste válido.")

    metodo = next((c.resultado.metodo for c in validos if c.resultado), None)
    if metodo == METODO_VE:
        avisos.append("Con σ_x, la varianza efectiva usa pesos que dependen del modelo: la comparación entre "
                      "modelos es aproximada.")
    elif metodo == METODO_OLS:
        avisos.append("Sin incertidumbres no se puede saber si un modelo es compatible con los datos; la "
                      "clasificación solo compara la dispersión de los residuos.")
    return Seleccion(candidatos=validos + excluidos, recomendado=recomendado, criterio=criterio, datos=datos,
                     avisos=avisos)
