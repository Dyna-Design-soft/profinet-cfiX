"""Bridges Python logging into the Qt event loop.

Gateway log records are emitted from worker threads (TCP/UDP handler
threads), but Qt widgets may only be touched from the GUI thread. Routing
through a signal (queued connection, Qt's default across threads) makes
the hand-off thread-safe.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal


class _Emitter(QObject):
    log_emitted = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.emitter = _Emitter()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self.emitter.log_emitted.emit(message)
