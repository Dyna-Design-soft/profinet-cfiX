"""Main window for the CFIX gateway desktop app.

Starts the gateway automatically on launch, using the last-saved
configuration (or mock-backend defaults on first run) - there is no
manual Start button. Two buttons cover configuration: "Gateway
Configuration" (TCP/UDP) and "DLL Configuration" (cifX board/channel/
driver DLL/mock toggle). Either dialog saves and restarts the gateway
automatically on Apply, so changes take effect immediately. A "Restart
Gateway" button covers manual recovery (e.g. after fixing a cable or a
misconfigured DLL) without closing the app.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..gateway.server import GatewayRunner
from .dll_config_dialog import DllConfigDialog
from .gateway_config_dialog import GatewayConfigDialog
from .gui_settings import DEFAULT_SETTINGS_PATH, load_settings, save_settings
from .log_handler import QtLogHandler

logger = logging.getLogger("cfix_api.gui")

POLL_INTERVAL_MS = 500


class MainWindow(QMainWindow):
    def __init__(
        self,
        log_handler: QtLogHandler,
        autostart: bool = True,
        settings_path: Path = DEFAULT_SETTINGS_PATH,
    ):
        super().__init__()
        self.setWindowTitle("CFIX Gateway")

        self._settings_path = settings_path
        self.config = load_settings(settings_path)
        self.runner: GatewayRunner | None = None

        self._build_ui()
        log_handler.emitter.log_emitted.connect(self._append_log)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)

        if autostart:
            self._start_gateway()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        status_group = QGroupBox("Status")
        status_form = QFormLayout()
        self.running_label = QLabel("Stopped")
        self.running_label.setStyleSheet("color: red; font-weight: bold;")
        self.bus_state_label = QLabel("-")
        self.host_state_label = QLabel("-")
        self.tcp_clients_label = QLabel("-")
        status_form.addRow("Gateway", self.running_label)
        status_form.addRow("Bus state", self.bus_state_label)
        status_form.addRow("Host state", self.host_state_label)
        status_form.addRow("TCP clients", self.tcp_clients_label)
        status_group.setLayout(status_form)
        layout.addWidget(status_group)

        button_row = QHBoxLayout()
        self.gateway_config_btn = QPushButton("Gateway Configuration…")
        self.dll_config_btn = QPushButton("DLL Configuration…")
        self.restart_btn = QPushButton("Restart Gateway")
        self.gateway_config_btn.clicked.connect(self._open_gateway_config)
        self.dll_config_btn.clicked.connect(self._open_dll_config)
        self.restart_btn.clicked.connect(self._restart_gateway)
        button_row.addWidget(self.gateway_config_btn)
        button_row.addWidget(self.dll_config_btn)
        button_row.addStretch()
        button_row.addWidget(self.restart_btn)
        layout.addLayout(button_row)

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setFont(QFont("Courier New", 9))
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, stretch=1)

        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # Config dialogs
    # ------------------------------------------------------------------
    def _open_gateway_config(self) -> None:
        dialog = GatewayConfigDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.apply_to(self.config)
            save_settings(self.config, self._settings_path)
            self._restart_gateway()

    def _open_dll_config(self) -> None:
        dialog = DllConfigDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.apply_to(self.config)
            save_settings(self.config, self._settings_path)
            self._restart_gateway()

    # ------------------------------------------------------------------
    # Gateway lifecycle
    # ------------------------------------------------------------------
    def _start_gateway(self) -> None:
        if self.runner is not None:
            return
        runner = GatewayRunner(self.config)
        try:
            runner.start()
        except Exception as exc:
            logger.error("failed to start gateway: %s", exc)
            self._set_running_ui(False)
            QMessageBox.critical(self, "Failed to start gateway", str(exc))
            return
        self.runner = runner
        self._set_running_ui(True)
        self._poll_timer.start()
        logger.info("gateway started")

    def _stop_gateway(self) -> None:
        if self.runner is None:
            return
        self._poll_timer.stop()
        try:
            self.runner.stop()
        except Exception as exc:
            logger.warning("error stopping gateway: %s", exc)
        self.runner = None
        self._set_running_ui(False)
        logger.info("gateway stopped")

    def _restart_gateway(self) -> None:
        self._stop_gateway()
        self._start_gateway()

    def _set_running_ui(self, running: bool) -> None:
        if running:
            self.running_label.setText("Running")
            self.running_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.running_label.setText("Stopped")
            self.running_label.setStyleSheet("color: red; font-weight: bold;")
            self.bus_state_label.setText("-")
            self.host_state_label.setText("-")
            self.tcp_clients_label.setText("-")

    # ------------------------------------------------------------------
    # Live polling
    # ------------------------------------------------------------------
    def _poll(self) -> None:
        if self.runner is None:
            return
        try:
            bus_state, host_state = self.runner.backend.get_status()
            self.bus_state_label.setText("ON" if bus_state else "OFF")
            self.host_state_label.setText("READY" if host_state else "NOT READY")
        except Exception as exc:
            logger.warning("status poll failed: %s", exc)

        client_count = self.runner.tcp_client_count
        self.tcp_clients_label.setText(str(client_count) if client_count is not None else "n/a")

    # ------------------------------------------------------------------
    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_gateway()
        super().closeEvent(event)
