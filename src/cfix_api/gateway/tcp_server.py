"""TCP gateway server: start/length/end-delimited framing over a persistent
connection.

Each request/response frame (see docs/PROTOCOL.md) is wrapped on the wire as
`[START byte][4-byte big-endian length][frame][END byte]`, where `length`
counts only the frame bytes (not the start byte, length field, or end byte).
The length field is authoritative for how many frame bytes to read; START and
END are sync/integrity markers checked at fixed offsets, not scanned for, so
arbitrary binary payload bytes never get misread as a delimiter. One thread
per client connection; requests on a connection are handled and answered
strictly in order.
"""

from __future__ import annotations

import logging
import socket
import socketserver
import struct
import threading
from typing import Optional

from ..cifx.backend import CifXBackend
from .dispatch import handle_frame
from .traffic_log import TrafficLog

logger = logging.getLogger("cfix_api.gateway.tcp")

START_BYTE = 0x82
END_BYTE = 0x83
_LENGTH_PREFIX = struct.Struct(">I")
MAX_FRAME_SIZE = 64 * 1024


def _recv_exact(sock, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class _Handler(socketserver.BaseRequestHandler):
    def setup(self) -> None:
        # This protocol is a small-frame, lock-step request/response
        # exchange (send, wait for the reply, repeat) - exactly the
        # pattern Nagle's algorithm (batching small writes) plus the
        # peer's delayed ACK can stall by tens of milliseconds. Disabling
        # it matters for a 20-50ms cyclic latency budget.
        self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def handle(self) -> None:
        server: TcpGatewayServer = self.server  # type: ignore[assignment]
        backend: CifXBackend = server.backend
        peer = self.client_address
        logger.info("TCP client connected: %s", peer)
        server._change_connection_count(1)
        try:
            while True:
                try:
                    start = _recv_exact(self.request, 1)
                except ConnectionError:
                    break
                if start[0] != START_BYTE:
                    logger.warning(
                        "TCP client %s sent bad start byte (0x%02x, expected 0x%02x); closing",
                        peer, start[0], START_BYTE,
                    )
                    break
                length_bytes = _recv_exact(self.request, _LENGTH_PREFIX.size)
                (length,) = _LENGTH_PREFIX.unpack(length_bytes)
                if length > MAX_FRAME_SIZE:
                    logger.warning("TCP client %s sent oversized frame (%d bytes); closing", peer, length)
                    break
                frame = _recv_exact(self.request, length)
                end = _recv_exact(self.request, 1)
                if end[0] != END_BYTE:
                    logger.warning(
                        "TCP client %s sent bad end byte (0x%02x, expected 0x%02x); closing",
                        peer, end[0], END_BYTE,
                    )
                    break
                response = handle_frame(backend, frame)
                self.request.sendall(
                    bytes([START_BYTE]) + _LENGTH_PREFIX.pack(len(response)) + response + bytes([END_BYTE])
                )
                if server.traffic_log is not None:
                    server.traffic_log.record("TCP", f"{peer[0]}:{peer[1]}", frame, response)
        except ConnectionError:
            pass
        except OSError as exc:
            logger.info("TCP client %s connection error: %s", peer, exc)
        finally:
            server._change_connection_count(-1)
            logger.info("TCP client disconnected: %s", peer)


class TcpGatewayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, backend: CifXBackend, traffic_log: Optional[TrafficLog] = None):
        self.backend = backend
        self.traffic_log = traffic_log
        self._connection_count = 0
        self._connection_lock = threading.Lock()
        super().__init__((host, port), _Handler)

    def _change_connection_count(self, delta: int) -> None:
        with self._connection_lock:
            self._connection_count += delta

    @property
    def connection_count(self) -> int:
        with self._connection_lock:
            return self._connection_count

    def serve_forever_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="cfix-tcp-gateway", daemon=True)
        thread.start()
        return thread
