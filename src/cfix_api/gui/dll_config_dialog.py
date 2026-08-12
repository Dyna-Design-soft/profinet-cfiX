"""Modal dialog for cifX board/channel/driver DLL settings."""

from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..gateway.config import CifxConfig, GatewayConfig


class DllConfigDialog(QDialog):
    def __init__(self, config: GatewayConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DLL Configuration")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.board_name = QLineEdit(config.cifx.board_name)
        self.channel = QSpinBox()
        self.channel.setRange(0, 7)
        self.channel.setValue(config.cifx.channel)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 60000)
        self.timeout.setSuffix(" ms")
        self.timeout.setValue(config.cifx.io_timeout_ms)

        self.dll_path = QLineEdit(config.cifx.dll_path or "")
        self.dll_path.setPlaceholderText("auto-detect (cifx32dll.dll)")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        dll_row = QHBoxLayout()
        dll_row.addWidget(self.dll_path)
        dll_row.addWidget(browse_btn)
        dll_row_widget = QWidget()
        dll_row_widget.setLayout(dll_row)

        self.mock = QCheckBox("Use mock backend (no hardware required)")
        self.mock.setChecked(config.cifx.mock)

        form.addRow("Board name", self.board_name)
        form.addRow("Channel", self.channel)
        form.addRow("IO timeout", self.timeout)
        form.addRow("Driver DLL path", dll_row_widget)
        form.addRow("", self.mock)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select cifX driver DLL", "", "DLL files (*.dll)")
        if path:
            self.dll_path.setText(path)

    def apply_to(self, config: GatewayConfig) -> GatewayConfig:
        return dataclasses.replace(
            config,
            cifx=CifxConfig(
                board_name=self.board_name.text().strip() or "cifX0",
                channel=self.channel.value(),
                io_timeout_ms=self.timeout.value(),
                dll_path=self.dll_path.text().strip() or None,
                mock=self.mock.isChecked(),
            ),
        )
