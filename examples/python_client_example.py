#!/usr/bin/env python3
"""Reference client for the CFIX gateway protocol (docs/PROTOCOL.md).

Useful for sanity-checking the gateway (including against the mock
backend, with no CIFX hardware) before wiring up a LabVIEW client. Not
part of the cfix_api package - kept standalone so it doubles as a plain
worked example of the wire format in a language other than LabVIEW.

Usage:
    python -m cfix_api.gateway.cli --config config/gateway.mock.json &
    python examples/python_client_example.py --transport tcp --port 9800
    python examples/python_client_example.py --transport udp --port 9801
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))

from cfix_api.gateway.protocol import Command, Request, decode_response, encode_request  # noqa: E402

LENGTH_PREFIX = struct.Struct(">I")


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_tcp(host: str, port: int, req: Request):
    frame = encode_request(req)
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(LENGTH_PREFIX.pack(len(frame)) + frame)
        (length,) = LENGTH_PREFIX.unpack(_recv_exact(sock, 4))
        return decode_response(_recv_exact(sock, length))


def send_udp(host: str, port: int, req: Request):
    frame = encode_request(req)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        sock.sendto(frame, (host, port))
        data, _ = sock.recvfrom(65536)
        return decode_response(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="CFIX gateway example client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--transport", choices=("tcp", "udp"), required=True)
    args = parser.parse_args()

    send = send_tcp if args.transport == "tcp" else send_udp

    write_req = Request(command=Command.WRITE_OUTPUT, area=0, offset=0, length=4, data=b"\xde\xad\xbe\xef")
    resp = send(args.host, args.port, write_req)
    print(f"WRITE_OUTPUT -> status={resp.status}")

    read_req = Request(command=Command.READ_OUTPUT, area=0, offset=0, length=4)
    resp = send(args.host, args.port, read_req)
    print(f"READ_OUTPUT  -> status={resp.status} data={resp.data.hex()}")

    status_req = Request(command=Command.GET_STATUS, area=0, offset=0, length=0)
    resp = send(args.host, args.port, status_req)
    if resp.status == 0 and len(resp.data) == 2:
        print(f"GET_STATUS   -> bus_state={resp.data[0]} host_state={resp.data[1]}")
    else:
        print(f"GET_STATUS   -> status={resp.status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
