"""Raw duplex TCP streaming gateway: no command byte, no fixed frame markers.

Two independent loops run per connection instead of a lock-step
request/response exchange:

- Reader: gets the next write frame from the client (see `write_framing`
  below), then writes it straight to the cifX output image at
  (area, write_offset). Repeats for as long as the client keeps sending.
- Poller: every `poll_interval_ms`, reads `read_length` bytes from the
  cifX input image at (area, read_offset) and sends them straight back to
  the client, unprompted.

Each successful write is recorded to the shared TrafficLog (visible in the
desktop app's Diagnostics window) as a raw entry - poll reads are not, since
at a typical 10ms interval they'd flood the log/table with little value; the
Diagnostics window's "Card Process Data" panel already shows live input/
output image content independent of this log.

`write_framing` controls how the reader finds a write frame's boundary:

- "fixed": read exactly `write_length` raw bytes, every time.
- "ascii_length_prefix": read the literal ASCII text `len"` (4 bytes),
  then ASCII decimal digit characters up to the next `"`, parse those
  digits as the frame length N, then read exactly N raw bytes - those N
  bytes (not the `len"...""` text) are the frame written to the DLL.
  Example on the wire: `len"103"` followed by 103 raw bytes.

See docs/PROTOCOL.md "Streaming mode" and docs/LABVIEW_INTEGRATION.md.
"""

from __future__ import annotations

import logging
import socket
import socketserver
import threading
from typing import Optional

from ..cifx.backend import CifXBackend
from .config import StreamConfig
from .traffic_log import TrafficLog

logger = logging.getLogger("cfix_api.gateway.stream")

_LEN_PREFIX_LITERAL = b'len"'
_MAX_ASCII_FRAME_SIZE = 64 * 1024
_MAX_LENGTH_DIGITS = 6  # up to 999999 - comfortably covers _MAX_ASCII_FRAME_SIZE


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


def _recv_byte(sock) -> bytes:
    b = sock.recv(1)
    if not b:
        raise ConnectionError("connection closed")
    return b


class FramingError(Exception):
    """The client sent something that doesn't match the configured write_framing."""


def _recv_ascii_length_prefixed_frame(sock) -> bytes:
    prefix = _recv_exact(sock, len(_LEN_PREFIX_LITERAL))
    if prefix != _LEN_PREFIX_LITERAL:
        raise FramingError(f"expected literal {_LEN_PREFIX_LITERAL!r}, got {prefix!r}")

    digits = b""
    while True:
        ch = _recv_byte(sock)
        if ch == b'"':
            break
        if not ch.isdigit():
            raise FramingError(f"non-digit byte {ch!r} in length field")
        digits += ch
        if len(digits) > _MAX_LENGTH_DIGITS:
            raise FramingError(f"length field too long: {digits!r}...")

    if not digits:
        raise FramingError('empty length field between len"" quotes')

    length = int(digits)
    if length > _MAX_ASCII_FRAME_SIZE:
        raise FramingError(f"declared length {length} exceeds max {_MAX_ASCII_FRAME_SIZE}")

    return _recv_exact(sock, length)


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
                    if cfg.write_framing == "ascii_length_prefix":
                        data = _recv_ascii_length_prefixed_frame(self.request)
                    else:
                        data = _recv_exact(self.request, cfg.write_length)
                except ConnectionError:
                    break
                except FramingError as exc:
                    logger.warning("stream client %s bad frame (%s); closing", peer, exc)
                    break
                try:
                    backend.io_write(cfg.area, cfg.write_offset, data)
                except Exception:
                    logger.exception("stream write failed for %s", peer)
                else:
                    if server.traffic_log is not None:
                        server.traffic_log.record_raw(
                            "TCP-STREAM", f"{peer[0]}:{peer[1]}", f"wrote {len(data)} bytes", data
                        )
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

    def __init__(
        self,
        host: str,
        port: int,
        backend: CifXBackend,
        stream_config: StreamConfig,
        traffic_log: Optional[TrafficLog] = None,
    ):
        self.backend = backend
        self.stream_config = stream_config
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
        thread = threading.Thread(target=self.serve_forever, name="cfix-stream-gateway", daemon=True)
        thread.start()
        return thread
