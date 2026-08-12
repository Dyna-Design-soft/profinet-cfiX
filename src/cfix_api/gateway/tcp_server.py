"""TCP gateway server: length-prefixed framing over a persistent connection.

Each request/response frame (see docs/PROTOCOL.md) is prefixed on the wire
with a 4-byte big-endian length. One thread per client connection; requests
on a connection are handled and answered strictly in order.
"""

from __future__ import annotations

import logging
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
    def handle(self) -> None:
        backend: CifXBackend = self.server.backend  # type: ignore[attr-defined]
        peer = self.client_address
        logger.info("TCP client connected: %s", peer)
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
            logger.info("TCP client disconnected: %s", peer)


class TcpGatewayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, backend: CifXBackend):
        self.backend = backend
        super().__init__((host, port), _Handler)

    def serve_forever_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="cfix-tcp-gateway", daemon=True)
        thread.start()
        return thread
