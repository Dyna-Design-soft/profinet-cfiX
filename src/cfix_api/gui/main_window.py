"""Main window for the CFIX gateway desktop GUI.

Runs the gateway in-process: Start/Stop owns a GatewayRunner directly
(the same class the CLI uses), so this app is a drop-in alternative to
`cfix-gateway --config ...` for interactive use, with a live view of
bus/host state, TCP client count, and the input/output process-data
image, plus a manual write buffer for commissioning/testing.
"""

from __future__ import annotations

import dataclasses
import json
import logging

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..gateway.config import CifxConfig, GatewayConfig, TcpConfig, UdpConfig
from ..gateway.server import GatewayRunner
from .log_handler import QtLogHandler

logger = logging.getLogger("cfix_api.gui")

POLL_INTERVAL_MS = 300


def _bytes_to_hex(data: bytes) -> str:
    return data.hex(" ").upper()


def _hex_to_bytes(text: str) -> bytes:
    cleaned = "".join(text.split())
    if len(cleaned) % 2 != 0:
        raise ValueError("odd number of hex digits")
    return bytes.fromhex(cleaned)


class MainWindow(QMainWindow):
    def __init__(self, log_handler: QtLogHandler):
        super().__init__()
        self.setWindowTitle("CFIX Gateway")

        self.runner: GatewayRunner | None = None
        self._current_config_path: str | None = None
        self._config_widgets: list[QWidget] = []

        self._build_ui()

        log_handler.emitter.log_emitted.connect(self._append_log)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        top_row = QHBoxLayout()
        top_row.addWidget(self._build_cifx_group())
        top_row.addWidget(self._build_transport_group("TCP", is_tcp=True))
        top_row.addWidget(self._build_transport_group("UDP", is_tcp=False))
        root.addLayout(top_row)

        root.addLayout(self._build_button_row())
        root.addWidget(self._build_status_group())
        root.addWidget(self._build_io_group())

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setFont(QFont("Courier New", 9))
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        root.addWidget(log_group, stretch=1)

        self.setCentralWidget(central)

    def _build_cifx_group(self) -> QGroupBox:
        group = QGroupBox("cifX Configuration")
        form = QFormLayout()

        self.board_name_edit = QLineEdit("cifX0")
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(0, 7)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60000)
        self.timeout_spin.setValue(100)
        self.timeout_spin.setSuffix(" ms")

        self.dll_path_edit = QLineEdit()
        self.dll_path_edit.setPlaceholderText("auto-detect (cifx32dll.dll)")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_dll)
        dll_row = QHBoxLayout()
        dll_row.addWidget(self.dll_path_edit)
        dll_row.addWidget(browse_btn)
        dll_row_widget = QWidget()
        dll_row_widget.setLayout(dll_row)

        self.mock_checkbox = QCheckBox("Use mock backend (no hardware required)")
        self.mock_checkbox.setChecked(True)

        form.addRow("Board name", self.board_name_edit)
        form.addRow("Channel", self.channel_spin)
        form.addRow("IO timeout", self.timeout_spin)
        form.addRow("Driver DLL path", dll_row_widget)
        form.addRow("", self.mock_checkbox)
        group.setLayout(form)

        self._config_widgets.extend(
            [self.board_name_edit, self.channel_spin, self.timeout_spin, self.dll_path_edit, browse_btn, self.mock_checkbox]
        )
        return group

    def _build_transport_group(self, title: str, is_tcp: bool) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout()

        enabled_checkbox = QCheckBox("Enabled")
        enabled_checkbox.setChecked(True)
        host_edit = QLineEdit("0.0.0.0")
        port_spin = QSpinBox()
        port_spin.setRange(1, 65535)
        port_spin.setValue(9800 if is_tcp else 9801)

        form.addRow(enabled_checkbox)
        form.addRow("Host", host_edit)
        form.addRow("Port", port_spin)
        group.setLayout(form)

        if is_tcp:
            self.tcp_enabled, self.tcp_host_edit, self.tcp_port_spin = enabled_checkbox, host_edit, port_spin
        else:
            self.udp_enabled, self.udp_host_edit, self.udp_port_spin = enabled_checkbox, host_edit, port_spin

        self._config_widgets.extend([enabled_checkbox, host_edit, port_spin])
        return group

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.open_config_btn = QPushButton("Open Config…")
        self.save_config_btn = QPushButton("Save Config…")
        self.start_btn = QPushButton("Start Gateway")
        self.stop_btn = QPushButton("Stop Gateway")
        self.stop_btn.setEnabled(False)

        self.open_config_btn.clicked.connect(self._open_config)
        self.save_config_btn.clicked.connect(self._save_config)
        self.start_btn.clicked.connect(self._start_gateway)
        self.stop_btn.clicked.connect(self._stop_gateway)

        row.addWidget(self.open_config_btn)
        row.addWidget(self.save_config_btn)
        row.addStretch()
        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)

        self._config_widgets.append(self.open_config_btn)
        return row

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("Status")
        form = QFormLayout()

        self.running_label = QLabel("Stopped")
        self.running_label.setStyleSheet("color: red; font-weight: bold;")
        self.bus_state_label = QLabel("-")
        self.host_state_label = QLabel("-")
        self.tcp_clients_label = QLabel("-")

        form.addRow("Gateway", self.running_label)
        form.addRow("Bus state", self.bus_state_label)
        form.addRow("Host state", self.host_state_label)
        form.addRow("TCP clients", self.tcp_clients_label)
        group.setLayout(form)
        return group

    def _build_io_group(self) -> QGroupBox:
        group = QGroupBox("Process Data Monitor (Area 0)")
        layout = QVBoxLayout()
        mono = QFont("Courier New", 10)

        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel("Offset"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 4096)
        offset_row.addWidget(self.offset_spin)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Input (from drive), length"))
        self.input_len_spin = QSpinBox()
        self.input_len_spin.setRange(1, 256)
        self.input_len_spin.setValue(32)
        input_row.addWidget(self.input_len_spin)
        layout.addLayout(input_row)
        self.input_hex_view = QLineEdit()
        self.input_hex_view.setReadOnly(True)
        self.input_hex_view.setFont(mono)
        layout.addWidget(self.input_hex_view)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output (to drive), length"))
        self.output_len_spin = QSpinBox()
        self.output_len_spin.setRange(1, 256)
        self.output_len_spin.setValue(32)
        output_row.addWidget(self.output_len_spin)
        layout.addLayout(output_row)
        self.output_hex_view = QLineEdit()
        self.output_hex_view.setReadOnly(True)
        self.output_hex_view.setFont(mono)
        layout.addWidget(self.output_hex_view)

        write_row = QHBoxLayout()
        self.write_buffer_edit = QLineEdit()
        self.write_buffer_edit.setPlaceholderText("DE AD BE EF ...")
        self.write_buffer_edit.setFont(mono)
        self.write_output_btn = QPushButton("Write Output →")
        self.write_output_btn.setEnabled(False)
        self.write_output_btn.clicked.connect(self._write_output)
        write_row.addWidget(self.write_buffer_edit)
        write_row.addWidget(self.write_output_btn)
        layout.addLayout(write_row)

        group.setLayout(layout)
        return group

    # ------------------------------------------------------------------
    # Config load/save
    # ------------------------------------------------------------------
    def _collect_config(self) -> GatewayConfig:
        return GatewayConfig(
            tcp=TcpConfig(
                enabled=self.tcp_enabled.isChecked(),
                host=self.tcp_host_edit.text().strip() or "0.0.0.0",
                port=self.tcp_port_spin.value(),
            ),
            udp=UdpConfig(
                enabled=self.udp_enabled.isChecked(),
                host=self.udp_host_edit.text().strip() or "0.0.0.0",
                port=self.udp_port_spin.value(),
            ),
            cifx=CifxConfig(
                board_name=self.board_name_edit.text().strip() or "cifX0",
                channel=self.channel_spin.value(),
                io_timeout_ms=self.timeout_spin.value(),
                dll_path=self.dll_path_edit.text().strip() or None,
                mock=self.mock_checkbox.isChecked(),
            ),
        )

    def _apply_config(self, config: GatewayConfig) -> None:
        self.board_name_edit.setText(config.cifx.board_name)
        self.channel_spin.setValue(config.cifx.channel)
        self.timeout_spin.setValue(config.cifx.io_timeout_ms)
        self.dll_path_edit.setText(config.cifx.dll_path or "")
        self.mock_checkbox.setChecked(config.cifx.mock)
        self.tcp_enabled.setChecked(config.tcp.enabled)
        self.tcp_host_edit.setText(config.tcp.host)
        self.tcp_port_spin.setValue(config.tcp.port)
        self.udp_enabled.setChecked(config.udp.enabled)
        self.udp_host_edit.setText(config.udp.host)
        self.udp_port_spin.setValue(config.udp.port)

    def _browse_dll(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select cifX driver DLL", "", "DLL files (*.dll)")
        if path:
            self.dll_path_edit.setText(path)

    def _open_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Gateway Config", "", "JSON files (*.json)")
        if not path:
            return
        try:
            config = GatewayConfig.load(path)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Failed to load config", str(exc))
            return
        self._apply_config(config)
        self._current_config_path = path

    def _save_config(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Gateway Config", self._current_config_path or "gateway.json", "JSON files (*.json)"
        )
        if not path:
            return
        config = self._collect_config()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(dataclasses.asdict(config), fh, indent=2)
        except OSError as exc:
            QMessageBox.critical(self, "Failed to save config", str(exc))
            return
        self._current_config_path = path

    # ------------------------------------------------------------------
    # Gateway lifecycle
    # ------------------------------------------------------------------
    def _start_gateway(self) -> None:
        if self.runner is not None:
            return
        config = self._collect_config()
        runner = GatewayRunner(config)
        try:
            runner.start()
        except Exception as exc:
            QMessageBox.critical(self, "Failed to start gateway", str(exc))
            return
        self.runner = runner
        self._set_running_ui(True)
        self._poll_timer.start()
        logger.info("gateway started from GUI")

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
        logger.info("gateway stopped from GUI")

    def _set_running_ui(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.write_output_btn.setEnabled(running)
        for widget in self._config_widgets:
            widget.setEnabled(not running)

        if running:
            self.running_label.setText("Running")
            self.running_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.running_label.setText("Stopped")
            self.running_label.setStyleSheet("color: red; font-weight: bold;")
            self.bus_state_label.setText("-")
            self.host_state_label.setText("-")
            self.tcp_clients_label.setText("-")
            self.input_hex_view.clear()
            self.output_hex_view.clear()

    # ------------------------------------------------------------------
    # Live polling
    # ------------------------------------------------------------------
    def _poll(self) -> None:
        if self.runner is None:
            return
        backend = self.runner.backend
        offset = self.offset_spin.value()

        try:
            bus_state, host_state = backend.get_status()
            self.bus_state_label.setText("ON" if bus_state else "OFF")
            self.host_state_label.setText("READY" if host_state else "NOT READY")

            input_data = backend.io_read(0, offset, self.input_len_spin.value())
            self.input_hex_view.setText(_bytes_to_hex(input_data))

            output_data = backend.io_read_output(0, offset, self.output_len_spin.value())
            self.output_hex_view.setText(_bytes_to_hex(output_data))
        except Exception as exc:
            logger.warning("status/IO poll failed: %s", exc)

        client_count = self.runner.tcp_client_count
        self.tcp_clients_label.setText(str(client_count) if client_count is not None else "n/a")

    def _write_output(self) -> None:
        if self.runner is None:
            return
        try:
            data = _hex_to_bytes(self.write_buffer_edit.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid hex", f"Could not parse hex bytes: {exc}")
            return
        if not data:
            return
        try:
            self.runner.backend.io_write(0, self.offset_spin.value(), data)
        except Exception as exc:
            QMessageBox.critical(self, "Write failed", str(exc))

    # ------------------------------------------------------------------
    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.runner is not None:
            self._stop_gateway()
        super().closeEvent(event)
