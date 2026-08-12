"""GUI tests, skipped automatically if PySide6 isn't installed (it's an
optional 'gui' extra). Run with QT_QPA_PLATFORM=offscreen in headless CI.
"""

import socket
import struct
import time

import pytest

pyside6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cfix_api.gateway.protocol import Command, Request, decode_response, encode_request  # noqa: E402
from cfix_api.gui.log_handler import QtLogHandler  # noqa: E402
from cfix_api.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    win = MainWindow(QtLogHandler())
    yield win
    if win.runner is not None:
        win._stop_gateway()


def test_defaults_to_mock_backend(window):
    assert window.mock_checkbox.isChecked()


def test_start_stop_lifecycle(window):
    window.tcp_port_spin.setValue(19800)
    window.udp_port_spin.setValue(19801)

    window._start_gateway()
    assert window.runner is not None
    assert not window.start_btn.isEnabled()
    assert window.stop_btn.isEnabled()
    assert not window.board_name_edit.isEnabled()

    window._stop_gateway()
    assert window.runner is None
    assert window.start_btn.isEnabled()
    assert window.board_name_edit.isEnabled()
    assert window.bus_state_label.text() == "-"


def test_write_then_poll_reflects_output(window):
    window.tcp_port_spin.setValue(19802)
    window.udp_port_spin.setValue(19803)
    window._start_gateway()

    window.write_buffer_edit.setText("DE AD BE EF")
    window._write_output()
    window._poll()

    assert window.output_hex_view.text().startswith("DE AD BE EF")
    assert window.bus_state_label.text() == "ON"


def test_external_tcp_client_can_reach_gui_started_gateway(window):
    window.tcp_port_spin.setValue(19804)
    window.udp_port_spin.setValue(19805)
    window._start_gateway()

    host, port = window.runner._tcp_server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        frame = encode_request(Request(command=Command.GET_STATUS, area=0, offset=0, length=0))
        sock.sendall(struct.pack(">I", len(frame)) + frame)
        (length,) = struct.unpack(">I", sock.recv(4))
        response = decode_response(sock.recv(length))
    assert response.status == 0

    # The server-side handler thread notices the closed socket
    # asynchronously, so give it a moment before the count reflects it.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        window._poll()
        if window.tcp_clients_label.text() == "0":
            break
        time.sleep(0.05)
    assert window.tcp_clients_label.text() == "0"
