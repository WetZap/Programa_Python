"""Pestaña «Selección de modelo»: ajusta todo el catálogo y ordena por AICc/BIC."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..ajuste import ResultadoAjuste
from ..seleccion import Seleccion, seleccionar
from .grafica import COLORES_COMPARAR, Escena
from .iconos import icono
from .paneles import Panel, _boton_principal, _celda, _g
from .trabajos import Trabajo


class PanelSeleccion(Panel):
    titulo = "Selección de modelo"
    nombre_icono = "seleccion"
    _COLUMNAS = ["Ver", "", "Modelo", "k", "χ²/ν", "p", "Rachas p", "Δ", "Peso", "Estado / advertencias"]

    def __init__(self, ventana, parent=None):
        super().__init__(ventana, parent)
        self.seleccion: Seleccion | None = None
        self.elegido = None
        self.criterio = QComboBox()
        self.criterio.addItem("AICc", "aicc")
        self.criterio.addItem("BIC", "bic")
        self.criterio.setToolTip("AICc: mejor con pocos puntos. BIC: penaliza más los parámetros extra")
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("modelos propios separados por «;» o claves (p. ej. malus_grados)")
        self.usar_dx = QCheckBox("Usar σx")
        self.usar_dx.setChecked(True)
        boton = _boton_principal("Probar todos los modelos", "seleccion")
        boton.clicked.connect(self.ejecutar)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Criterio:"))
        fila.addWidget(self.criterio)
        fila.addWidget(self.extra, 1)
        fila.addWidget(self.usar_dx)
        fila.addWidget(boton)

        self.tabla = QTableWidget(0, len(self._COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self._COLUMNAS)
        self.tabla.horizontalHeaderItem(0).setToolTip("Superponer en la gráfica para comparar (máximo 3)")
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        cab = self.tabla.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(len(self._COLUMNAS) - 1, QHeaderView.Stretch)
        self.tabla.itemSelectionChanged.connect(self._al_seleccionar)
        self.tabla.itemDoubleClicked.connect(lambda _: self.usar_en_ajuste())
        self.tabla.itemChanged.connect(self._al_marcar)

        self.leyenda = QLabel("★ recomendado   ✓ compatible   ✗ incompatible   (doble clic: usar en «Ajuste»)")
        self.leyenda.setObjectName("secundario")
        self.avisos = QLabel()
        self.avisos.setWordWrap(True)
        self.avisos.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_usar = QPushButton(icono("usar"), "Usar en «Ajuste»")
        b_usar.clicked.connect(self.usar_en_ajuste)
        abajo = QHBoxLayout()
        abajo.addWidget(self.avisos, 1)
        abajo.addWidget(b_usar, 0, Qt.AlignTop)

        capa = QVBoxLayout(self)
        capa.addLayout(fila)
        capa.addWidget(self.tabla, 1)
        capa.addWidget(self.leyenda)
        capa.addLayout(abajo)

    def ejecutar(self) -> None:
        obtenidos = self.ventana.obtener_datos()
        if obtenidos is None:
            return
        datos, _ = obtenidos
        extra = [t.strip() for t in self.extra.text().split(";") if t.strip()]
        trabajo = Trabajo(seleccionar, datos, extra=extra, criterio=self.criterio.currentData(),
                          usar_dx=self.usar_dx.isChecked(), con_progreso=True)
        self.ventana.lanzar(trabajo, self.mostrar, "Probando modelos…", cancelable=True, canal=self.titulo)

    def mostrar(self, sel: Seleccion) -> None:
        self.seleccion = sel
        self.obsoleto = False
        fmt = self.ventana.fmt
        self.tabla.blockSignals(True)
        self.tabla.setHorizontalHeaderItem(7, QTableWidgetItem("ΔAICc" if sel.criterio == "aicc" else "ΔBIC"))
        self.tabla.setRowCount(len(sel.candidatos))
        fila_rec = 0
        for i, c in enumerate(sel.candidatos):
            b = c.bondad
            marca = "★" if c is sel.recomendado else ("✓" if c.compatible else ("✗" if c.valido else ""))
            estado = "; ".join(c.advertencias) if c.valido else f"excluido: {c.motivo}"
            ver = QTableWidgetItem()
            if c.valido:
                ver.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                ver.setCheckState(Qt.Unchecked)
            else:
                ver.setFlags(Qt.NoItemFlags)
            self.tabla.setItem(i, 0, ver)
            valores = [marca, c.modelo.nombre, str(c.modelo.k), _g(b.chi2_red if b else None),
                       _g(b.p_valor if b else None, 2), _g(b.rachas.p if b else None, 2),
                       _g(c.delta if c.valido else None, 3), _g(c.peso if c.valido else None, 2), estado]
            for j, v in enumerate(valores, start=1):
                item = _celda(fmt(v) if 4 <= j <= 8 else v, alinear_derecha=3 <= j <= 8)
                if not c.valido:
                    item.setForeground(self.palette().placeholderText())
                self.tabla.setItem(i, j, item)
            if c is sel.recomendado:
                fila_rec = i
        self.tabla.blockSignals(False)
        self.avisos.setText(fmt("\n".join(f"• {a}" for a in sel.avisos)))
        self.tabla.selectRow(fila_rec)
        self._al_seleccionar()
        if sel.recomendado is not None:
            self.ventana.notificar(f"Recomendado: {sel.recomendado.modelo.nombre}", "bueno")

    def comparados(self) -> list[ResultadoAjuste]:
        if self.seleccion is None or self.obsoleto:
            return []
        salida = []
        for i, c in enumerate(self.seleccion.candidatos):
            it = self.tabla.item(i, 0)
            if it is not None and it.checkState() == Qt.Checked and c.resultado is not None and c is not self.elegido:
                salida.append(c.resultado)
        return salida[:3]

    def _al_marcar(self, item) -> None:
        if item.column() != 0 or self.seleccion is None:
            return
        marcados = [i for i in range(self.tabla.rowCount())
                    if self.tabla.item(i, 0) is not None and self.tabla.item(i, 0).checkState() == Qt.Checked]
        if len(marcados) > 3 and item.checkState() == Qt.Checked:
            self.tabla.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.tabla.blockSignals(False)
            self.ventana.notificar("Se pueden comparar como máximo 3 modelos a la vez.", "aviso")
            return
        self._colorear_marcados()
        self.ventana.actualizar_grafica()

    def _colorear_marcados(self) -> None:
        colores = COLORES_COMPARAR[self.ventana.tema.oscuro]
        k = 0
        self.tabla.blockSignals(True)
        for i in range(self.tabla.rowCount()):
            it = self.tabla.item(i, 0)
            nombre = self.tabla.item(i, 2)
            if it is None or nombre is None:
                continue
            c = self.seleccion.candidatos[i] if self.seleccion else None
            if it.checkState() == Qt.Checked and c is not self.elegido and k < 3:
                it.setBackground(QBrush(QColor(colores[k])))
                k += 1
            else:
                it.setBackground(QBrush())
        self.tabla.blockSignals(False)

    def _al_seleccionar(self) -> None:
        if self.seleccion is None:
            return
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return
        c = self.seleccion.candidatos[filas[0].row()]
        self.elegido = c if c.resultado is not None and c.valido else None
        self._colorear_marcados()
        self.ventana.actualizar_grafica()

    def usar_en_ajuste(self) -> None:
        if self.elegido is not None:
            self.ventana.usar_en_ajuste(self.elegido.resultado)

    def tiene_resultado(self) -> bool:
        return self.seleccion is not None

    def escena(self, datos, filas) -> Escena:
        r = self.elegido.resultado if self.elegido is not None and not self.obsoleto else None
        return Escena(datos=datos, filas=filas, ajuste=r, nivel_banda=0.6827, comparar=self.comparados())

    def marcar_obsoleto(self) -> None:
        super().marcar_obsoleto()
        if self.obsoleto:
            self.avisos.setText("⚠ Los datos han cambiado: vuelve a pulsar «Probar todos los modelos».")

    def reiniciar(self) -> None:
        self.seleccion = None
        self.elegido = None
        self.tabla.setRowCount(0)
        self.avisos.clear()

    def texto_informe(self) -> str:
        return self.ventana.fmt(self.seleccion.resumen()) if self.seleccion is not None else ""

    def estado(self) -> dict:
        return {"criterio": self.criterio.currentData(), "extra": self.extra.text(),
                "usar_dx": self.usar_dx.isChecked(), "calculado": self.seleccion is not None}

    def restaurar(self, e: dict) -> None:
        i = self.criterio.findData(e.get("criterio", "aicc"))
        self.criterio.setCurrentIndex(max(i, 0))
        self.extra.setText(e.get("extra", ""))
        self.usar_dx.setChecked(e.get("usar_dx", True))
        if e.get("calculado"):
            self.ejecutar()


#
