"""Wires a CifXBackend to the configured TCP/UDP servers and runs them."""

from __future__ import annotations

import logging
import signal
import time

from ..cifx.backend import CifXBackend, HilscherCifXBackend, MockCifXBackend
from .config import GatewayConfig
from .stream_server import StreamGatewayServer
from .tcp_server import TcpGatewayServer
from .traffic_log import TrafficLog
from .udp_server import UdpGatewayServer

logger = logging.getLogger("cfix_api.gateway")


def build_backend(config: GatewayConfig) -> CifXBackend:
    if config.cifx.mock:
        logger.info("using MockCifXBackend (config.cifx.mock = true, no hardware required)")
        return MockCifXBackend()
    return HilscherCifXBackend(
        board_name=config.cifx.board_name,
        channel=config.cifx.channel,
        io_timeout_ms=config.cifx.io_timeout_ms,
        dll_path=config.cifx.dll_path,
    )


class GatewayRunner:
    """Owns the backend lifecycle and the TCP/UDP server threads."""

    def __init__(self, config: GatewayConfig):
        self.config = config
        self.backend = build_backend(config)
        self.traffic_log = TrafficLog()
        self._tcp_server: TcpGatewayServer | StreamGatewayServer | None = None
        self._udp_server: UdpGatewayServer | None = None

    def start(self) -> None:
        self.backend.open()
        logger.info(
            "cifX backend open (board=%s channel=%s)",
            getattr(self.backend, "board_name", "<mock>"),
            getattr(self.backend, "channel", "-"),
        )

        if self.config.tcp.enabled and self.config.stream.enabled:
            self._tcp_server = StreamGatewayServer(
                self.config.tcp.host, self.config.tcp.port, self.backend, self.config.stream
            )
            self._tcp_server.serve_forever_in_thread()
            logger.info(
                "TCP gateway listening on %s:%d (streaming mode: write %d bytes @ area=%d off=%d, "
                "poll %d bytes @ area=%d off=%d every %dms)",
                self.config.tcp.host, self.config.tcp.port,
                self.config.stream.write_length, self.config.stream.area, self.config.stream.write_offset,
                self.config.stream.read_length, self.config.stream.area, self.config.stream.read_offset,
                self.config.stream.poll_interval_ms,
            )
        elif self.config.tcp.enabled:
            self._tcp_server = TcpGatewayServer(
                self.config.tcp.host, self.config.tcp.port, self.backend, self.traffic_log
            )
            self._tcp_server.serve_forever_in_thread()
            logger.info("TCP gateway listening on %s:%d", self.config.tcp.host, self.config.tcp.port)

        if self.config.udp.enabled:
            self._udp_server = UdpGatewayServer(
                self.config.udp.host, self.config.udp.port, self.backend, self.traffic_log
            )
            self._udp_server.serve_forever_in_thread()
            logger.info("UDP gateway listening on %s:%d", self.config.udp.host, self.config.udp.port)

        if not self._tcp_server and not self._udp_server:
            raise RuntimeError("neither TCP nor UDP is enabled in the gateway config")

    @property
    def tcp_client_count(self) -> int | None:
        """Number of currently connected TCP clients, or None if TCP is disabled."""
        return self._tcp_server.connection_count if self._tcp_server else None

    def stop(self) -> None:
        if self._tcp_server:
            self._tcp_server.shutdown()
            self._tcp_server.server_close()
        if self._udp_server:
            self._udp_server.shutdown()
            self._udp_server.server_close()
        self.backend.close()
        logger.info("gateway stopped")

    def run_forever(self) -> None:
        self.start()
        stop_requested = False

        def _handle_signal(signum, frame):
            nonlocal stop_requested
            stop_requested = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handle_signal)
            except (ValueError, OSError):
                pass  # not available on this platform/thread

        try:
            while not stop_requested:
                time.sleep(0.2)
        finally:
            self.stop()
