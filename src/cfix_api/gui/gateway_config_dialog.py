"""Modal dialog for the gateway's TCP/UDP transport settings."""

from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..gateway.config import GatewayConfig, TcpConfig, UdpConfig


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

        layout.addWidget(tcp_group)
        layout.addWidget(udp_group)

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
        )
