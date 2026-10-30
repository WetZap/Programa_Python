# Escribire un programa que junte una multitud de programas
# utiles a lo largo de la carrera, se hara en forma de menu

# Importamos todos los modulos necesarios
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import matplotlib.transforms as transforms
from scipy.optimize import curve_fit
from scipy.interpolate import CubicSpline
from statistics import stdev
from statistics import mean
from scipy import odr
import argparse


# Funciones

def menu():
    print('---------------------------------------------------')
    print('------------------ MENÚ DE PROGRAMAS --------------')
    print('---------------------------------------------------')
    print('Seleccione una opción (o 0 para salir):')
    print('1. Ajuste lineal tipo y = ax con incertidumbre')
    print('2. Ajuste lineal tipo y = ax + b con incertidumbre')
    print('3. Ajuste lineal tipo y = ax² + bx + c con incertidumbre')
    print('4. Ajuste de dos conjuntos de datos y determinación de intersección (desarrollo)')
    print('5. Ajuste por minimos cuadrados (y = ax + b)')
    print('6. Ajuste por minimos cuadrados (y = ax)')
    print('7. Realizar un spline cubico a unos datos dados')
    print('8. Realizar un ajuste no lineal a unos datos dados')
    print('0. Salir')
    print('---------------------------------------------------')
    return input('Ingrese el número de la opción deseada: ')


'''
Lista de numeros para los programas, debera cambiar el valor de opción para ejecutar un programa u otro
1 Ajuste lineal tipo y = ax con incertidumbre
2 Ajuste lineal tipo y = ax + b con incertidumbre
3 Ajuste lineal tipo y = ax² + bx + c con incertidumbre
4 Ajuste de dos conjuntos de datos y determinación de intersección (desarrollo)
5 Ajuste por minimos cuadrados (y = ax + b)
6 Ajuste por minimos cuadrados (y = ax)
7 Realizar un spline cubico a unos datos dados
8 Realizar un ajuste no lineal a unos datos dados
0 Salir

'''
opcion = 1

# Esta sera la ruta en la que se encuentran los datos, el archivo debe estar en .csv
file_name = 'Datos.csv'


# Ahora escribiremos el delimitador, si lo has separado con espacios, con comas, con tabuladores:
delimitador = ','

# Nombre de la gráfica que se guardara.
nombre_graf = ''

# Decimal utilizado en el archivo de datos, por defecto es el punto:
decimal = '.'


# Variable para ajustes no lineales ( opción 8 ) la variable sera x con algun coeficiente 
# Ejemplo ax**2
expresion_no_lineal = ''

# Unidades ejex
unidad_ejex = r''
# Unidades ejey
unidad_ejey = r''

parser = argparse.ArgumentParser()
parser.add_argument("--file", type=str, required=True, help="Nombre del archivo de datos o ruta del archivo")
parser.add_argument("--out_name", type=str, help="Nombre del archivo de la gráfica de salida")
parser.add_argument("--deli", type=str,  help="Delimitador de los datos")
parser.add_argument("--dec", type=str, help="Decimal utilizado en el archivo de datos")
parser.add_argument("--exp", type=str, help="Expresión para ajuste no lineal escrito en operaciones de python (opción 8)")

args = parser.parse_args()
file_name = args.file
nombre_graf = args.out_name if args.out_name else 'grafica_salida.png'
delimitador = args.deli if args.deli else ','
decimal = args.dec if args.dec else '.'
expresion_no_lineal = args.exp if args.exp else ''


opcion = menu()
while opcion != "0":
    if opcion == "1":
        print('---------------------------------------------------')
        print('Escogió la opción 1, ajuste lineal tipo y = a * x: ')
        print('---------------------------------------------------')

        print(f"El archivo de datos debe tener la siguiente estructura:\nx{delimitador}y{delimitador}dx{delimitador}dy{delimitador}")
        
        ### Función de ajuste

        def func(x, a):
            return a*x

        ### Lectura de datos

        data = pd.read_csv(file_name, delimiter=delimitador, header=0, names=['x', 'y','dx', 'dy'],decimal=decimal)
        print(data)

        ### Ajuste

        popt, pcov = curve_fit(func, data.x, data.y, sigma=data.dy, absolute_sigma=True,maxfev=10000)

        y_pred = func(data.x, *popt)

        r = data.y - y_pred
        chisq = sum((r / data.dy) ** 2)
        mediax = mean(data.x)
        mediay = mean(data.y)

        mediaxy = mean(data.x*data.y)
        sigmax = stdev(data.x)
        sigmay = stdev(data.y)
        coef_Pearson = len(data.x)*(mediaxy-mediax*mediay)/((len(data.x)-1)*sigmax*sigmay)

        ### Salida de resultados

        print(f'   a: {popt[0]} \u00B1 {np.sqrt(pcov.diagonal())[0]}')
        print('')
        print(f'chi\u00b2: {chisq}')
        print('')
        print(f'media x: {mediax}')
        print(f'media y: {mediay}')
        print(f'media xy: {mediaxy}')
        print(f'Sigma x: {sigmax}')
        print(f'Sigma y: {sigmay}')
        print(f'Coeficiente de Pearson: {coef_Pearson}')

        ### Gráfica
        # - figure crea la figura con el tamaño indicado (los valores son en pulgadas y el valor por defecto de número de puntos por pulgada es 100).
        # - errorbar muestra los datos data.x y data.y con sus errores (data.dx y data.dy).
        #     - el formato es puntos de color azul: format='b.'
        #     - label es la etiqueta que aparecerá en la leyenda
        #     - definimos el grosor de las líneas con linewidth
        # - plot lo usamos para mostrar la recta de regresión.
        #     - Aquí indicamos que el formato es una línea roja: format='r-'
        # - xlim e ylim definen los límites de los ejes x e y respectivamente.
        # - xlabel e ylabel definen la etiqueta de los ejes x e y respectivamente
        #     - Podemos definir una etiqueta en formato LaTex poniendo r antes de la cadena de texto y la exprexión LaTex entre simbolos $ (mira ylabel)
        # - legend muestra la leyenda.

        fig=plt.figure(figsize=[18,12])
        ax=fig.gca()
        plt.errorbar(data.x, data.y, xerr=data.dx, yerr=data.dy, fmt='b.', label='Datos', linewidth=3)
        plt.plot(data.x, y_pred, 'g-', label='Ajuste',linewidth=4.0)


        plt.xlabel(unidad_ejex,fontsize=25)
        plt.ylabel(unidad_ejey,fontsize=25)
        plt.legend(loc='best',fontsize=25)
        plt.grid()

        # Este comando permite modificar el grosor de los ejes:
        for axis in ['top','bottom','left','right']:
            ax.spines[axis].set_linewidth(4)

        # Con estas líneas podemos dar formato a los "ticks" de los ejes:
        plt.tick_params(axis="x", labelsize=25, labelrotation=0, labelcolor="black")
        plt.tick_params(axis="y", labelsize=25, labelrotation=0, labelcolor="black")

        # Aquí dibuja el gráfico que hemos definido.
        plt.savefig(nombre_graf)
        plt.show()
        input("Presione Enter para continuar...")
        opcion = menu()
    elif opcion == "2":
        print('----------------------------------------------------')
        print('Escogio opción 2, ajuste lineal tipo y = a * x + b: ')
        print('----------------------------------------------------')

        print(f"El archivo de datos debe tener la siguiente estructura:\nx{delimitador}y{delimitador}dx{delimitador}dy{delimitador}")

        ### Función de ajuste

        def func(x, a, b):
            return a*x + b

        ### Lectura de datos

        data = pd.read_csv(file_name, delimiter=delimitador, header=0, names=['x', 'y','dx', 'dy'], decimal=decimal)
        print(data)

        ### Ajuste

        popt, pcov = curve_fit(func, data.x, data.y, sigma=data.dy, absolute_sigma=True,maxfev=10000)

        y_pred = func(data.x, *popt)

        r = data.y - y_pred
        chisq = sum((r / data.dy) ** 2)
        mediax = mean(data.x)
        mediay = mean(data.y)

        mediaxy = mean(data.x*data.y)
        sigmax = stdev(data.x)
        sigmay = stdev(data.y)
        coef_Pearson = len(data.x)*(mediaxy-mediax*mediay)/((len(data.x)-1)*sigmax*sigmay)

        ### Salida de resultados

        print(f'   a: {popt[0]} \u00B1 {np.sqrt(pcov.diagonal())[0]}')
        if popt.size > 1:
            print(f'   b: {popt[1]} \u00B1 {np.sqrt(pcov.diagonal())[1]}')

        print('')
        print(f'chi\u00b2: {chisq}')
        print('')
        print(f'media x: {mediax}')
        print(f'media y: {mediay}')
        print(f'media xy: {mediaxy}')
        print(f'Sigma x: {sigmax}')
        print(f'Sigma y: {sigmay}')
        print(f'Coeficiente de Pearson: {coef_Pearson}')

        ### Gráfica
        # - figure crea la figura con el tamaño indicado (los valores son en pulgadas y el valor por defecto de número de puntos por pulgada es 100).
        # - errorbar muestra los datos data.x y data.y con sus errores (data.dx y data.dy).
        #     - el formato es puntos de color azul: format='b.'
        #     - label es la etiqueta que aparecerá en la leyenda
        #     - definimos el grosor de las líneas con linewidth
        # - plot lo usamos para mostrar la recta de regresión.
        #     - Aquí indicamos que el formato es una línea roja: format='r-'
        # - xlim e ylim definen los límites de los ejes x e y respectivamente.
        # - xlabel e ylabel definen la etiqueta de los ejes x e y respectivamente
        #     - Podemos definir una etiqueta en formato LaTex poniendo r antes de la cadena de texto y la exprexión LaTex entre simbolos $ (mira ylabel)
        # - legend muestra la leyenda.

        fig=plt.figure(figsize=[18,12])
        ax=fig.gca()
        plt.errorbar(data.x, data.y, xerr=data.dx, yerr=data.dy, fmt='b.', label='Datos', linewidth=3)
        plt.plot(data.x, y_pred, 'g-', label='Ajuste',linewidth=4.0)


        plt.xlabel(unidad_ejex,fontsize=25)
        plt.ylabel(unidad_ejey,fontsize=25)
        plt.legend(loc='best',fontsize=25)
        plt.grid()

        # Este comando permite modificar el grosor de los ejes:
        for axis in ['top','bottom','left','right']:
            ax.spines[axis].set_linewidth(4)

        # Con estas líneas podemos dar formato a los "ticks" de los ejes:
        plt.tick_params(axis="x", labelsize=25, labelrotation=0, labelcolor="black")
        plt.tick_params(axis="y", labelsize=25, labelrotation=0, labelcolor="black")

        # Aquí dibuja el gráfico que hemos definido.
        plt.savefig(nombre_graf)
        plt.show()
        input("Presione Enter para continuar...")
        opcion = menu()

    elif opcion == "3":
        print('-------------------------------------------------------------')
        print('Escogio opción 3, ajuste lineal tipo y = a * x² + b * x + c: ')
        print('-------------------------------------------------------------')

        print(f"El archivo de datos debe tener la siguiente estructura:\nx{delimitador}y{delimitador}dx{delimitador}dy{delimitador}")

        ### Función de ajuste

        def func(x, a, b,c):
            return (a*(x**2) + (b*x) + c)

        ### Lectura de datos

        data = pd.read_csv(file_name, delimiter=delimitador, header=0, names=['x', 'y','dx', 'dy'], decimal=decimal)
        print(data)

        ### Ajuste

        popt, pcov = curve_fit(func, data.x, data.y, sigma=data.dy, absolute_sigma=True,maxfev=10000)

        y_pred = func(data.x, *popt)

        r = data.y - y_pred
        chisq = sum((r / data.dy) ** 2)
        mediax = mean(data.x)
        mediay = mean(data.y)

        mediaxy = mean(data.x*data.y)
        sigmax = stdev(data.x)
        sigmay = stdev(data.y)
        coef_Pearson = len(data.x)*(mediaxy-mediax*mediay)/((len(data.x)-1)*sigmax*sigmay)

        ### Salida de resultados

        print(f'   a: {popt[0]} \u00B1 {np.sqrt(pcov.diagonal())[0]}')
        if popt.size > 1:
            print(f'   b: {popt[1]} \u00B1 {np.sqrt(pcov.diagonal())[1]}')
        if popt.size >= 2:
            print(f'   c: {popt[2]} \u00B1 {np.sqrt(pcov.diagonal())[2]}')

        print('')
        print(f'chi\u00b2: {chisq}')
        print('')
        print(f'media x: {mediax}')
        print(f'media y: {mediay}')
        print(f'media xy: {mediaxy}')
        print(f'Sigma x: {sigmax}')
        print(f'Sigma y: {sigmay}')
        print(f'Coeficiente de Pearson: {coef_Pearson}')

        ### Gráfica
        # - figure crea la figura con el tamaño indicado (los valores son en pulgadas y el valor por defecto de número de puntos por pulgada es 100).
        # - errorbar muestra los datos data.x y data.y con sus errores (data.dx y data.dy).
        #     - el formato es puntos de color azul: format='b.'
        #     - label es la etiqueta que aparecerá en la leyenda
        #     - definimos el grosor de las líneas con linewidth
        # - plot lo usamos para mostrar la recta de regresión.
        #     - Aquí indicamos que el formato es una línea roja: format='r-'
        # - xlim e ylim definen los límites de los ejes x e y respectivamente.
        # - xlabel e ylabel definen la etiqueta de los ejes x e y respectivamente
        #     - Podemos definir una etiqueta en formato LaTex poniendo r antes de la cadena de texto y la exprexión LaTex entre simbolos $ (mira ylabel)
        # - legend muestra la leyenda.

        fig=plt.figure(figsize=[18,12])
        ax=fig.gca()
        plt.errorbar(data.x, data.y, xerr=data.dx, yerr=data.dy, fmt='b.', label='Datos', linewidth=3)
        plt.plot(data.x, y_pred, 'g-', label='Ajuste',linewidth=4.0)


        plt.xlabel(unidad_ejex,fontsize=25)
        plt.ylabel(unidad_ejey,fontsize=25)
        plt.legend(loc='best',fontsize=25)
        plt.grid()

        # Este comando permite modificar el grosor de los ejes:
        for axis in ['top','bottom','left','right']:
            ax.spines[axis].set_linewidth(4)

        # Con estas líneas podemos dar formato a los "ticks" de los ejes:
        plt.tick_params(axis="x", labelsize=25, labelrotation=0, labelcolor="black")
        plt.tick_params(axis="y", labelsize=25, labelrotation=0, labelcolor="black")

        # Aquí dibuja el gráfico que hemos definido.
        plt.savefig(nombre_graf)
        plt.show()
        input("Presione Enter para continuar...")
        opcion = menu()
    elif opcion == "4":
        print('------------------------------------------------------------------------------------')
        print('Escogio opción 4, ajuste de dos conjuntos de datos y determinación de intersección: ')
        print('------------------------------------------------------------------------------------')

        print(f"El archivo de datos debe tener la siguiente estructura:\nx{delimitador}y{delimitador}dx{delimitador}dy{delimitador}")
        # Aquí iría el desarrollo del programa para la opción 4
        def weighted_linear_fit(data):
            ### Ajuste lineal con incertidumbres en x e y usando ODR.

            model = odr.Model(lambda p, x: p[0]*x + p[1])
            mydata = odr.RealData(data['x'], data['y'], sx=data['dx'], sy=data['dy'])
            odr_fit = odr.ODR(mydata, model, beta0=[1., 0.])
            return odr_fit.run()

        def calculate_intersection(fit1, fit2):
            ### Calcula intersección y su matriz de covarianza.

            # Parámetros y covarianzas
            a1, b1 = fit1.beta
            a2, b2 = fit2.beta
            cov1 = fit1.cov_beta
            cov2 = fit2.cov_beta
            
            # Cálculo analítico de la intersección
            denom = a1 - a2
            if abs(denom) < 1e-10:
                raise ValueError("Las rectas son paralelas (no hay intersección)")
            
            x_int = (b2 - b1) / denom
            y_int = a1 * x_int + b1
            
            # Propagación de errores (primer orden)
            da1 = (b1 - b2)/(denom**2)
            db1 = -1/denom
            da2 = -da1
            db2 = -db1
            
            grad = np.array([da1, db1, da2, db2])
            total_cov = np.block([[cov1, np.zeros((2,2))],[np.zeros((2,2)), cov2]])
            
            cov_intersection = grad.T @ total_cov @ grad
            return (x_int, y_int), cov_intersection

        def plot_results(set1, set2, fit1, fit2, intersection, cov):
            ### Genera la visualización con matplotlib.

            plt.figure(figsize=(10, 6))
            
            # Conjuntos de datos con barras de error
            plt.errorbar(set1['x'], set1['y'], xerr=set1['dx'], yerr=set1['dy'], fmt='o', color='blue', label='Conjunto 1', alpha=0.7)
            plt.errorbar(set2['x'], set2['y'], xerr=set2['dx'], yerr=set2['dy'], fmt='s', color='green', label='Conjunto 2', alpha=0.7)
            
            # Rectas ajustadas
            x_vals = np.array([min(set1['x'].min(), set2['x'].min()), max(set1['x'].max(), set2['x'].max())])
            
            plt.plot(x_vals, fit1.beta[0]*x_vals + fit1.beta[1], 'b-', label=f'Recta 1: $y = {fit1.beta[0]:.2f}x + {fit1.beta[1]:.2f}$')
            plt.plot(x_vals, fit2.beta[0]*x_vals + fit2.beta[1], 'g-', label=f'Recta 2: $y = {fit2.beta[0]:.2f}x + {fit2.beta[1]:.2f}$')
            
            # Punto de intersección con elipse de error
            x_int, y_int = intersection
            plot_uncertainty_ellipse(x_int, y_int, cov, plt.gca())
            
            plt.scatter(x_int, y_int, color='red', s=100, zorder=5, label=f'Intersección: ({x_int:.2f}, {y_int:.2f})')
            
            plt.xlabel(unidad_ejex)
            plt.ylabel(unidad_ejey)
            plt.title('Ajuste lineal e intersección con incertidumbres')
            plt.legend()
            plt.grid(True)
            plt.show()

        def plot_uncertainty_ellipse(x, y, cov, ax, n_std=2.0):
            ### Dibuja una elipse de incertidumbre alrededor del punto.
            
            
            pearson = cov[0, 1]/np.sqrt(cov[0, 0] * cov[1, 1])
            ell_radius_x = np.sqrt(1 + pearson)
            ell_radius_y = np.sqrt(1 - pearson)
            
            ellipse = Ellipse((0, 0), width=ell_radius_x * 2 * n_std, height=ell_radius_y * 2 * n_std,facecolor='red', alpha=0.2, edgecolor='none')
            
            transf = transforms.Affine2D() \
                .rotate_deg(45) \
                .scale(np.sqrt(cov[0, 0]) * n_std, 
                    np.sqrt(cov[1, 1]) * n_std) \
                .translate(x, y)
            
            ellipse.set_transform(transf + ax.transData)
            ax.add_patch(ellipse)
            

            try:
                # Leer archivo CSV
                data = pd.read_csv(file_name, delimiter=delimitador, header=0, names=['x', 'y','dx', 'dy'])
                if not all(col in data.columns for col in ['x', 'y', 'dx', 'dy']):
                    raise ValueError("El archivo debe contener las columnas: x, y, dx, dy")
                
                # Separar conjuntos (asume que están ordenados secuencialmente)
                n = int(input("Número de puntos en el primer conjunto: "))
                set1 = data.iloc[:n]
                set2 = data.iloc[n:]
                
                # Realizar ajustes
                fit1 = weighted_linear_fit(set1)
                fit2 = weighted_linear_fit(set2)
                
                # Calcular intersección
                intersection, cov = calculate_intersection(fit1, fit2)
                x_int, y_int = intersection
                x_err, y_err = np.sqrt(np.diag(cov))
                
                # Resultados
                print("\n--- RESULTADOS ---")
                print(f"Recta 1: y = ({fit1.beta[0]:.4f} ± {fit1.sd_beta[0]:.4f})x + ({fit1.beta[1]:.4f} ± {fit1.sd_beta[1]:.4f})")
                print(f"Recta 2: y = ({fit2.beta[0]:.4f} ± {fit2.sd_beta[0]:.4f})x + ({fit2.beta[1]:.4f} ± {fit2.sd_beta[1]:.4f})")
                print("\nIntersección:")
                print(f"x = {x_int:.4f} ± {x_err:.4f}")
                print(f"y = {y_int:.4f} ± {y_err:.4f}")
                
                # Gráfico
                plot_results(set1, set2, fit1, fit2, intersection, cov)
                
            except Exception as e:
                print(f"Error: {str(e)}")

        input("Presione Enter para continuar...")
        opcion = menu()
    elif opcion == "5":
        print('---------------------------------------------------')
        print('Escogió la opción 5, ajuste por mínimos cuadrados (y = a·x + b): ')
        print('---------------------------------------------------')
        # === 1. Cargar datos desde CSV ===

        datos = pd.read_csv(file_name,delimiter=delimitador, header=0,names=["x","y","dx","dy"],decimal=decimal)
        # Extraer columnas
        x = np.array(datos["x"])
        y = np.array(datos["y"])
        ex = np.array(datos["dx"])   # Incertidumbre en x 
        ey = np.array(datos["dy"])   # Incertidumbre en y

        # === 2. Cálculo del ajuste lineal ponderado ===
        # Ponderaciones = 1/ey^2
        w = 1 / ey**2

        # Parámetros intermedios
        S = np.sum(w)
        Sx = np.sum(w * x)
        Sy = np.sum(w * y)
        Sxx = np.sum(w * x**2)
        Sxy = np.sum(w * x * y)
        Delta = S * Sxx - Sx**2

        # Coeficientes del ajuste y = a*x + b
        a = (S * Sxy - Sx * Sy) / Delta
        b = (Sxx * Sy - Sx * Sxy) / Delta

        # Incertidumbres de los parámetros
        sigma_a = np.sqrt(S / Delta)
        sigma_b = np.sqrt(Sxx / Delta)

        # === 3. Resultados ===
        print("=== Resultados del ajuste ponderado ===")
        print(f"Ajuste lineal: y = ({a:.8f} ± {sigma_a:.12f})·x + ({b:.4f} ± {sigma_b:.4f})")

        # === 4. Cálculo de valores ajustados ===
        y_ajuste = a * x + b

        # === 5. Cálculo del chi-cuadrado reducido (bondad del ajuste) ===
        chi2 = np.sum(((y - y_ajuste) / ey)**2)
        ndof = len(x) - 2
        chi2_red = chi2 / ndof
        print(f"Chi² reducido = {chi2_red:.3f}")

        # === 6. Gráfica ===
        plt.errorbar(x, y, xerr=ex, yerr=ey, fmt='o', label='Datos experimentales', color='blue', ecolor='gray', capsize=4)
        plt.plot(x, y_ajuste, color='red', label='Ajuste lineal ponderado')

        plt.xlabel(unidad_ejex,fontsize=25)
        plt.ylabel(unidad_ejey,fontsize=25)

        plt.legend(loc='best',fontsize=25)
        plt.grid(True)


        plt.savefig(nombre_graf)
        plt.show()

        input("Presione Enter para continuar...")
        opcion = menu()
    elif opcion == "6":
        print('---------------------------------------------------')
        print('Escogió la opción 6, ajuste por mínimos cuadrados (y = a·x): ')
        print('---------------------------------------------------')
        # === 1. Cargar datos desde CSV ===

        datos = pd.read_csv(file_name,delimiter=delimitador, header=0,names=["x","y","dx","dy"],decimal=decimal)
        # Extraer columnas
        x = np.array(datos["x"])
        y = np.array(datos["y"])
        ex = np.array(datos["dx"])   # Incertidumbre en x 
        ey = np.array(datos["dy"])   # Incertidumbre en y

        # === 2. Cálculo del ajuste lineal ponderado ===
        # Ponderaciones = 1/ey^2
        w = 1 / ey**2

        # Parámetros intermedios
        S = np.sum(w)
        Sx = np.sum(w * x)
        Sy = np.sum(w * y)
        Sxx = np.sum(w * x**2)
        Sxy = np.sum(w * x * y)
        Delta = S * Sxx - Sx**2

        # Coeficientes del ajuste y = a*x + b
        a = (S * Sxy - Sx * Sy) / Delta
        b = (Sxx * Sy - Sx * Sxy) / Delta

        # Incertidumbres de los parámetros
        sigma_a = np.sqrt(S / Delta)
        sigma_b = np.sqrt(Sxx / Delta)

        # === 3. Resultados ===
        print("=== Resultados del ajuste ponderado ===")
        print(f"Ajuste lineal: y = ({a:.8f} ± {sigma_a:.12f})·x + ({b:.4f} ± {sigma_b:.4f})")

        # === 4. Cálculo de valores ajustados ===
        y_ajuste = a * x

        # === 5. Cálculo del chi-cuadrado reducido (bondad del ajuste) ===
        chi2 = np.sum(((y - y_ajuste) / ey)**2)
        ndof = len(x) - 2
        chi2_red = chi2 / ndof
        print(f"Chi² reducido = {chi2_red:.3f}")

        # === 6. Gráfica ===
        plt.errorbar(x, y, xerr=ex, yerr=ey, fmt='o', label='Datos experimentales', color='blue', ecolor='gray', capsize=4)
        plt.plot(x, y_ajuste, color='red', label='Ajuste lineal ponderado')

        plt.xlabel(unidad_ejex,fontsize=25)
        plt.ylabel(unidad_ejey,fontsize=25)

        plt.legend(loc='best',fontsize=25)
        plt.grid(True)


        plt.savefig(nombre_graf)
        plt.show()

        input("Presione Enter para continuar...")
        opcion = menu()

    elif opcion == "7":
        print('---------------------------------------------------')
        print('Escogió la opción 7, spline cúbico a unos datos dados: ')
        print('---------------------------------------------------')

        data = pd.read_csv(file_name, delimiter=delimitador, header=0, names=['x', 'y'], decimal=decimal)
        print(data)
        eje_x = np.array([fila for fila in data['x']])
        eje_y = np.array([fila for fila in data['y']])
        cs = CubicSpline(eje_x, eje_y, bc_type="natural")

        funcion = lambda x: cs(x)
        x_fino = np.linspace(eje_x.min(), eje_x.max(), 1000)
        plt.figure(figsize=(8, 4))
        plt.plot(eje_x, eje_y, "o", label="Datos")
        plt.plot(x_fino, funcion(x_fino), "-", label="Spline Datos")
        plt.legend(loc='best', fontsize=25)
        plt.grid(True)
        plt.show()

        xs = cs.x        # nodos
        coef = cs.c 
        with open('spline_tramos.txt', 'w') as f:
            for i in range(len(xs) - 1):
                a3, a2, a1, a0 = coef[:, i]
                x_i = xs[i]
                f.write("Estructura del spline cúbico por tramos:\n")
                f.write('Tramo_i:   para x_i <= ν <= xs[i+1]: C_i(ν) = a3*(ν-x_i)**3 + a2*(ν-x_i)**2 + a1*(ν-x_i) + a0\n"')
                f.write(f"Tramo {i}:   para {x_i} <= ν <= {xs[i+1]}: C_i(ν) = {a3}*(ν-{x_i})**3 + {a2}*(ν-{x_i})**2 + {a1}*(ν-{x_i}) + {a0}\n")


        input("Presione Enter para continuar...")
        opcion = menu()


    elif opcion == "8":
        print('---------------------------------------------------')
        print('Escogió la opción 8, ajuste no lineal a unos datos dados: ')
        print('---------------------------------------------------')
        

        print(f"El archivo de datos debe tener la siguiente estructura:\nx{delimitador}y{delimitador}dx{delimitador}dy{delimitador}")
        
        ### Función de ajuste

        def func(x, a):
            return eval(expresion_no_lineal)

        ### Lectura de datos

        data = pd.read_csv(file_name, delimiter=delimitador, header=0, names=['x', 'y','dx', 'dy'],decimal=decimal)
        print(data)

        ### Ajuste

        popt, pcov = curve_fit(func, data.x, data.y, sigma=data.dy, absolute_sigma=True,maxfev=10000)

        y_pred = func(data.x, *popt)

        r = data.y - y_pred
        chisq = sum((r / data.dy) ** 2)
        mediax = mean(data.x)
        mediay = mean(data.y)

        mediaxy = mean(data.x*data.y)
        sigmax = stdev(data.x)
        sigmay = stdev(data.y)
        coef_Pearson = len(data.x)*(mediaxy-mediax*mediay)/((len(data.x)-1)*sigmax*sigmay)

        ### Salida de resultados

        print(f'   a: {popt[0]} \u00B1 {np.sqrt(pcov.diagonal())[0]}')
        print('')
        print(f'chi\u00b2: {chisq}')
        print('')
        print(f'media x: {mediax}')
        print(f'media y: {mediay}')
        print(f'media xy: {mediaxy}')
        print(f'Sigma x: {sigmax}')
        print(f'Sigma y: {sigmay}')
        print(f'Coeficiente de Pearson: {coef_Pearson}')

        ### Gráfica
        # - figure crea la figura con el tamaño indicado (los valores son en pulgadas y el valor por defecto de número de puntos por pulgada es 100).
        # - errorbar muestra los datos data.x y data.y con sus errores (data.dx y data.dy).
        #     - el formato es puntos de color azul: format='b.'
        #     - label es la etiqueta que aparecerá en la leyenda
        #     - definimos el grosor de las líneas con linewidth
        # - plot lo usamos para mostrar la recta de regresión.
        #     - Aquí indicamos que el formato es una línea roja: format='r-'
        # - xlim e ylim definen los límites de los ejes x e y respectivamente.
        # - xlabel e ylabel definen la etiqueta de los ejes x e y respectivamente
        #     - Podemos definir una etiqueta en formato LaTex poniendo r antes de la cadena de texto y la exprexión LaTex entre simbolos $ (mira ylabel)
        # - legend muestra la leyenda.

        fig=plt.figure(figsize=[18,12])
        ax=fig.gca()
        plt.errorbar(data.x, data.y, xerr=data.dx, yerr=data.dy, fmt='b.', label='Datos', linewidth=3)
        plt.plot(data.x, y_pred, 'g-', label='Ajuste',linewidth=4.0)


        plt.xlabel(unidad_ejex,fontsize=25)
        plt.ylabel(unidad_ejey,fontsize=25)
        plt.legend(loc='best',fontsize=25)
        plt.grid()

        # Este comando permite modificar el grosor de los ejes:
        for axis in ['top','bottom','left','right']:
            ax.spines[axis].set_linewidth(4)

        # Con estas líneas podemos dar formato a los "ticks" de los ejes:
        plt.tick_params(axis="x", labelsize=25, labelrotation=0, labelcolor="black")
        plt.tick_params(axis="y", labelsize=25, labelrotation=0, labelcolor="black")

        # Aquí dibuja el gráfico que hemos definido.
        plt.savefig(nombre_graf)
        plt.show()
        
        input("Presione Enter para continuar...")
        opcion = menu()



    else:
        print("Opción no válida. Por favor, seleccione una opción del menú.")
        opcion = menu()




