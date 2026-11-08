# Base estadística

[← README](../README.md) · [Instalación](INSTALACION.md) · [Guía](GUIA.md) · **Base estadística** · [Terminal y Python](PYTHON.md) · [Desarrollo](DESARROLLO.md)

Qué calcula ajustelab y por qué, con las fórmulas. Para usarlo no hace falta leerlo entero, pero sí
conviene saber qué significan χ²_ν, el p-valor y el test de rachas antes de fiarse de un ajuste.

1. [Incertidumbres](#incertidumbres) · [Bondad del ajuste](#bondad-del-ajuste) · [Selección de modelo](#selección-de-modelo) · [Histogramas](#histogramas) · [Intersección](#intersección)
2. [Catálogo de modelos](#catálogo-de-modelos)
3. [Interpolación](#interpolación)
4. [Validación](#validación)
5. [Cambios respecto a `ProgramasUtiles.py`](#cambios-respecto-a-programasutilespy)
6. [Referencias](#referencias)


---

## Incertidumbres

| Datos | Método | Covarianza de los parámetros |
|---|---|---|
| σ_y | Mínimos cuadrados ponderados: minimiza $\chi^2=\sum_i\left(\frac{y_i-f(x_i;\mathbf p)}{\sigma_i}\right)^2$ | Absoluta: $C=(J^\mathsf{T}WJ)^{-1}$ |
| σ_x (y σ_y) | **Varianza efectiva** (Orear, 1982), iterada hasta converger: $\sigma_{\mathrm{ef},i}^2=\sigma_{y,i}^2+\left(\partial_x f\right)^2\sigma_{x,i}^2$ | Absoluta |
| Ninguna | Mínimos cuadrados ordinarios | Escalada por $s^2=\mathrm{RSS}/\nu$ (sin test χ²) |

- Los modelos lineales en los parámetros (polinomios, $a/x+b$...) se resuelven **de forma exacta**
  por SVD, sin valores iniciales.
- Los no lineales usan Levenberg–Marquardt con **jacobiano analítico** (SymPy) y **arranque múltiple**.
  Los valores iniciales se obtienen por *proyección variable*: se recorre una rejilla del parámetro no
  lineal (τ, ω...) y el resto se resuelve exactamente en cada punto.

## Bondad del ajuste

| Indicador | Interpretación |
|---|---|
| $\chi^2_\nu=\chi^2/\nu$, con $\nu=n-k$ | ≈ 1 → compatible; ≫ 1 → modelo incorrecto o σ subestimadas; ≪ 1 → σ sobreestimadas |
| $p=P(\chi^2_\nu\ge\chi^2_\text{obs})$ | p < 0.01 → incompatible; p > 0.99 → σ sospechosamente grandes |
| **Test de rachas** (Wald–Wolfowitz, distribución exacta) | Pocas rachas de residuos del mismo signo → **falta un término en el modelo**, aunque χ²_ν parezca bueno |
| Shapiro–Wilk (n ≥ 8) | Residuos no normales → posibles atípicos |
| Durbin–Watson | ≈ 2 si los residuos no están autocorrelacionados |
| Correlación $\rho_{ij}=C_{ij}/\sqrt{C_{ii}C_{jj}}$ | \|ρ\| > 0.95 → parámetros casi degenerados (conviene centrar x o reparametrizar) |
| $R^2$ ponderado | Solo informativo; **no** sirve para comparar modelos no lineales |

Si p < 0.05 y atribuyes el exceso de χ² a errores subestimados, el informe da también las σ
multiplicadas por $\sqrt{\chi^2_\nu}$ (criterio del PDG).

**Bandas** (método delta): $\sigma_f^2(x)=J(x)\,C\,J(x)^\mathsf{T}$. La banda de predicción añade la
dispersión de una medida nueva.

**Redondeo** (regla del PDG): se miran las tres primeras cifras del error. De 100 a 354 → 2 cifras
significativas; de 355 a 949 → 1 cifra; de 950 a 999 → se sube a 1000 con 2 cifras. El valor se
redondea a la misma posición decimal: `3.14159 ± 0.0234 → 3.142 ± 0.023`.

## Selección de modelo

Elegir el modelo con menor χ² **siempre favorece al que tiene más parámetros**. Por eso se usa

```math
\mathrm{AICc}=\chi^2+2k+\frac{2k(k+1)}{n-k-1},\qquad \mathrm{BIC}=\chi^2+k\ln n,
\qquad w_i\propto e^{-\Delta_i/2}.
```

1. Se **excluyen** los ajustes que no convergen, los degenerados, los que tienen ν < 2, los que tienen
   datos fuera del dominio del modelo y los **físicamente implausibles** (un pico con el centro fuera
   del rango de x, una frecuencia por encima de Nyquist, una sigmoide que no se completa...).
2. Entre los modelos **compatibles** (p ≥ 0.01 y rachas p ≥ 0.05) se toma el de menor criterio. Si
   otros quedan a Δ < 2 (estadísticamente indistinguibles), se recomienda el de **menos parámetros**.

> **La recomendación es estadística, no física.** Si la teoría predice un modelo, usa ese. En la
> validación (abajo), los fallos son siempre un modelo con un parámetro de más que absorbe ruido.

## Histogramas

- **Intervalos**: Freedman–Diaconis, $h=2\,\mathrm{IQR}\,n^{-1/3}$; Scott, $h=3.49\,s\,n^{-1/3}$;
  Sturges, $k=\lceil\log_2 n\rceil+1$ (solo razonable con pocos datos normales); $\sqrt n$. Si el IQR
  es 0 (muchos valores repetidos) se usa Sturges. Como mucho 500 intervalos.
- **Errores**: $\sqrt N$ en cada intervalo. Con $N=0$ la barra es 0, lo que no significa que no haya
  incertidumbre: ahí $\sqrt N$ deja de ser una buena aproximación.
- **Ajuste** por máxima verosimilitud con los **datos sin agrupar** (no con el histograma, que pierde
  información y depende de los intervalos): normal, $\hat\mu=\bar x\pm s/\sqrt n$ y
  $\hat\sigma=s\pm s/\sqrt{2(n-1)}$; Poisson, $\hat\lambda=\bar x\pm\sqrt{\hat\lambda/n}$; exponencial,
  $\hat\tau=\bar x\pm\hat\tau/\sqrt n$.
- **Test χ² de Pearson**: los intervalos de los extremos se extienden hasta el final del soporte y se
  agrupan intervalos vecinos hasta que cada grupo espera al menos 5 entradas;
  $\nu=k-1-(\text{parámetros estimados})$. Al estimar con los datos sin agrupar el p-valor es algo
  optimista (Chernoff–Lehmann), poco con muchos intervalos. En la validación, con datos que siguen la
  distribución, $p<0.05$ sale en el 5 % de los casos para las tres distribuciones.

## Intersección

Para $g(x^*;\mathbf p_1,\mathbf p_2)=f_1-f_2=0$, el teorema de la función implícita da
$\partial x^*/\partial\mathbf p_1=-(\partial f_1/\partial\mathbf p_1)/g'$ y
$\partial x^*/\partial\mathbf p_2=(\partial f_2/\partial\mathbf p_2)/g'$. La covarianza de $(x^*,y^*)$
es $G\,\mathrm{diag}(C_1,C_2)\,G^\mathsf{T}$. La elipse del 68 % usa $\Delta\chi^2=2.30$ (dos grados de
libertad); la elipse «de 1σ» por eje solo contiene el 39 %. Se supone que los dos conjuntos son
independientes.

---

## Catálogo de modelos

| Clave | Modelo | Expresión |
|---|---|---|
| `constante` | Constante | $c$ |
| `proporcional` | Proporcional | $ax$ |
| `lineal` | Lineal | $ax+b$ |
| `cuadratico` | Cuadrático | $ax^2+bx+c$ |
| `cubico` | Polinomio de grado 3 | $c_0+c_1x+c_2x^2+c_3x^3$ |
| `inversa` | Inversa | $a/x+b$ |
| `inversa_cuadrado` | Inversa del cuadrado | $a/x^2+b$ |
| `raiz` | Raíz cuadrada | $a\sqrt{x}+b$ |
| `logaritmica` | Logarítmica | $a\ln x+b$ |
| `exponencial` | Exponencial | $Ae^{bx}$ |
| `exponencial_fondo` | Exponencial con fondo | $Ae^{-x/\tau}+C$ |
| `carga` ¹ | Carga de un condensador | $A(1-e^{-x/\tau})+C$ |
| `doble_exponencial` | Doble exponencial ($t_1<t_2$) | $A_1e^{-x/t_1}+A_2e^{-x/t_2}+C$ |
| `arrhenius` | Arrhenius | $Ae^{-b/x}$ |
| `potencia` | Potencia | $Ax^b$ |
| `potencia_fondo` | Potencia con fondo | $Ax^b+C$ |
| `gaussiana` | Gaussiana | $Ae^{-(x-\mu)^2/2s^2}+C$ |
| `lorentziana` | Lorentziana | $A\gamma^2/((x-x_0)^2+\gamma^2)+C$ |
| `logistica` | Logística (sigmoide) | $L/(1+e^{-k(x-x_0)})+C$ |
| `seno` | Sinusoidal | $A\sin(\omega x+\varphi)+C$ |
| `seno_amortiguado` | Oscilación amortiguada | $Ae^{-gx}\sin(\omega x+\varphi)+C$ |
| `malus` ¹ | Ley de Malus (rad) | $I_0\cos^2(x-t_0)+C$ |
| `malus_grados` ¹ | Ley de Malus (grados) | $I_0\cos^2(\pi(x-t_0)/180)+C$ |

¹ No entran en la selección automática: `carga` es la misma curva que `exponencial_fondo`, y Malus es
demasiado específico. Se pueden añadir con el campo *modelos propios* (o `--extra`). Los polinomios de
cualquier grado se piden como `polinomio_5`.

**Modelos propios**: cualquier expresión en `x` con `+ - * / ** ^`, las funciones
`exp log ln log10 sqrt sin cos tan asin acos atan sinh cosh tanh abs erf` y las constantes `pi` y `e`.
Cualquier otro nombre es un parámetro, incluidos `gamma`, `beta`, `E` o `I`.

---

## Interpolación

Un interpolante **pasa por todos los puntos e ignora las incertidumbres**: úsalo para tablas y
calibraciones sin ruido. Con datos ruidosos usa el *spline de suavizado* o, mejor aún, un ajuste.

| Método | Cuándo usarlo |
|---|---|
| `lineal` | Muchos puntos, o cuando no quieres introducir curvatura |
| `natural` | Spline cúbico con f″ = 0 en los extremos |
| `not-a-knot` | Spline cúbico por defecto de SciPy; reproduce exactamente un cúbico |
| `clamped` | Conoces f′ en los extremos |
| `periodico` | Datos periódicos (y₀ = yₙ) |
| `pchip` | Datos monótonos: no sobreoscila |
| `akima`, `makima` | Robustos frente a un punto que se sale de la tendencia |
| `suavizado` | Datos con ruido: spline penalizado, pesos 1/σ² y λ por validación cruzada |
| `polinomio` | Pocos puntos (fenómeno de Runge con más de 10) |

La interpolación también da su **incertidumbre** cuando los datos la tienen: se generan muchos
conjuntos de datos perturbados con sus σ (Monte Carlo), se interpola cada uno y la desviación típica
de los resultados es la σ de f(x), f′(x), la inversa o la integral. Sin incertidumbres en los datos,
solo se da el valor.

En un informe no hace falta pegar los tramos del spline: basta con decir qué método se usó, con
cuántos puntos y en qué rango, y dar una tabla corta de valores. Es lo que escribe *Resumen para el
informe* (y `Interpolacion.informe()` desde Python).

---

## Validación

La batería de tests (`pytest`, más de 300 pruebas) comprueba, entre otras cosas:

- **Frente a soluciones conocidas**: fórmulas cerradas de la recta ponderada, `numpy.polyfit`,
  `scipy.optimize.curve_fit`, la varianza efectiva para una recta (que es analítica), la
  distribución exacta de rachas frente a la enumeración de todos los casos, y el redondeo PDG.
- **Monte Carlo de las incertidumbres**: en cientos de conjuntos sintéticos, los *pulls*
  $(\hat p-p_\text{real})/\sigma_p$ siguen una $N(0,1)$, $\langle\chi^2_\nu\rangle\approx1$ y los
  p-valores son uniformes. Esto se comprueba para mínimos cuadrados ponderados, ajustes no lineales,
  varianza efectiva y mínimos cuadrados ordinarios (cobertura de la t de Student).
- **Catálogo**: los 23 modelos recuperan sus parámetros verdaderos dentro de 4σ.
- **Selección**: acierta el modelo verdadero en ≈ 95 % de los casos (23 familias, varias semillas).
- **Intersección**: los pulls de x* e y* y su correlación coinciden con la covarianza calculada; la
  elipse del 68 % contiene el 68.3 % de los puntos simulados.
- **Histogramas**: las reglas de intervalos coinciden con las de NumPy; los ajustes recuperan sus
  parámetros y, con datos que siguen la distribución, el p-valor del test χ² es uniforme (p < 0.05 en
  ≈ 5 % de 400 conjuntos) para la normal, la Poisson y la exponencial.
- **Interfaz**: arranque, temas, apertura, ajuste, clic para excluir, selección con cancelación,
  interpolación, intersección, pegado, columnas de texto, todos los tipos de gráfica, eje partido,
  arrastre y edición de título, leyenda, etiquetas y textos, plantillas, marcas, rango escrito, guardar una
  parte de los datos, evaluar y resumir la interpolación y exportación, todo sin pantalla.

La CI de GitHub ejecuta los tests en **Ubuntu, Windows y macOS** con Python 3.10, 3.13 y 3.14, y construye
y prueba los ejecutables de cada sistema (ver [Desarrollo](DESARROLLO.md)).

---

## Cambios respecto a `ProgramasUtiles.py`

El script original se conserva en `legacy/`. Tenía fallos que **afectan a los resultados**:

| Opción antigua | Fallo | Ahora |
|---|---|---|
| 6 (y = ax) | Calculaba `a` con las fórmulas de y = ax + b y descartaba `b`, con ν = N−2. Con datos y = 2x + 5 daba a = 2.000 en vez de 2.714. **Si la usaste en un informe, revísalo.** | `ajustar(datos, "proporcional")`: a = Σwxy/Σwx², ν = n−1 |
| 4 (intersección) | El cálculo estaba indentado dentro de otra función y nunca se ejecutaba; además, la covarianza salía escalar | Intersección de cualquier par de modelos con covarianza 2×2 y elipse correcta |
| 1, 2, 3, 8 | σx se leía pero no se usaba; χ² sin ν ni p-valor; curva dibujada uniendo los puntos | Varianza efectiva, bondad completa, curva suave con banda |
| 7 (spline) | Un CSV de 4 columnas se leía mal; cabecera repetida en cada tramo | Diez métodos y exportación de tramos en txt, LaTeX y CSV |
| 8 (no lineal) | Un solo parámetro, `eval` sin control y p0 = 1 | Expresiones con cualquier número de parámetros, valores iniciales automáticos y arranque múltiple |

`scipy.odr`, que usaba la opción 4, está obsoleto desde SciPy 1.17 y desaparece en la 1.19.

---

## Referencias

- J. Orear, *Least squares when both variables have uncertainties*, Am. J. Phys. **50**, 912 (1982).
- Particle Data Group, *Review of Particle Physics*, capítulos «Introduction» (redondeo, factor de
  escala) y «Statistics».
- K. P. Burnham y D. R. Anderson, *Model Selection and Multimodel Inference*, Springer (2002).
- A. Wald y J. Wolfowitz, *On a test whether two samples are from the same population*,
  Ann. Math. Statist. **11**, 147 (1940).
- P. R. Bevington y D. K. Robinson, *Data Reduction and Error Analysis for the Physical Sciences*.
