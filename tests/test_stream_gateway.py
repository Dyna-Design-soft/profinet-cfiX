import socket
import time

import pytest

from cfix_api.cifx.backend import MockCifXBackend
from cfix_api.gateway.config import StreamConfig
from cfix_api.gateway.stream_server import StreamGatewayServer


@pytest.fixture
def stream_gateway():
    backend = MockCifXBackend()
    backend.open()
    config = StreamConfig(
        enabled=True, area=0, write_offset=0, write_length=4, read_offset=0, read_length=4, poll_interval_ms=5
    )
    server = StreamGatewayServer("127.0.0.1", 0, backend, config)
    server.serve_forever_in_thread()
    yield server, backend
    server.shutdown()
    server.server_close()
    backend.close()


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        assert chunk, "connection closed unexpectedly"
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def test_poller_streams_input_image_without_any_write(stream_gateway):
    server, backend = stream_gateway
    backend.io_write(0, 0, b"\xaa\xbb\xcc\xdd")
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        chunk = _recv_exact(sock, 4)
        assert chunk == b"\xaa\xbb\xcc\xdd"


def test_write_reaches_output_image_and_is_polled_back(stream_gateway):
    server, backend = stream_gateway
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(b"\x11\x22\x33\x44")
        deadline = time.monotonic() + 2
        seen = b""
        while time.monotonic() < deadline:
            seen = _recv_exact(sock, 4)
            if seen == b"\x11\x22\x33\x44":
                break
        assert seen == b"\x11\x22\x33\x44"
    assert backend.io_read(0, 0, 4) == b"\x11\x22\x33\x44"


def test_no_frame_markers_on_the_wire(stream_gateway):
    """Unlike the framed TcpGatewayServer, raw bytes go straight through -
    no start/length/end wrapper to strip."""
    server, backend = stream_gateway
    backend.io_write(0, 0, b"\x01\x02\x03\x04")
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        chunk = _recv_exact(sock, 4)
        assert chunk == b"\x01\x02\x03\x04"


def test_connection_count_tracks_connect_and_disconnect(stream_gateway):
    server, _backend = stream_gateway
    assert server.connection_count == 0
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        _recv_exact(sock, 4)
        assert server.connection_count == 1
    deadline = time.monotonic() + 2
    while server.connection_count != 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.connection_count == 0


def test_bytes_written_counter_tracks_writes(stream_gateway):
    server, _backend = stream_gateway
    assert server.bytes_written == 0
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(b"\x11\x22\x33\x44")
        _recv_exact(sock, 4)  # drain one poll chunk so the handler loop has run at least once
        sock.sendall(b"\x55\x66\x77\x88")
        _recv_exact(sock, 4)
    assert server.bytes_written == 8


def test_bytes_read_counter_tracks_polls(stream_gateway):
    server, backend = stream_gateway
    backend.io_write(0, 0, b"\xaa\xbb\xcc\xdd")
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        for _ in range(5):
            _recv_exact(sock, 4)
    assert server.bytes_read >= 20


@pytest.fixture
def ascii_length_prefix_gateway():
    backend = MockCifXBackend()
    backend.open()
    config = StreamConfig(
        enabled=True,
        area=0,
        write_offset=0,
        write_framing="ascii_length_prefix",
        read_offset=0,
        read_length=4,
        poll_interval_ms=5,
    )
    server = StreamGatewayServer("127.0.0.1", 0, backend, config)
    server.serve_forever_in_thread()
    yield server, backend
    server.shutdown()
    server.server_close()
    backend.close()


def test_ascii_length_prefix_write_reaches_output_image(ascii_length_prefix_gateway):
    server, backend = ascii_length_prefix_gateway
    host, port = server.server_address
    frame = bytes.fromhex(
        "8080808080800400000000002c88d3781333eccd000002200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000080808080808080043e810000000000400000000000000000014000400040008080"
    )
    assert len(frame) == 103
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(f'len"{len(frame)}"'.encode("ascii") + frame)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if backend.io_read(0, 0, len(frame)) == frame:
                break
            time.sleep(0.02)
    assert backend.io_read(0, 0, len(frame)) == frame


def _assert_connection_closes(sock: socket.socket) -> None:
    """Reads (and discards) any in-flight poller bytes until the socket
    actually closes, instead of asserting on the very next recv() - the
    independent poll loop may still deliver a chunk or two first."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        chunk = sock.recv(4096)
        if chunk == b"":
            return
    pytest.fail("connection did not close within timeout")


def test_ascii_length_prefix_bad_literal_closes_connection(ascii_length_prefix_gateway):
    server, _backend = ascii_length_prefix_gateway
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(b'xen"4"\x01\x02\x03\x04')
        _assert_connection_closes(sock)


def test_ascii_length_prefix_non_digit_length_closes_connection(ascii_length_prefix_gateway):
    server, _backend = ascii_length_prefix_gateway
    host, port = server.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(b'len"4x"\x01\x02\x03\x04')
        _assert_connection_closes(sock)
