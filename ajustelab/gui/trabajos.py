"""Ejecución de cálculos en segundo plano para no congelar la interfaz.

Un :class:`Trabajo` ejecuta una función del núcleo en el ``QThreadPool`` global
y comunica el resultado con señales (siempre recibidas en el hilo de la GUI).
Si la función acepta ``progreso=``, el trabajo informa del avance y se puede
cancelar: la cancelación lanza :class:`Cancelado` dentro de la llamada de
progreso, que se propaga y detiene el cálculo.
"""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class Cancelado(Exception):
    """El usuario ha cancelado el trabajo."""


def mensaje_error(e: Exception) -> str:
    """Los errores propios de ajustelab ya traen un mensaje para el usuario; el
    resto se muestran con su tipo para poder diagnosticarlos."""
    if type(e).__module__.startswith("ajustelab"):
        return str(e)
    return f"{type(e).__name__}: {e}"


class SenalesTrabajo(QObject):
    terminado = Signal(object)
    error = Signal(str)
    cancelado = Signal()
    progreso = Signal(int, int, str)


class Trabajo(QRunnable):
    def __init__(self, funcion: Callable[..., Any], *args, con_progreso: bool = False, **kwargs):
        super().__init__()
        self.funcion = funcion
        self.args = args
        self.kwargs = kwargs
        self.con_progreso = con_progreso
        self.senales = SenalesTrabajo()
        self._cancelar = False
        self.setAutoDelete(False)  # lo libera quien lo lanza al recibir una señal final

    def cancelar(self) -> None:
        self._cancelar = True

    def _progreso(self, i: int, n: int, texto: str) -> None:
        if self._cancelar:
            raise Cancelado()
        self.senales.progreso.emit(i, n, texto)

    def run(self) -> None:
        try:
            if self.con_progreso:
                self.kwargs["progreso"] = self._progreso
            resultado = self.funcion(*self.args, **self.kwargs)
        except Cancelado:
            self.senales.cancelado.emit()
            return
        except Exception as e:  # se muestra al usuario; el detalle va a la consola
            traceback.print_exc()
            self.senales.error.emit(mensaje_error(e))
            return
        if self._cancelar:
            self.senales.cancelado.emit()
        else:
            self.senales.terminado.emit(resultado)
