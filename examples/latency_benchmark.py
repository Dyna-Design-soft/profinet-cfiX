#!/usr/bin/env python3
"""Measures round-trip latency against a running CFIX gateway.

This is the actual empirical check for a cyclic latency budget (e.g.
"needs to land within 20-50ms") - run it against your real deployment
rather than trusting the number in a doc. It keeps one connection open
and repeats a WRITE_OUTPUT + READ_INPUT round trip back to back, the
same pattern a LabVIEW cyclic control loop would use.

Usage:
    python -m cfix_api.gateway.cli --config config/gateway.mock.json &
    python examples/latency_benchmark.py --transport tcp --port 9800
    python examples/latency_benchmark.py --transport udp --port 9801 -n 2000
"""

from __future__ import annotations

import argparse
import socket
import statistics
import struct
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))

from cfix_api.gateway.protocol import Command, Request, decode_response, encode_request  # noqa: E402
from cfix_api.gateway.tcp_server import END_BYTE, START_BYTE  # noqa: E402

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


def _round_trip_tcp(sock: socket.socket, frame: bytes) -> bytes:
    sock.sendall(bytes([START_BYTE]) + LENGTH_PREFIX.pack(len(frame)) + frame + bytes([END_BYTE]))
    start = _recv_exact(sock, 1)
    if start[0] != START_BYTE:
        raise ConnectionError(f"bad start byte 0x{start[0]:02x}")
    (length,) = LENGTH_PREFIX.unpack(_recv_exact(sock, 4))
    response = _recv_exact(sock, length)
    end = _recv_exact(sock, 1)
    if end[0] != END_BYTE:
        raise ConnectionError(f"bad end byte 0x{end[0]:02x}")
    return response


def _round_trip_udp(sock: socket.socket, addr, frame: bytes) -> bytes:
    sock.sendto(frame, addr)
    data, _ = sock.recvfrom(65536)
    return data


def run(host: str, port: int, transport: str, iterations: int, data_len: int) -> list[float]:
    write_frame = encode_request(
        Request(command=Command.WRITE_OUTPUT, area=0, offset=0, length=data_len, data=bytes(data_len))
    )
    read_frame = encode_request(Request(command=Command.READ_INPUT, area=0, offset=0, length=data_len))

    samples_ms: list[float] = []

    if transport == "tcp":
        sock = socket.create_connection((host, port), timeout=2)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            for _ in range(iterations):
                start = time.perf_counter()
                _round_trip_tcp(sock, write_frame)
                _round_trip_tcp(sock, read_frame)
                samples_ms.append((time.perf_counter() - start) * 1000.0)
        finally:
            sock.close()
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        addr = (host, port)
        try:
            for _ in range(iterations):
                start = time.perf_counter()
                resp = decode_response(_round_trip_udp(sock, addr, write_frame))
                if resp.status != 0:
                    raise RuntimeError(f"WRITE_OUTPUT failed: status={resp.status}")
                resp = decode_response(_round_trip_udp(sock, addr, read_frame))
                if resp.status != 0:
                    raise RuntimeError(f"READ_INPUT failed: status={resp.status}")
                samples_ms.append((time.perf_counter() - start) * 1000.0)
        finally:
            sock.close()

    return samples_ms


def _percentile(sorted_samples: list[float], pct: float) -> float:
    if not sorted_samples:
        return float("nan")
    index = min(len(sorted_samples) - 1, int(round(pct / 100.0 * (len(sorted_samples) - 1))))
    return sorted_samples[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="CFIX gateway round-trip latency benchmark")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--transport", choices=("tcp", "udp"), required=True)
    parser.add_argument("-n", "--iterations", type=int, default=500)
    parser.add_argument("--data-len", type=int, default=4, help="bytes written/read per cycle")
    parser.add_argument(
        "--budget-ms", type=float, default=50.0, help="report how many round trips exceeded this"
    )
    args = parser.parse_args()

    print(
        f"Running {args.iterations} WRITE_OUTPUT+READ_INPUT round trips over "
        f"{args.transport.upper()} to {args.host}:{args.port} ({args.data_len} bytes each way)..."
    )
    samples = run(args.host, args.port, args.transport, args.iterations, args.data_len)
    sorted_samples = sorted(samples)

    over_budget = sum(1 for s in samples if s > args.budget_ms)

    print(f"\nRound trips     : {len(samples)}")
    print(f"Min             : {min(samples):.3f} ms")
    print(f"Median          : {statistics.median(samples):.3f} ms")
    print(f"Mean            : {statistics.fmean(samples):.3f} ms")
    print(f"p95             : {_percentile(sorted_samples, 95):.3f} ms")
    print(f"p99             : {_percentile(sorted_samples, 99):.3f} ms")
    print(f"Max             : {max(samples):.3f} ms")
    print(f"Over {args.budget_ms:.0f}ms budget : {over_budget} / {len(samples)}")

    return 1 if over_budget else 0


if __name__ == "__main__":
    sys.exit(main())
