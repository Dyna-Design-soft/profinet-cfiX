#!/usr/bin/env python3
"""Reference streaming-mode client with auto-reconnect (docs/PROTOCOL.md
"Streaming mode", docs/LABVIEW_INTEGRATION.md "Auto-reconnect").

Demonstrates the client-side pattern LabVIEW should mirror: an outer loop
that reopens the TCP connection whenever it drops (gateway restart, cable
pull, the gateway closing a desynced connection) instead of requiring a
human to notice and reconnect manually. Each write uses the
ascii_length_prefix framing (len"N" + N bytes); read is a fixed-size poll
chunk, matching config/gateway.mock.stream.json.

Usage:
    python -m cfix_api.gateway.cli --config config/gateway.mock.stream.json &
    python examples/stream_client_example.py --port 9800
    # then, to see the reconnect path: stop and restart the gateway while
    # this is running - it should print "connection lost", retry every
    # RECONNECT_DELAY_S, and resume once the gateway is back.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time

RECONNECT_DELAY_S = 1.0

# The confirmed 103-byte multi-drive frame from docs/LABVIEW_INTEGRATION.md's
# worked example: header(6) + drive1(64) + header(7) + drive2(24) + trailer(2).
FRAME = bytes.fromhex(
    "8080808080800400000000002c88d3781333eccd000002200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000080808080808080043e810000000000400000000000000000014000400040008080"
)


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


def run_connected(host: str, port: int, read_length: int, iterations: int, write_interval_s: float) -> None:
    """One connection's worth of work. Raises on any socket error - the
    caller (main) is responsible for reconnecting."""
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"connected to {host}:{port}")
        wire = f'len"{len(FRAME)}"'.encode("ascii") + FRAME
        for i in range(iterations):
            sock.sendall(wire)
            data = _recv_exact(sock, read_length)
            print(f"  [{i}] wrote {len(FRAME)} bytes, read back {data[:8].hex()}...")
            time.sleep(write_interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description="CFIX streaming-mode client with auto-reconnect")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--read-length", type=int, default=103, help="must match config.stream.read_length")
    parser.add_argument("--iterations-per-connection", type=int, default=20)
    parser.add_argument("--write-interval", type=float, default=0.2, help="seconds between writes")
    args = parser.parse_args()

    while True:
        try:
            run_connected(args.host, args.port, args.read_length, args.iterations_per_connection, args.write_interval)
            return 0
        except KeyboardInterrupt:
            return 0
        except (ConnectionError, OSError) as exc:
            print(f"connection lost ({exc}); reconnecting in {RECONNECT_DELAY_S}s...")
            time.sleep(RECONNECT_DELAY_S)


if __name__ == "__main__":
    sys.exit(main())
