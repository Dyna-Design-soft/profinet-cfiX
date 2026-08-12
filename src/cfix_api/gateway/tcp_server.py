"""TCP gateway server: length-prefixed framing over a persistent connection.

Each request/response frame (see docs/PROTOCOL.md) is prefixed on the wire
with a 4-byte big-endian length. One thread per client connection; requests
on a connection are handled and answered strictly in order.
"""

from __future__ import annotations

import logging
import socket
import socketserver
import struct
import threading

from ..cifx.backend import CifXBackend
from .dispatch import handle_frame

logger = logging.getLogger("cfix_api.gateway.tcp")

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
                    length_bytes = _recv_exact(self.request, _LENGTH_PREFIX.size)
                except ConnectionError:
                    break
                (length,) = _LENGTH_PREFIX.unpack(length_bytes)
                if length > MAX_FRAME_SIZE:
                    logger.warning("TCP client %s sent oversized frame (%d bytes); closing", peer, length)
                    break
                frame = _recv_exact(self.request, length)
                response = handle_frame(backend, frame)
                self.request.sendall(_LENGTH_PREFIX.pack(len(response)) + response)
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

    def __init__(self, host: str, port: int, backend: CifXBackend):
        self.backend = backend
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
