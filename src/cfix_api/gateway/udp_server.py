"""UDP gateway server: one datagram in, one datagram out.

Each UDP datagram is a complete request frame (see docs/PROTOCOL.md); no
length prefix is used since the datagram boundary already delimits the
frame. The response is sent back to the same source address/port.
"""

from __future__ import annotations

import logging
import socketserver
import threading

from ..cifx.backend import CifXBackend
from .dispatch import handle_frame

logger = logging.getLogger("cfix_api.gateway.udp")


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        backend: CifXBackend = self.server.backend  # type: ignore[attr-defined]
        data, sock = self.request
        try:
            response = handle_frame(backend, data)
        except Exception:
            logger.exception("unhandled error processing UDP frame from %s", self.client_address)
            return
        sock.sendto(response, self.client_address)


class UdpGatewayServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, backend: CifXBackend):
        self.backend = backend
        super().__init__((host, port), _Handler)

    def serve_forever_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="cfix-udp-gateway", daemon=True)
        thread.start()
        return thread
