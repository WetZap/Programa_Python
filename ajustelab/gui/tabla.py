"""Tabla de datos editable, asignación de columnas y deshacer/rehacer.

* Editar celdas (acepta coma o punto decimal).
* Ctrl+C copia la selección como texto tabulado (se pega bien en LibreOffice/Excel).
* Ctrl+V pega un bloque desde la celda actual (amplía filas/columnas si hace falta).
* Supr borra las celdas seleccionadas.
* Doble clic en una cabecera para renombrar la columna.
* Las filas excluidas del ajuste se muestran tachadas y en gris; las que quedan
  fuera del rango de ajuste, en gris sin tachar.
* Todo cambio en los datos se puede deshacer (Ctrl+Z) y rehacer (Ctrl+Mayús+Z).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QPalette, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QLineEdit, QPushButton, QTableView, QVBoxLayout, QWidget)

from ..datos import Datos, ErrorDatos, leer_texto
from .iconos import icono

NINGUNA = "— ninguna —"
CONSTANTE = "constante…"


def _a_float(texto: str) -> float:
    t = str(texto).strip().replace(",", ".")
    if t == "":
        return np.nan
    return float(t)


class _CambioDatos(QUndoCommand):
    """Paso de deshacer: instantánea completa antes y después del cambio."""

    def __init__(self, modelo: "ModeloTabla", antes: dict, despues: dict, texto: str):
        super().__init__(texto)
        self.modelo, self.antes, self.despues = modelo, antes, despues
        self._primera = True

    def redo(self):
        if self._primera:  # el cambio ya está hecho al registrarlo
            self._primera = False
            return
        self.modelo.restaurar(self.despues)

    def undo(self):
        self.modelo.restaurar(self.antes)


class ModeloTabla(QAbstractTableModel):
    rangoCambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._v = np.empty((0, 0))
        self._nombres: list[str] = []
        self.excluidas: set[int] = set()
        self.rango_x: tuple[float, float] | None = None
        self.x_actual: np.ndarray | None = None  # columna x elegida (para marcar el rango en la tabla)
        self.pila: QUndoStack | None = None

    # -- deshacer/rehacer ---------------------------------------------------
    def estado(self) -> dict:
        return {"v": self._v.copy(), "nombres": list(self._nombres), "excluidas": set(self.excluidas),
                "rango": self.rango_x}

    def restaurar(self, e: dict) -> None:
        self.beginResetModel()
        self._v = e["v"].copy()
        self._nombres = list(e["nombres"])
        self.excluidas = set(e["excluidas"])
        rango_previo, self.rango_x = self.rango_x, e["rango"]
        self.endResetModel()
        if rango_previo != self.rango_x:
            self.rangoCambiado.emit()

    @staticmethod
    def _iguales(a: dict, b: dict) -> bool:
        return (a["v"].shape == b["v"].shape and np.array_equal(a["v"], b["v"], equal_nan=True)
                and a["nombres"] == b["nombres"] and a["excluidas"] == b["excluidas"] and a["rango"] == b["rango"])

    def _registrar(self, texto: str, cambio) -> None:
        antes = self.estado()
        cambio()
        despues = self.estado()
        if self.pila is not None and not self._iguales(antes, despues):
            self.pila.push(_CambioDatos(self, antes, despues, texto))

    # -- contenido ----------------------------------------------------------
    def cargar(self, df: pd.DataFrame) -> None:
        """Contenido nuevo (abrir fichero): no se puede deshacer y vacía la pila."""
        self.beginResetModel()
        self._v = df.to_numpy(dtype=float, na_value=np.nan).copy()
        self._nombres = [str(c) for c in df.columns]
        self.excluidas = set()
        self.rango_x = None
        self.endResetModel()
        self.rangoCambiado.emit()
        if self.pila is not None:
            self.pila.clear()

    def vaciar(self, filas: int = 10, columnas: int = 4) -> None:
        self.cargar(pd.DataFrame(np.full((filas, columnas), np.nan), columns=["x", "y", "dx", "dy"][:columnas]
                                 + [f"col{i + 1}" for i in range(4, columnas)]))

    def a_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self._v.copy(), columns=list(self._nombres))

    @property
    def nombres(self) -> list[str]:
        return list(self._nombres)

    def fuera_de_rango(self, fila: int) -> bool:
        if self.rango_x is None or self.x_actual is None or fila >= self.x_actual.size:
            return False
        x = self.x_actual[fila]
        return bool(np.isfinite(x) and not (self.rango_x[0] <= x <= self.rango_x[1]))

    # -- interfaz Qt -------------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._v.shape[0]

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._v.shape[1]

    def data(self, index, rol=Qt.DisplayRole):
        if not index.isValid():
            return None
        v = self._v[index.row(), index.column()]
        excluida = index.row() in self.excluidas
        fuera = self.fuera_de_rango(index.row())
        if rol in (Qt.DisplayRole, Qt.EditRole):
            return "" if np.isnan(v) else f"{v:.10g}"
        if rol == Qt.TextAlignmentRole:
            return Qt.AlignRight | Qt.AlignVCenter
        if rol == Qt.ForegroundRole and (excluida or fuera):
            return QGuiApplication.palette().brush(QPalette.PlaceholderText)
        if rol == Qt.FontRole and excluida:
            f = QFont()
            f.setStrikeOut(True)
            return f
        if rol == Qt.ToolTipRole:
            if excluida:
                return "Fila excluida del ajuste (clic en el punto de la gráfica para incluirla)"
            if fuera:
                return "Fuera del rango de ajuste"
        return None

    def headerData(self, seccion, orientacion, rol=Qt.DisplayRole):
        if rol != Qt.DisplayRole:
            return None
        if orientacion == Qt.Horizontal:
            return self._nombres[seccion] if seccion < len(self._nombres) else None
        return str(seccion + 1)

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, index, valor, rol=Qt.EditRole):
        if rol != Qt.EditRole or not index.isValid():
            return False
        try:
            nuevo = _a_float(valor)
        except ValueError:
            return False
        actual = self._v[index.row(), index.column()]
        if nuevo == actual or (np.isnan(nuevo) and np.isnan(actual)):
            return True

        def cambio():
            self._v[index.row(), index.column()] = nuevo

        self._registrar("editar celda", cambio)
        self.dataChanged.emit(index, index)
        return True

    # -- operaciones (todas se pueden deshacer) ----------------------------
    def renombrar(self, columna: int, nombre: str) -> None:
        nombre = nombre.strip()
        if nombre and nombre not in self._nombres:
            self._registrar("renombrar columna", lambda: self._nombres.__setitem__(columna, nombre))
            self.headerDataChanged.emit(Qt.Horizontal, columna, columna)

    def insertar_filas(self, n: int = 1) -> None:
        r = self._v.shape[0]

        def cambio():
            self.beginInsertRows(QModelIndex(), r, r + n - 1)
            self._v = np.vstack([self._v, np.full((n, self._v.shape[1]), np.nan)])
            self.endInsertRows()

        self._registrar("añadir fila", cambio)

    def borrar_filas(self, filas: list[int]) -> None:
        if not filas:
            return

        def cambio():
            self.beginResetModel()
            quedan = np.setdiff1d(np.arange(self._v.shape[0]), filas)
            nuevo_indice = {int(old): i for i, old in enumerate(quedan)}
            self._v = self._v[quedan]
            self.excluidas = {nuevo_indice[f] for f in self.excluidas if f in nuevo_indice}
            self.endResetModel()

        self._registrar(f"borrar {len(filas)} fila{'s' if len(filas) > 1 else ''}", cambio)

    def pegar_bloque(self, fila: int, col: int, bloque: np.ndarray) -> None:
        def cambio():
            nf, nc = bloque.shape
            filas_nec = fila + nf - self._v.shape[0]
            cols_nec = col + nc - self._v.shape[1]
            self.beginResetModel()
            if filas_nec > 0:
                self._v = np.vstack([self._v, np.full((filas_nec, self._v.shape[1]), np.nan)])
            if cols_nec > 0:
                self._v = np.hstack([self._v, np.full((self._v.shape[0], cols_nec), np.nan)])
                n0 = len(self._nombres)
                self._nombres += [f"col{n0 + i + 1}" for i in range(cols_nec)]
            self._v[fila:fila + nf, col:col + nc] = bloque
            self.endResetModel()

        self._registrar("pegar", cambio)

    def borrar_celdas(self, indices) -> None:
        def cambio():
            for ix in indices:
                self._v[ix.row(), ix.column()] = np.nan
            self.layoutChanged.emit()

        self._registrar("borrar celdas", cambio)

    def alternar_exclusion(self, fila: int) -> None:
        texto = "incluir punto" if fila in self.excluidas else "excluir punto"
        self._registrar(texto, lambda: self.excluidas.symmetric_difference_update({fila}))
        self.dataChanged.emit(self.index(fila, 0), self.index(fila, self.columnCount() - 1))

    def alternar_varias(self, filas: list[int]) -> None:
        """Si alguna de las filas está incluida, las excluye todas; si no, las incluye."""
        filas = set(int(f) for f in filas)
        if not filas:
            return
        excluir = bool(filas - self.excluidas)

        def cambio():
            if excluir:
                self.excluidas |= filas
            else:
                self.excluidas -= filas
            self.layoutChanged.emit()

        self._registrar(f"{'excluir' if excluir else 'incluir'} {len(filas)} puntos", cambio)

    def incluir_todas(self) -> None:
        def cambio():
            self.excluidas.clear()
            self.layoutChanged.emit()

        self._registrar("incluir todos los puntos", cambio)

    def fijar_rango(self, rango: tuple[float, float] | None) -> None:
        if rango is not None:
            rango = (float(min(rango)), float(max(rango)))

        def cambio():
            self.rango_x = rango
            self.layoutChanged.emit()

        self._registrar("rango de ajuste" if rango else "quitar rango de ajuste", cambio)
        self.rangoCambiado.emit()


class VistaTabla(QTableView):
    def __init__(self, modelo: ModeloTabla, parent=None):
        super().__init__(parent)
        self.setModel(modelo)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setDefaultSectionSize(92)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().sectionDoubleClicked.connect(self._renombrar)
        self.horizontalHeader().setToolTip("Doble clic para renombrar la columna")

    def _renombrar(self, columna: int) -> None:
        m: ModeloTabla = self.model()
        nombre, ok = QInputDialog.getText(self, "Renombrar columna", "Nuevo nombre:", text=m.nombres[columna])
        if ok:
            m.renombrar(columna, nombre)

    def keyPressEvent(self, evento):
        if evento.matches(QKeySequence.Copy):
            self.copiar()
        elif evento.matches(QKeySequence.Paste):
            self.pegar()
        elif evento.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.state() != QAbstractItemView.EditingState:
            self.model().borrar_celdas(self.selectedIndexes())
        else:
            super().keyPressEvent(evento)

    def copiar(self) -> None:
        indices = self.selectedIndexes()
        if not indices:
            return
        filas = sorted({i.row() for i in indices})
        cols = sorted({i.column() for i in indices})
        m = self.model()
        texto = "\n".join("\t".join(m.data(m.index(f, c)) or "" for c in cols) for f in filas)
        QGuiApplication.clipboard().setText(texto)

    def pegar(self) -> None:
        texto = QGuiApplication.clipboard().text()
        if not texto.strip():
            return
        try:
            bloque = leer_texto(texto).to_numpy(dtype=float)
        except ErrorDatos:
            filas = [f.split("\t") for f in texto.strip("\n").splitlines()]
            ancho = max(len(f) for f in filas)
            try:
                bloque = np.array([[_a_float(v) for v in f] + [np.nan] * (ancho - len(f)) for f in filas])
            except ValueError:
                return
        actual = self.currentIndex()
        fila, col = (actual.row(), actual.column()) if actual.isValid() else (0, 0)
        self.model().pegar_bloque(fila, col, bloque)


class PanelDatos(QWidget):
    """Tabla + elección de columnas x, y, dx, dy (columna, ninguna o constante)."""

    datosCambiados = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modelo = ModeloTabla(self)
        self.vista = VistaTabla(self.modelo)
        self.info = QLabel("Sin datos")
        self.info.setObjectName("secundario")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.aviso_rango = QLabel()
        self.aviso_rango.setWordWrap(True)
        self.aviso_rango.setVisible(False)

        self.combos = {k: QComboBox() for k in ("x", "y", "dx", "dy")}
        self.constantes = {k: QLineEdit() for k in ("dx", "dy")}
        formulario = QFormLayout()
        ayudas = {"x": "Variable independiente", "y": "Variable dependiente",
                  "dx": "Incertidumbre (1σ) de x: columna, ninguna o un valor constante",
                  "dy": "Incertidumbre (1σ) de y: columna, ninguna o un valor constante"}
        for k, etiqueta in (("x", "x:"), ("y", "y:"), ("dx", "σx:"), ("dy", "σy:")):
            fila = QHBoxLayout()
            fila.addWidget(self.combos[k], 1)
            self.combos[k].setToolTip(ayudas[k])
            if k in self.constantes:
                ce = self.constantes[k]
                ce.setPlaceholderText("valor")
                ce.setMaximumWidth(90)
                ce.setVisible(False)
                ce.editingFinished.connect(self.datosCambiados)
                fila.addWidget(ce)
            formulario.addRow(etiqueta, fila)
            self.combos[k].currentIndexChanged.connect(self._al_cambiar_combo)

        b_fila = QPushButton("Añadir fila")
        b_borrar = QPushButton("Borrar filas")
        b_incluir = QPushButton("Incluir todas")
        b_fila.setToolTip("Añade una fila vacía al final")
        b_borrar.setToolTip("Borra las filas seleccionadas (se puede deshacer)")
        b_incluir.setToolTip("Vuelve a incluir todos los puntos excluidos y quita el rango de ajuste")
        b_fila.clicked.connect(lambda: self.modelo.insertar_filas(1))
        b_borrar.clicked.connect(self.borrar_filas_seleccionadas)
        b_incluir.clicked.connect(self.incluir_todas)
        botones = QHBoxLayout()
        for b in (b_fila, b_borrar, b_incluir):
            botones.addWidget(b)

        self.b_quitar_rango = QPushButton(icono("quitar"), "Quitar rango")
        self.b_quitar_rango.clicked.connect(lambda: self.modelo.fijar_rango(None))
        fila_rango = QHBoxLayout()
        fila_rango.addWidget(self.aviso_rango, 1)
        fila_rango.addWidget(self.b_quitar_rango)
        self.b_quitar_rango.setVisible(False)

        capa = QVBoxLayout(self)
        capa.addWidget(self.info)
        capa.addLayout(formulario)
        capa.addLayout(fila_rango)
        capa.addWidget(self.vista, 1)
        capa.addLayout(botones)

        self.modelo.dataChanged.connect(lambda *_: self.datosCambiados.emit())
        self.modelo.modelReset.connect(self._al_reiniciar)
        self.modelo.headerDataChanged.connect(lambda *_: self._rellenar_combos(conservar=True))
        self.modelo.layoutChanged.connect(lambda *_: self.datosCambiados.emit())
        self.modelo.rowsInserted.connect(lambda *_: self.datosCambiados.emit())
        self.modelo.rangoCambiado.connect(self._mostrar_rango)

    # -- carga --------------------------------------------------------------
    def cargar(self, df: pd.DataFrame, descripcion: str = "") -> None:
        self.modelo.cargar(df)
        cab = self.vista.horizontalHeader()
        # Pocas columnas: que llenen el ancho; muchas: ancho ajustable a mano
        cab.setSectionResizeMode(QHeaderView.Stretch if df.shape[1] <= 5 else QHeaderView.Interactive)
        self.info.setText(descripcion or f"{df.shape[0]} filas × {df.shape[1]} columnas")
        self._asignar_por_defecto(df)

    def _asignar_por_defecto(self, df: pd.DataFrame) -> None:
        """Misma asignación automática que :func:`ajustelab.datos.a_datos`."""
        from ..datos import _emparejar_errores

        cols = [str(c) for c in df.columns]
        pares = _emparejar_errores(cols)
        valores = [c for c in cols if c not in pares]
        asign = {"x": None, "y": None, "dx": None, "dy": None}
        if pares and len(valores) >= 2:
            inv = {v: e for e, v in pares.items()}
            asign.update(x=valores[0], y=valores[1], dx=inv.get(valores[0]), dy=inv.get(valores[1]))
        elif len(cols) >= 2:
            asign.update(x=cols[0], y=cols[1])
            if len(cols) == 3:
                asign["dy"] = cols[2]
            elif len(cols) >= 4:
                asign.update(dx=cols[2], dy=cols[3])
        self._rellenar_combos(asignacion=asign)
        self.datosCambiados.emit()

    def _al_reiniciar(self):
        self._rellenar_combos(conservar=True)
        self.datosCambiados.emit()

    def _rellenar_combos(self, asignacion: dict | None = None, conservar: bool = False) -> None:
        cols = self.modelo.nombres
        previo = {k: c.currentText() for k, c in self.combos.items()}
        for k, combo in self.combos.items():
            combo.blockSignals(True)
            combo.clear()
            opciones = cols if k in ("x", "y") else [NINGUNA, *cols, CONSTANTE]
            combo.addItems(opciones)
            objetivo = asignacion.get(k) if asignacion else (previo[k] if conservar else None)
            if objetivo not in opciones:  # columna desaparecida: valores por defecto
                if k in ("dx", "dy"):
                    objetivo = NINGUNA
                elif cols:
                    objetivo = cols[min(0 if k == "x" else 1, len(cols) - 1)]
            if objetivo in opciones:
                combo.setCurrentText(objetivo)
            combo.blockSignals(False)
            if k in self.constantes:
                self.constantes[k].setVisible(combo.currentText() == CONSTANTE)

    def _al_cambiar_combo(self) -> None:
        for k, ce in self.constantes.items():
            ce.setVisible(self.combos[k].currentText() == CONSTANTE)
        self.datosCambiados.emit()

    def _mostrar_rango(self) -> None:
        r = self.modelo.rango_x
        self.aviso_rango.setVisible(r is not None)
        self.b_quitar_rango.setVisible(r is not None)
        if r is not None:
            self.aviso_rango.setText(f"Rango de ajuste: {r[0]:.6g} ≤ x ≤ {r[1]:.6g}")
        self.vista.viewport().update()

    # -- asignación (para guardar/abrir sesiones) ---------------------------
    def asignacion(self) -> dict:
        a = {k: c.currentText() for k, c in self.combos.items()}
        a.update({f"{k}_constante": ce.text() for k, ce in self.constantes.items()})
        return a

    def fijar_asignacion(self, a: dict) -> None:
        self._rellenar_combos(asignacion={k: a.get(k) for k in self.combos})
        for k, ce in self.constantes.items():
            ce.setText(a.get(f"{k}_constante", ""))
            ce.setVisible(self.combos[k].currentText() == CONSTANTE)
        self.datosCambiados.emit()

    # -- acciones -----------------------------------------------------------
    def borrar_filas_seleccionadas(self) -> None:
        self.modelo.borrar_filas(sorted({i.row() for i in self.vista.selectedIndexes()}))

    def incluir_todas(self) -> None:
        self.modelo.incluir_todas()
        if self.modelo.rango_x is not None:
            self.modelo.fijar_rango(None)

    def alternar_fila(self, fila: int) -> None:
        self.modelo.alternar_exclusion(fila)
        self.vista.scrollTo(self.modelo.index(fila, 0))

    # -- construcción de Datos ---------------------------------------------
    def datos(self) -> tuple[Datos, np.ndarray]:
        """(Datos, filas) con las columnas elegidas. ``filas[i]`` es la fila de la
        tabla del punto i. Las filas con huecos se ignoran; las excluidas o fuera
        del rango de ajuste quedan con ``incluidos = False``."""
        df = self.modelo.a_dataframe()
        if df.empty:
            raise ErrorDatos("No hay datos.")
        cx, cy = self.combos["x"].currentText(), self.combos["y"].currentText()
        if not cx or not cy:
            raise ErrorDatos("Elige las columnas x e y.")
        if cx == cy:
            raise ErrorDatos("x e y no pueden ser la misma columna.")
        x, y = df[cx].to_numpy(), df[cy].to_numpy()
        self.modelo.x_actual = x
        validas = np.isfinite(x) & np.isfinite(y)
        errores = {}
        for k in ("dx", "dy"):
            sel = self.combos[k].currentText()
            if sel == NINGUNA or not sel:
                errores[k] = None
            elif sel == CONSTANTE:
                try:
                    errores[k] = _a_float(self.constantes[k].text())
                except ValueError:
                    raise ErrorDatos(f"σ{k[1]} constante no es un número.") from None
                if np.isnan(errores[k]):
                    raise ErrorDatos(f"Escribe el valor de σ{k[1]} constante.")
            else:
                col = df[sel].to_numpy()
                validas &= np.isfinite(col)
                errores[k] = col
        if validas.sum() < 2:
            raise ErrorDatos("Hacen falta al menos 2 filas con x e y numéricas (y sus σ, si las has elegido).")
        filas = np.flatnonzero(validas)
        sub = (lambda v: v if v is None or np.ndim(v) == 0 else v[validas])
        incluidos = ~np.isin(filas, list(self.modelo.excluidas))
        if self.modelo.rango_x is not None:
            lo, hi = self.modelo.rango_x
            incluidos &= (x[validas] >= lo) & (x[validas] <= hi)
        d = Datos(x[validas], y[validas], dx=sub(errores["dx"]), dy=sub(errores["dy"]), nombre_x=cx,
                  nombre_y=cy, incluidos=incluidos)
        d.filas_descartadas = int(len(df) - validas.sum())
        return d, filas
