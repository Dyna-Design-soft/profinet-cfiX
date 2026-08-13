"""Raw duplex TCP streaming gateway: no command byte, no frame markers.

Two independent loops run per connection instead of a lock-step
request/response exchange:

- Reader: blocks for exactly `write_length` bytes from the client, then
  writes them straight to the cifX output image at (area, write_offset).
  Repeats for as long as the client keeps sending.
- Poller: every `poll_interval_ms`, reads `read_length` bytes from the
  cifX input image at (area, read_offset) and sends them straight back to
  the client, unprompted.

See docs/PROTOCOL.md "Streaming mode" and docs/LABVIEW_INTEGRATION.md.
"""

from __future__ import annotations

import logging
import socket
import socketserver
import threading

from ..cifx.backend import CifXBackend
from .config import StreamConfig

logger = logging.getLogger("cfix_api.gateway.stream")


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
        self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def handle(self) -> None:
        server: StreamGatewayServer = self.server  # type: ignore[assignment]
        backend: CifXBackend = server.backend
        cfg = server.stream_config
        peer = self.client_address
        logger.info("stream client connected: %s", peer)
        server._change_connection_count(1)

        stop = threading.Event()

        def poll_loop() -> None:
            interval = cfg.poll_interval_ms / 1000.0
            while not stop.is_set():
                try:
                    data = backend.io_read(cfg.area, cfg.read_offset, cfg.read_length)
                    self.request.sendall(data)
                except (OSError, ConnectionError):
                    stop.set()
                    return
                except Exception:
                    logger.exception("stream poll read failed for %s", peer)
                stop.wait(interval)

        poller = threading.Thread(target=poll_loop, name=f"cfix-stream-poll-{peer}", daemon=True)
        poller.start()

        try:
            while not stop.is_set():
                try:
                    data = _recv_exact(self.request, cfg.write_length)
                except ConnectionError:
                    break
                try:
                    backend.io_write(cfg.area, cfg.write_offset, data)
                except Exception:
                    logger.exception("stream write failed for %s", peer)
        except OSError as exc:
            logger.info("stream client %s connection error: %s", peer, exc)
        finally:
            stop.set()
            poller.join(timeout=1.0)
            server._change_connection_count(-1)
            logger.info("stream client disconnected: %s", peer)


class StreamGatewayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, backend: CifXBackend, stream_config: StreamConfig):
        self.backend = backend
        self.stream_config = stream_config
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
        thread = threading.Thread(target=self.serve_forever, name="cfix-stream-gateway", daemon=True)
        thread.start()
        return thread
