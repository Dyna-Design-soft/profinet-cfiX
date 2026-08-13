"""Main window for the CFIX gateway desktop app.

Starts the gateway automatically on launch, using the last-saved
configuration (or mock-backend defaults on first run) - there is no
manual Start button. Two buttons cover configuration: "Gateway
Configuration" (TCP/UDP, plus the opt-in streaming mode) and "DLL
Configuration" (cifX board/channel/driver DLL/mock toggle). Either dialog
saves and restarts the gateway automatically on Apply, so changes take
effect immediately. A "Restart Gateway" button covers manual recovery
(e.g. after fixing a cable or a misconfigured DLL) without closing the
app.

Those three actions - Gateway Configuration, DLL Configuration, Restart
Gateway - are gated behind a Login button (see auth.py): disabled until a
correct password is entered, re-locked on every app launch (no "remember
me"). Diagnostics is read-only and never gated.
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
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..gateway.server import GatewayRunner
from . import auth
from .diagnostics_window import DiagnosticsWindow
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
        auth_path: Path = auth.DEFAULT_AUTH_PATH,
    ):
        super().__init__()
        self.setWindowTitle("CFIX Gateway")

        self._settings_path = settings_path
        self._auth_path = auth_path
        auth.ensure_password_set(self._auth_path)
        self._authenticated = False
        self.config = load_settings(settings_path)
        self.runner: GatewayRunner | None = None
        self._diagnostics_window: DiagnosticsWindow | None = None

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

        login_row = QHBoxLayout()
        self.login_status_label = QLabel("Locked")
        self.login_status_label.setStyleSheet("color: red;")
        self.change_password_btn = QPushButton("Change Password…")
        self.change_password_btn.setEnabled(False)
        self.change_password_btn.clicked.connect(self._change_password)
        self.login_btn = QPushButton("Login…")
        self.login_btn.clicked.connect(self._toggle_login)
        login_row.addWidget(self.login_status_label)
        login_row.addStretch()
        login_row.addWidget(self.change_password_btn)
        login_row.addWidget(self.login_btn)
        layout.addLayout(login_row)

        button_row = QHBoxLayout()
        self.gateway_config_btn = QPushButton("Gateway Configuration…")
        self.dll_config_btn = QPushButton("DLL Configuration…")
        self.diagnostics_btn = QPushButton("Diagnostics…")
        self.restart_btn = QPushButton("Restart Gateway")
        self.gateway_config_btn.clicked.connect(self._open_gateway_config)
        self.dll_config_btn.clicked.connect(self._open_dll_config)
        self.diagnostics_btn.clicked.connect(self._open_diagnostics)
        self.restart_btn.clicked.connect(self._restart_gateway)
        # Gated behind Login - Diagnostics is read-only and never gated.
        self.gateway_config_btn.setEnabled(False)
        self.dll_config_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        button_row.addWidget(self.gateway_config_btn)
        button_row.addWidget(self.dll_config_btn)
        button_row.addWidget(self.diagnostics_btn)
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
    # Login gate
    # ------------------------------------------------------------------
    def _toggle_login(self) -> None:
        if self._authenticated:
            self._set_authenticated(False)
            logger.info("logged out")
            return

        password, ok = QInputDialog.getText(self, "Login", "Password:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if auth.verify_password(password, self._auth_path):
            self._set_authenticated(True)
            logger.info("logged in")
        else:
            QMessageBox.warning(self, "Login failed", "Incorrect password.")

    def _set_authenticated(self, authenticated: bool) -> None:
        self._authenticated = authenticated
        self.gateway_config_btn.setEnabled(authenticated)
        self.dll_config_btn.setEnabled(authenticated)
        self.restart_btn.setEnabled(authenticated)
        self.change_password_btn.setEnabled(authenticated)
        if authenticated:
            self.login_btn.setText("Logout")
            self.login_status_label.setText("Unlocked")
            self.login_status_label.setStyleSheet("color: green;")
        else:
            self.login_btn.setText("Login…")
            self.login_status_label.setText("Locked")
            self.login_status_label.setStyleSheet("color: red;")

    def _change_password(self) -> None:
        new_password, ok = QInputDialog.getText(
            self, "Change Password", "New password:", QLineEdit.EchoMode.Password
        )
        if not ok or not new_password:
            return
        confirm, ok = QInputDialog.getText(
            self, "Change Password", "Confirm new password:", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if confirm != new_password:
            QMessageBox.warning(self, "Change Password", "Passwords did not match.")
            return
        auth.set_password(new_password, self._auth_path)
        logger.info("password changed")
        QMessageBox.information(self, "Change Password", "Password changed.")

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

    def _open_diagnostics(self) -> None:
        if self._diagnostics_window is None:
            self._diagnostics_window = DiagnosticsWindow(self, self)
        self._diagnostics_window.show()
        self._diagnostics_window.raise_()
        self._diagnostics_window.activateWindow()

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
        if self._diagnostics_window is not None:
            self._diagnostics_window.close()
        self._stop_gateway()
        super().closeEvent(event)
