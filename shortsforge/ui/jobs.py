"""Фоновые задачи интерфейса: одна задача — один поток, с прогрессом, логом и отменой."""

from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal


class Task(QThread):
    """Выполняет функцию в отдельном потоке и сообщает о ходе работы."""

    progress = Signal(float, str)     # доля 0..1, текст
    log = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def _progress(self, value: float | None, text: str = "") -> None:
        if value is None:
            self.progress.emit(-1.0, text)
        else:
            self.progress.emit(float(value), text)

    def run(self) -> None:  # noqa: D401 - метод Qt
        try:
            result = self._func(*self._args, progress=self._progress,
                                cancel=self.is_cancelled, **self._kwargs)
            self.done.emit(result)
        except RuntimeError as e:
            if "отменено" in str(e):
                self.log.emit("Отменено пользователем")
            else:
                self.failed.emit(str(e))
        except Exception as e:                      # noqa: BLE001 - показываем любую ошибку
            self.failed.emit(f"{e}")
            self.log.emit(traceback.format_exc(limit=4))


class TaskRunner(QObject):
    """Держит ссылку на текущую задачу, чтобы её не собрал сборщик мусора."""

    def __init__(self) -> None:
        super().__init__()
        self.current: Task | None = None

    def busy(self) -> bool:
        return self.current is not None and self.current.isRunning()

    def start(self, func: Callable, *args, **kwargs) -> Task:
        if self.busy():
            raise RuntimeError("уже выполняется другая задача")
        task = Task(func, *args, **kwargs)
        self.current = task
        task.finished.connect(lambda: setattr(self, "current", None))
        task.start()
        return task

    def cancel(self) -> None:
        if self.current is not None:
            self.current.cancel()
