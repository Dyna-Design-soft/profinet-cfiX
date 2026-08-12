import socket

import pytest

from cfix_api.cifx.backend import MockCifXBackend
from cfix_api.gateway.protocol import Command, Request, Status, decode_response, encode_request
from cfix_api.gateway.udp_server import UdpGatewayServer


@pytest.fixture
def udp_gateway():
    backend = MockCifXBackend()
    backend.open()
    server = UdpGatewayServer("127.0.0.1", 0, backend)
    server.serve_forever_in_thread()
    yield server
    server.shutdown()
    server.server_close()
    backend.close()


def _send_request(sock: socket.socket, addr, req: Request) -> bytes:
    sock.sendto(encode_request(req), addr)
    data, _ = sock.recvfrom(65536)
    return data


def test_write_then_read_output_roundtrip(udp_gateway):
    addr = udp_gateway.server_address
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        write_req = Request(
            command=Command.WRITE_OUTPUT, area=0, offset=8, length=2, data=b"\xaa\xbb"
        )
        resp = decode_response(_send_request(sock, addr, write_req))
        assert resp.status == Status.OK

        read_req = Request(command=Command.READ_OUTPUT, area=0, offset=8, length=2)
        resp = decode_response(_send_request(sock, addr, read_req))
        assert resp.status == Status.OK
        assert resp.data == b"\xaa\xbb"


def test_read_input_default_zeroed(udp_gateway):
    addr = udp_gateway.server_address
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        resp = decode_response(
            _send_request(sock, addr, Request(command=Command.READ_INPUT, area=0, offset=0, length=8))
        )
        assert resp.status == Status.OK
        assert resp.data == b"\x00" * 8


def test_unknown_command_returns_error_status(udp_gateway):
    addr = udp_gateway.server_address
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        bad_frame = bytes([0x99, 0, 0, 0, 0, 0])  # unknown command 0x99
        sock.sendto(bad_frame, addr)
        data, _ = sock.recvfrom(65536)
        resp = decode_response(data)
        assert resp.status == Status.UNKNOWN_COMMAND
