"""Pestaña «Intersección»: corte de dos curvas ajustadas, con su incertidumbre."""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QPlainTextEdit, QSpinBox, QVBoxLayout

from ..estadistica import formatear
from ..interseccion import Interseccion, dividir, intersecar_datos
from ..modelos import ErrorModelo
from .grafica import Escena
from .paneles import Panel, SelectorModelo, _boton_principal, _monoespaciado
from .trabajos import Trabajo


class PanelInterseccion(Panel):
    titulo = "Intersección"
    nombre_icono = "rango"

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.resultado: Interseccion | None = None
        self.n = QSpinBox()
        self.n.setRange(2, 2)
        self.n.setToolTip("Los n primeros puntos válidos de la tabla forman el conjunto 1; el resto, el conjunto 2.")
        self.sel1 = SelectorModelo("lineal")
        self.sel2 = SelectorModelo("lineal")
        boton = _boton_principal("Calcular intersección", "rango")
        boton.clicked.connect(self.calcular)
        form = QFormLayout()
        form.addRow("Conjunto 1 = primeros n puntos, n =", self.n)
        form.addRow("Modelo del conjunto 1:", self.sel1)
        form.addRow("Modelo del conjunto 2:", self.sel2)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(boton)
        form.addRow(fila)
        self.salida = _monoespaciado(QPlainTextEdit())
        self.salida.setReadOnly(True)
        capa = QVBoxLayout(self)
        capa.addLayout(form)
        capa.addWidget(self.salida, 1)

    def actualizar_rango(self, n_total: int) -> None:
        self.n.setRange(2, max(2, n_total - 2))

    def calcular(self) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        try:
            d1, d2 = dividir(datos, self.n.value())
            m1, m2 = self.sel1.modelo(), self.sel2.modelo()
        except (ErrorModelo, ValueError) as e:
            self.ventana.mostrar_error(str(e))
            return
        self.ventana.lanzar(Trabajo(intersecar_datos, d1, d2, m1, m2), self.mostrar, "Calculando intersección…",
                            canal=self.titulo)

    def mostrar(self, I: Interseccion) -> None:
        self.resultado = I
        self.obsoleto = False
        ancho, alto, ang = I.elipse(0.6827)
        texto = [I.resumen(), "", f"Región de confianza 68 % (Δχ² = 2.30): ejes {ancho:.4g} × {alto:.4g}, "
                 f"girada {ang:.1f}°", "", "── Ajuste 1 ──", I.ajuste1.resumen(), "", "── Ajuste 2 ──",
                 I.ajuste2.resumen()]
        self.salida.setPlainText(self.ventana.fmt("\n".join(texto)))
        self.ventana.actualizar_grafica()
        self.ventana.notificar(self.ventana.fmt(f"Corte en x* = {formatear(I.x, I.sigma_x)}"), "bueno")

    def tiene_resultado(self) -> bool:
        return self.resultado is not None

    def escena(self, datos, filas) -> Escena:
        if self.resultado is None or self.obsoleto:
            return Escena(datos=datos, filas=filas)
        return Escena(datos=datos, filas=filas, interseccion=self.resultado)

    def recalcular(self) -> None:
        if self.resultado is not None:
            self.calcular()

    def reiniciar(self) -> None:
        self.resultado = None
        self.salida.clear()

    def texto_informe(self) -> str:
        return self.salida.toPlainText()

    def estado(self) -> dict:
        return {"n": self.n.value(), "modelo1": self.sel1.estado(), "modelo2": self.sel2.estado(),
                "calculado": self.resultado is not None}

    def restaurar(self, e: dict) -> None:
        self.n.setValue(e.get("n", 2))
        self.sel1.restaurar(e.get("modelo1", {"clave": "lineal"}))
        self.sel2.restaurar(e.get("modelo2", {"clave": "lineal"}))
        if e.get("calculado"):
            self.calcular()
