# -*- coding: utf-8 -*-
"""Background work. Nothing slow may run on the UI thread."""
from __future__ import annotations

import traceback
from typing import Callable

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    """Runs `fn(*args, **kwargs)` off the UI thread.

    Emits exactly one of:
        done(object)   — the return value
        failed(str)    — a human-readable message (full traceback in `.error_detail`)

    If `pass_progress` is set, a `progress=` callback is injected that re-emits
    on the `progress(float, str)` signal, so callers can drive a progress bar
    without knowing about Qt.
    """

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)

    def __init__(self, fn: Callable, *args, pass_progress: bool = False, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._pass_progress = pass_progress
        self.error_detail = ""

    def run(self) -> None:  # pragma: no cover - exercised via the UI
        try:
            kwargs = dict(self._kwargs)
            if self._pass_progress:
                kwargs["progress"] = lambda frac, text: self.progress.emit(float(frac), str(text))
            result = self._fn(*self._args, **kwargs)
        except Exception as e:
            self.error_detail = traceback.format_exc()
            msg = str(e) or e.__class__.__name__
            self.failed.emit(msg)
            return
        self.done.emit(result)
