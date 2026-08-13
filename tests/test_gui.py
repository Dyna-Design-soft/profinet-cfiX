"""GUI tests, skipped automatically if PySide6 isn't installed (it's an
optional 'gui' extra). Run with QT_QPA_PLATFORM=offscreen in headless CI.

Dialog.exec() opens a real modal event loop that only returns once
"accepted"/"rejected" - with no user present that would hang a test
forever, so these tests exercise dialog widgets and MainWindow's
restart/persistence logic directly rather than calling exec().
"""

import dataclasses
import socket
import struct
import time

import pytest

pyside6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cfix_api.gateway.config import CifxConfig, GatewayConfig, StreamConfig, TcpConfig, UdpConfig  # noqa: E402
from cfix_api.gateway.protocol import Command, Request, decode_response, encode_request  # noqa: E402
from cfix_api.gateway.tcp_server import END_BYTE, START_BYTE  # noqa: E402
from cfix_api.gui.diagnostics_window import DiagnosticsWindow  # noqa: E402
from cfix_api.gui.dll_config_dialog import DllConfigDialog  # noqa: E402
from cfix_api.gui.gateway_config_dialog import GatewayConfigDialog  # noqa: E402
from cfix_api.gui.gui_settings import load_settings, save_settings  # noqa: E402
from cfix_api.gui.log_handler import QtLogHandler  # noqa: E402
from cfix_api.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path):
    settings_path = tmp_path / "gui_config.json"
    win = MainWindow(QtLogHandler(), autostart=False, settings_path=settings_path)
    yield win
    if win.runner is not None:
        win._stop_gateway()


def _send_framed_request(sock: socket.socket, req: Request):
    """Sends one request over the framed TCP protocol (start byte + u32
    length + frame + end byte, see tcp_server.py) and returns the decoded
    response."""
    frame = encode_request(req)
    sock.sendall(bytes([START_BYTE]) + struct.pack(">I", len(frame)) + frame + bytes([END_BYTE]))
    start = sock.recv(1)
    assert start == bytes([START_BYTE])
    (length,) = struct.unpack(">I", sock.recv(4))
    response = sock.recv(length)
    end = sock.recv(1)
    assert end == bytes([END_BYTE])
    return decode_response(response)


def test_first_run_defaults_to_mock_backend(tmp_path):
    config = load_settings(tmp_path / "does_not_exist.json")
    assert config.cifx.mock is True


def test_settings_round_trip(tmp_path):
    path = tmp_path / "gui_config.json"
    config = GatewayConfig(
        tcp=TcpConfig(port=19850),
        udp=UdpConfig(port=19851),
        cifx=CifxConfig(board_name="cifX1", mock=True),
    )
    save_settings(config, path)
    reloaded = load_settings(path)
    assert reloaded.tcp.port == 19850
    assert reloaded.udp.port == 19851
    assert reloaded.cifx.board_name == "cifX1"


def test_autostart_starts_gateway(qapp, tmp_path):
    win = MainWindow(QtLogHandler(), autostart=True, settings_path=tmp_path / "gui_config.json")
    try:
        assert win.runner is not None
        assert win.running_label.text() == "Running"
    finally:
        win._stop_gateway()


def test_manual_start_stop_and_ui_state(window):
    window.config.tcp.port = 19852
    window.config.udp.port = 19853
    window._start_gateway()
    assert window.runner is not None
    assert window.running_label.text() == "Running"

    window._stop_gateway()
    assert window.runner is None
    assert window.running_label.text() == "Stopped"
    assert window.bus_state_label.text() == "-"


def test_restart_applies_new_config(window):
    window.config = dataclasses.replace(window.config, tcp=TcpConfig(port=19854), udp=UdpConfig(port=19855))
    window._start_gateway()
    assert window.runner.config.tcp.port == 19854

    window.config = dataclasses.replace(window.config, tcp=TcpConfig(port=19856), udp=UdpConfig(port=19857))
    window._restart_gateway()
    assert window.runner is not None
    assert window.runner.config.tcp.port == 19856

    host, port = window.runner._tcp_server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        response = _send_framed_request(sock, Request(command=Command.GET_STATUS, area=0, offset=0, length=0))
    assert response.status == 0
    assert port == 19856


def test_close_event_stops_gateway(window):
    window.config.tcp.port = 19858
    window.config.udp.port = 19859
    window._start_gateway()
    assert window.runner is not None

    window.close()
    assert window.runner is None


def test_gateway_config_dialog_apply_to_changes_ports(qapp):
    config = GatewayConfig()
    dialog = GatewayConfigDialog(config)
    dialog.tcp_port.setValue(19860)
    dialog.udp_enabled.setChecked(False)
    updated = dialog.apply_to(config)
    assert updated.tcp.port == 19860
    assert updated.udp.enabled is False
    # apply_to must not mutate the original config in place.
    assert config.tcp.port != 19860


def test_gateway_config_dialog_apply_to_changes_stream_settings(qapp):
    from cfix_api.gui.gateway_config_dialog import _WRITE_FRAMING_ASCII

    config = GatewayConfig()
    dialog = GatewayConfigDialog(config)
    dialog.stream_enabled.setChecked(True)
    dialog.stream_area.setValue(1)
    dialog.stream_write_framing.setCurrentText(_WRITE_FRAMING_ASCII)
    dialog.stream_write_offset.setValue(10)
    dialog.stream_read_offset.setValue(20)
    dialog.stream_read_length.setValue(103)
    dialog.stream_poll_interval_ms.setValue(5)

    updated = dialog.apply_to(config)
    assert updated.stream.enabled is True
    assert updated.stream.area == 1
    assert updated.stream.write_framing == "ascii_length_prefix"
    assert updated.stream.write_offset == 10
    assert updated.stream.read_offset == 20
    assert updated.stream.read_length == 103
    assert updated.stream.poll_interval_ms == 5
    # apply_to must not mutate the original config in place.
    assert config.stream.enabled is False


def test_gateway_config_dialog_write_length_disabled_in_ascii_mode(qapp):
    from cfix_api.gui.gateway_config_dialog import _WRITE_FRAMING_ASCII, _WRITE_FRAMING_FIXED

    dialog = GatewayConfigDialog(GatewayConfig())
    assert dialog.stream_write_length.isEnabled() is True
    dialog.stream_write_framing.setCurrentText(_WRITE_FRAMING_ASCII)
    assert dialog.stream_write_length.isEnabled() is False
    dialog.stream_write_framing.setCurrentText(_WRITE_FRAMING_FIXED)
    assert dialog.stream_write_length.isEnabled() is True


def test_dll_config_dialog_apply_to_changes_board(qapp):
    config = GatewayConfig()
    dialog = DllConfigDialog(config)
    dialog.board_name.setText("cifX2")
    dialog.mock.setChecked(True)
    updated = dialog.apply_to(config)
    assert updated.cifx.board_name == "cifX2"
    assert updated.cifx.mock is True


def test_open_gateway_config_dialog_saves_and_restarts(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    window.config.tcp.port = 19862
    window.config.udp.port = 19863
    window._start_gateway()

    def fake_exec(self):
        self.tcp_port.setValue(19870)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(GatewayConfigDialog, "exec", fake_exec)
    window._open_gateway_config()

    assert window.runner is not None
    assert window.runner.config.tcp.port == 19870

    reloaded = load_settings(window._settings_path)
    assert reloaded.tcp.port == 19870


def test_poll_updates_status_labels(window):
    window.config.tcp.port = 19864
    window.config.udp.port = 19865
    window._start_gateway()
    window._poll()
    assert window.bus_state_label.text() == "ON"
    assert window.host_state_label.text() == "NOT READY"
    assert window.tcp_clients_label.text() == "0"


def test_tcp_client_count_reflects_active_connection(window):
    window.config.tcp.port = 19866
    window.config.udp.port = 19867
    window._start_gateway()

    host, port = window.runner._tcp_server.server_address
    with socket.create_connection((host, port), timeout=2):
        # The server-side handler thread notices the new connection
        # asynchronously, so give it a moment before the count reflects it.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            window._poll()
            if window.tcp_clients_label.text() == "1":
                break
            time.sleep(0.05)
        assert window.tcp_clients_label.text() == "1"

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        window._poll()
        if window.tcp_clients_label.text() == "0":
            break
        time.sleep(0.05)
    assert window.tcp_clients_label.text() == "0"


def test_diagnostics_window_shows_not_running_when_gateway_stopped(window):
    diag = DiagnosticsWindow(window)
    try:
        diag._refresh()
        assert "not running" in diag.traffic_status_label.text().lower()
        assert diag.input_hex_view.text() == "-"
    finally:
        diag.close()


def test_diagnostics_window_shows_traffic_and_io_after_request(window):
    window.config.tcp.port = 19868
    window.config.udp.port = 19869
    window._start_gateway()

    host, port = window.runner._tcp_server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        _send_framed_request(
            sock, Request(command=Command.WRITE_OUTPUT, area=0, offset=0, length=4, data=b"\xde\xad\xbe\xef")
        )

    diag = DiagnosticsWindow(window)
    try:
        diag._refresh()
        assert diag.traffic_table.rowCount() == 1
        assert "WRITE_OUTPUT" in diag.traffic_table.item(0, 3).text()
        assert "status=OK" in diag.traffic_table.item(0, 4).text()
        assert diag.output_hex_view.text().startswith("DE AD BE EF")

        diag._clear_traffic_log()
        assert diag.traffic_table.rowCount() == 0
    finally:
        diag.close()


def test_diagnostics_window_shows_na_throughput_in_framed_mode(window):
    window.config.tcp.port = 19870
    window.config.udp.port = 19871
    window._start_gateway()

    diag = DiagnosticsWindow(window)
    try:
        diag._refresh()
        assert "n/a" in diag.throughput_label.text().lower()
    finally:
        diag.close()


def test_diagnostics_window_shows_streaming_throughput(window):
    window.config = dataclasses.replace(
        window.config,
        tcp=TcpConfig(port=19872),
        udp=UdpConfig(enabled=False),
        stream=StreamConfig(enabled=True, write_length=4, read_length=4, poll_interval_ms=5),
    )
    window._start_gateway()

    diag = DiagnosticsWindow(window)
    try:
        host, port = window.runner._tcp_server.server_address
        with socket.create_connection((host, port), timeout=2) as sock:
            diag._refresh()  # first sample, establishes the baseline
            sock.sendall(b"\x11\x22\x33\x44")
            time.sleep(0.2)
            diag._refresh()  # second sample, should compute a rate against the baseline
        text = diag.throughput_label.text()
        assert "n/a" not in text.lower()
        assert "KB/s" in text
    finally:
        diag.close()


def test_open_diagnostics_reuses_same_window_instance(window):
    window._open_diagnostics()
    first = window._diagnostics_window
    window._open_diagnostics()
    second = window._diagnostics_window
    assert first is second
    first.close()
