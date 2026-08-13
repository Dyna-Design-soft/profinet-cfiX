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

        # A PROFINET IO controller card won't actually go active on the bus
        # after every gateway start (most visibly after a PC restart) until
        # this exact sequence runs - matches a known-working reference
        # implementation: unlock the downloaded configuration, signal the
        # host is ready, then explicitly start the bus. Previously nothing
        # did any of this automatically, so the card sat
        # configured-but-dormant until something else (e.g. SyCon
        # connecting) did it as a side effect. None of these three are
        # fatal to gateway startup if they fail - io_read/io_write's own
        # stale-handle recovery and the explicit SET_HOST_STATE protocol
        # command both remain available as fallbacks.
        for step, fn in (
            ("unlock configuration", lambda: self.backend.set_config_lock(False)),
            ("set host state ready", lambda: self.backend.set_host_state(True)),
            ("set bus state on", lambda: self.backend.set_bus_state(True)),
        ):
            try:
                fn()
            except Exception as exc:
                logger.warning("failed to %s on startup: %s", step, exc)

        if self.config.tcp.enabled and self.config.stream.enabled:
            self._tcp_server = StreamGatewayServer(
                self.config.tcp.host, self.config.tcp.port, self.backend, self.config.stream
            )
            self._tcp_server.serve_forever_in_thread()
            if self.config.stream.write_framing == "ascii_length_prefix":
                write_desc = 'write len"N" + N bytes (ascii_length_prefix)'
            else:
                write_desc = f"write {self.config.stream.write_length} bytes (fixed)"
            logger.info(
                'TCP gateway listening on %s:%d (streaming mode: %s @ area=%d off=%d, '
                "poll %d bytes @ area=%d off=%d every %dms)",
                self.config.tcp.host, self.config.tcp.port,
                write_desc, self.config.stream.area, self.config.stream.write_offset,
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

    @property
    def stream_byte_counters(self) -> tuple[int, int] | None:
        """(bytes_written, bytes_read) cumulative since the streaming server
        started, or None if TCP isn't running in streaming mode."""
        if isinstance(self._tcp_server, StreamGatewayServer):
            return self._tcp_server.bytes_written, self._tcp_server.bytes_read
        return None

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
