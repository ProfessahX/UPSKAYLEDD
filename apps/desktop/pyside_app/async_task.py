from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class TaskSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class AsyncTask(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.signals.failed.emit(detail)
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
