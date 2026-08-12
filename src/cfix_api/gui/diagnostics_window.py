"""Diagnostics window: live TCP/UDP traffic log + card process-data monitor.

Non-modal (opened with .show(), never .exec()) so it can stay open and
refresh while the main window keeps working. It always reads the current
MainWindow.runner fresh on each poll tick rather than capturing it once,
so it keeps working correctly across Restart Gateway / config changes
that swap in a new GatewayRunner underneath it.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

POLL_INTERVAL_MS = 300
MAX_ROWS_SHOWN = 200


def _bytes_to_hex(data: bytes) -> str:
    return data.hex(" ").upper()


class DiagnosticsWindow(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("Diagnostics")
        self.setMinimumSize(760, 560)

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        mono = QFont("Courier New", 9)

        traffic_group = QGroupBox("TCP / UDP Traffic")
        traffic_layout = QVBoxLayout()

        header_row = QHBoxLayout()
        self.traffic_status_label = QLabel("-")
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_traffic_log)
        header_row.addWidget(self.traffic_status_label)
        header_row.addStretch()
        header_row.addWidget(clear_btn)
        traffic_layout.addLayout(header_row)

        self.traffic_table = QTableWidget(0, 5)
        self.traffic_table.setHorizontalHeaderLabels(["Time", "Transport", "Peer", "Request", "Response"])
        self.traffic_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.traffic_table.verticalHeader().setVisible(False)
        self.traffic_table.setFont(mono)
        header = self.traffic_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        traffic_layout.addWidget(self.traffic_table)
        traffic_group.setLayout(traffic_layout)
        layout.addWidget(traffic_group, stretch=1)

        io_group = QGroupBox("Card Process Data")
        io_layout = QVBoxLayout()

        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel("Offset"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 4096)
        offset_row.addWidget(self.offset_spin)
        offset_row.addWidget(QLabel("Length"))
        self.length_spin = QSpinBox()
        self.length_spin.setRange(1, 256)
        self.length_spin.setValue(32)
        offset_row.addWidget(self.length_spin)
        offset_row.addStretch()
        io_layout.addLayout(offset_row)

        io_layout.addWidget(QLabel("Input (from drive):"))
        self.input_hex_view = QLabel("-")
        self.input_hex_view.setFont(mono)
        self.input_hex_view.setWordWrap(True)
        io_layout.addWidget(self.input_hex_view)

        io_layout.addWidget(QLabel("Output (to drive):"))
        self.output_hex_view = QLabel("-")
        self.output_hex_view.setFont(mono)
        self.output_hex_view.setWordWrap(True)
        io_layout.addWidget(self.output_hex_view)

        io_group.setLayout(io_layout)
        layout.addWidget(io_group)

    def _clear_traffic_log(self) -> None:
        runner = self.main_window.runner
        if runner is not None:
            runner.traffic_log.clear()
        self._refresh()

    def _refresh(self) -> None:
        runner = self.main_window.runner
        if runner is None:
            self.traffic_status_label.setText("Gateway not running")
            self.input_hex_view.setText("-")
            self.output_hex_view.setText("-")
            return

        all_events = runner.traffic_log.snapshot()
        events = all_events[-MAX_ROWS_SHOWN:]
        self.traffic_status_label.setText(f"{len(events)} shown (of {len(all_events)} kept)")

        self.traffic_table.setRowCount(len(events))
        for row, event in enumerate(events):
            self.traffic_table.setItem(row, 0, QTableWidgetItem(f"{event.timestamp:.3f}"))
            self.traffic_table.setItem(row, 1, QTableWidgetItem(event.transport))
            self.traffic_table.setItem(row, 2, QTableWidgetItem(event.peer))
            self.traffic_table.setItem(row, 3, QTableWidgetItem(event.request_summary))
            self.traffic_table.setItem(row, 4, QTableWidgetItem(event.response_summary))
        if events:
            self.traffic_table.scrollToBottom()

        offset = self.offset_spin.value()
        length = self.length_spin.value()
        try:
            input_data = runner.backend.io_read(0, offset, length)
            self.input_hex_view.setText(_bytes_to_hex(input_data))
        except Exception as exc:
            self.input_hex_view.setText(f"<error: {exc}>")
        try:
            output_data = runner.backend.io_read_output(0, offset, length)
            self.output_hex_view.setText(_bytes_to_hex(output_data))
        except Exception as exc:
            self.output_hex_view.setText(f"<error: {exc}>")

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
