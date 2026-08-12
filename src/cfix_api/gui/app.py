"""Entry point for the CFIX gateway desktop GUI: python -m cfix_api.gui.app"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from .log_handler import QtLogHandler
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    log_handler = QtLogHandler()
    package_logger = logging.getLogger("cfix_api")
    package_logger.addHandler(log_handler)
    package_logger.setLevel(logging.INFO)

    window = MainWindow(log_handler)
    window.resize(900, 820)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
