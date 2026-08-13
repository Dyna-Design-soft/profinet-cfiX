"""Modal dialog for the gateway's TCP/UDP/streaming transport settings."""

from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..gateway.config import GatewayConfig, StreamConfig, TcpConfig, UdpConfig

_WRITE_FRAMING_FIXED = "Fixed size"
_WRITE_FRAMING_ASCII = 'ASCII length prefix (len"N" + N bytes)'


class GatewayConfigDialog(QDialog):
    def __init__(self, config: GatewayConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gateway Configuration")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        tcp_group = QGroupBox("TCP")
        tcp_form = QFormLayout()
        self.tcp_enabled = QCheckBox("Enabled")
        self.tcp_enabled.setChecked(config.tcp.enabled)
        self.tcp_host = QLineEdit(config.tcp.host)
        self.tcp_port = QSpinBox()
        self.tcp_port.setRange(1, 65535)
        self.tcp_port.setValue(config.tcp.port)
        tcp_form.addRow(self.tcp_enabled)
        tcp_form.addRow("Host", self.tcp_host)
        tcp_form.addRow("Port", self.tcp_port)
        tcp_group.setLayout(tcp_form)

        udp_group = QGroupBox("UDP")
        udp_form = QFormLayout()
        self.udp_enabled = QCheckBox("Enabled")
        self.udp_enabled.setChecked(config.udp.enabled)
        self.udp_host = QLineEdit(config.udp.host)
        self.udp_port = QSpinBox()
        self.udp_port.setRange(1, 65535)
        self.udp_port.setValue(config.udp.port)
        udp_form.addRow(self.udp_enabled)
        udp_form.addRow("Host", self.udp_host)
        udp_form.addRow("Port", self.udp_port)
        udp_group.setLayout(udp_form)

        stream_group = QGroupBox("Streaming mode (raw, no command byte)")
        stream_form = QFormLayout()
        self.stream_enabled = QCheckBox("Enabled (replaces the framed TCP protocol above)")
        self.stream_enabled.setChecked(config.stream.enabled)
        self.stream_area = QSpinBox()
        self.stream_area.setRange(0, 255)
        self.stream_area.setValue(config.stream.area)
        self.stream_write_framing = QComboBox()
        self.stream_write_framing.addItems([_WRITE_FRAMING_FIXED, _WRITE_FRAMING_ASCII])
        self.stream_write_framing.setCurrentText(
            _WRITE_FRAMING_ASCII if config.stream.write_framing == "ascii_length_prefix" else _WRITE_FRAMING_FIXED
        )
        self.stream_write_offset = QSpinBox()
        self.stream_write_offset.setRange(0, 65535)
        self.stream_write_offset.setValue(config.stream.write_offset)
        self.stream_write_length = QSpinBox()
        self.stream_write_length.setRange(1, 65535)
        self.stream_write_length.setValue(config.stream.write_length)
        self.stream_read_offset = QSpinBox()
        self.stream_read_offset.setRange(0, 65535)
        self.stream_read_offset.setValue(config.stream.read_offset)
        self.stream_read_length = QSpinBox()
        self.stream_read_length.setRange(1, 65535)
        self.stream_read_length.setValue(config.stream.read_length)
        self.stream_poll_interval_ms = QSpinBox()
        self.stream_poll_interval_ms.setRange(1, 60000)
        self.stream_poll_interval_ms.setValue(config.stream.poll_interval_ms)

        def _update_write_length_enabled() -> None:
            self.stream_write_length.setEnabled(self.stream_write_framing.currentText() == _WRITE_FRAMING_FIXED)

        self.stream_write_framing.currentTextChanged.connect(_update_write_length_enabled)
        _update_write_length_enabled()

        stream_form.addRow(self.stream_enabled)
        stream_form.addRow("Area", self.stream_area)
        stream_form.addRow("Write framing", self.stream_write_framing)
        stream_form.addRow("Write offset", self.stream_write_offset)
        stream_form.addRow("Write length (fixed mode only)", self.stream_write_length)
        stream_form.addRow("Read offset", self.stream_read_offset)
        stream_form.addRow("Read length", self.stream_read_length)
        stream_form.addRow("Poll interval (ms)", self.stream_poll_interval_ms)
        stream_group.setLayout(stream_form)

        layout.addWidget(tcp_group)
        layout.addWidget(udp_group)
        layout.addWidget(stream_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to(self, config: GatewayConfig) -> GatewayConfig:
        return dataclasses.replace(
            config,
            tcp=TcpConfig(
                enabled=self.tcp_enabled.isChecked(),
                host=self.tcp_host.text().strip() or "0.0.0.0",
                port=self.tcp_port.value(),
            ),
            udp=UdpConfig(
                enabled=self.udp_enabled.isChecked(),
                host=self.udp_host.text().strip() or "0.0.0.0",
                port=self.udp_port.value(),
            ),
            stream=StreamConfig(
                enabled=self.stream_enabled.isChecked(),
                area=self.stream_area.value(),
                write_offset=self.stream_write_offset.value(),
                write_framing=(
                    "ascii_length_prefix"
                    if self.stream_write_framing.currentText() == _WRITE_FRAMING_ASCII
                    else "fixed"
                ),
                write_length=self.stream_write_length.value(),
                read_offset=self.stream_read_offset.value(),
                read_length=self.stream_read_length.value(),
                poll_interval_ms=self.stream_poll_interval_ms.value(),
            ),
        )
