import socket
import struct
import time

import pytest

from cfix_api.cifx.backend import MockCifXBackend
from cfix_api.gateway.protocol import Command, Request, Status, decode_response, encode_request
from cfix_api.gateway.tcp_server import END_BYTE, START_BYTE, TcpGatewayServer, _Handler
from cfix_api.gateway.traffic_log import TrafficLog

LENGTH_PREFIX = struct.Struct(">I")


@pytest.fixture
def tcp_gateway():
    backend = MockCifXBackend()
    backend.open()
    server = TcpGatewayServer("127.0.0.1", 0, backend)
    server.serve_forever_in_thread()
    yield server
    server.shutdown()
    server.server_close()
    backend.close()


def _send_request(sock: socket.socket, req: Request) -> bytes:
    frame = encode_request(req)
    sock.sendall(bytes([START_BYTE]) + LENGTH_PREFIX.pack(len(frame)) + frame + bytes([END_BYTE]))
    start = _recv_exact(sock, 1)
    assert start[0] == START_BYTE
    (length,) = LENGTH_PREFIX.unpack(_recv_exact(sock, 4))
    response = _recv_exact(sock, length)
    end = _recv_exact(sock, 1)
    assert end[0] == END_BYTE
    return response


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        assert chunk, "connection closed unexpectedly"
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def test_write_then_read_output_roundtrip(tcp_gateway):
    host, port = tcp_gateway.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        write_req = Request(
            command=Command.WRITE_OUTPUT, area=0, offset=0, length=4, data=b"\x11\x22\x33\x44"
        )
        resp_frame = _send_request(sock, write_req)
        resp = decode_response(resp_frame)
        assert resp.status == Status.OK

        read_req = Request(command=Command.READ_OUTPUT, area=0, offset=0, length=4)
        resp_frame = _send_request(sock, read_req)
        resp = decode_response(resp_frame)
        assert resp.status == Status.OK
        assert resp.data == b"\x11\x22\x33\x44"


def test_get_status(tcp_gateway):
    host, port = tcp_gateway.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        resp_frame = _send_request(sock, Request(command=Command.GET_STATUS, area=0, offset=0, length=0))
        resp = decode_response(resp_frame)
        assert resp.status == Status.OK
        assert len(resp.data) == 2


def test_pipelined_requests_answered_in_order(tcp_gateway):
    host, port = tcp_gateway.server_address
    with socket.create_connection((host, port), timeout=2) as sock:
        for offset in range(3):
            data = bytes([offset, offset, offset, offset])
            resp_frame = _send_request(
                sock, Request(command=Command.WRITE_OUTPUT, area=0, offset=offset * 4, length=4, data=data)
            )
            assert decode_response(resp_frame).status == Status.OK

        for offset in range(3):
            resp_frame = _send_request(
                sock, Request(command=Command.READ_OUTPUT, area=0, offset=offset * 4, length=4)
            )
            resp = decode_response(resp_frame)
            assert resp.data == bytes([offset, offset, offset, offset])


def test_bad_start_byte_closes_connection(tcp_gateway):
    host, port = tcp_gateway.server_address
    frame = encode_request(Request(command=Command.GET_STATUS, area=0, offset=0, length=0))
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(bytes([0x00]) + LENGTH_PREFIX.pack(len(frame)) + frame + bytes([END_BYTE]))
        assert sock.recv(1) == b""


def test_bad_end_byte_closes_connection(tcp_gateway):
    host, port = tcp_gateway.server_address
    frame = encode_request(Request(command=Command.GET_STATUS, area=0, offset=0, length=0))
    with socket.create_connection((host, port), timeout=2) as sock:
        # Bad end byte is caught before the request is dispatched, so no
        # response is sent - the connection just closes.
        sock.sendall(bytes([START_BYTE]) + LENGTH_PREFIX.pack(len(frame)) + frame + bytes([0x00]))
        assert sock.recv(1) == b""


def test_handler_disables_nagle_on_accepted_socket():
    """TCP_NODELAY matters for this lock-step small-frame protocol - see
    the "Latency" section in README.md. Regression-guard it directly
    since it isn't otherwise observable from a test client socket."""

    class _FakeSocket:
        def __init__(self):
            self.calls = []

        def setsockopt(self, level, optname, value):
            self.calls.append((level, optname, value))

    handler = _Handler.__new__(_Handler)  # bypass BaseRequestHandler.__init__
    handler.request = _FakeSocket()
    handler.setup()

    assert (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) in handler.request.calls


def test_traffic_log_records_request_and_response():
    backend = MockCifXBackend()
    backend.open()
    traffic_log = TrafficLog()
    server = TcpGatewayServer("127.0.0.1", 0, backend, traffic_log)
    server.serve_forever_in_thread()
    try:
        host, port = server.server_address
        with socket.create_connection((host, port), timeout=2) as sock:
            _send_request(
                sock, Request(command=Command.WRITE_OUTPUT, area=0, offset=0, length=4, data=b"\xde\xad\xbe\xef")
            )

        events = traffic_log.snapshot()
        assert len(events) == 1
        event = events[0]
        assert event.transport == "TCP"
        assert event.peer.startswith("127.0.0.1:")
        assert "WRITE_OUTPUT" in event.request_summary
        assert "status=OK" in event.response_summary
    finally:
        server.shutdown()
        server.server_close()
        backend.close()
