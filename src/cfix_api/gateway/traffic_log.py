"""Bounded, thread-safe log of recent gateway request/response frames.

Purely for the desktop app's Diagnostics window - it observes what the
gateway already did, it never influences dispatch. A decode failure here
only degrades the display text; it's always caught, never raised.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from .protocol import Command, Status, decode_request, decode_response


def _describe_request(frame: bytes) -> str:
    try:
        req = decode_request(frame)
    except Exception:
        return f"<{len(frame)} bytes, unparsed>"
    try:
        name = Command(req.command).name
    except ValueError:
        name = f"0x{req.command:02X}"
    return f"{name} area={req.area} offset={req.offset} length={req.length}"


def _describe_response(frame: bytes) -> str:
    try:
        resp = decode_response(frame)
    except Exception:
        return f"<{len(frame)} bytes, unparsed>"
    try:
        status_name = Status(resp.status).name
    except ValueError:
        status_name = f"0x{resp.status:02X}"
    return f"status={status_name} data={resp.data.hex()}"


@dataclass
class TrafficEvent:
    timestamp: float
    transport: str  # "TCP" or "UDP"
    peer: str
    request_summary: str
    response_summary: str
    request_hex: str
    response_hex: str


class TrafficLog:
    """Ring buffer of the most recent request/response pairs, across both transports."""

    def __init__(self, max_events: int = 500):
        self._events: deque[TrafficEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def record(self, transport: str, peer: str, request_frame: bytes, response_frame: bytes) -> None:
        event = TrafficEvent(
            timestamp=time.time(),
            transport=transport,
            peer=peer,
            request_summary=_describe_request(request_frame),
            response_summary=_describe_response(response_frame),
            request_hex=request_frame.hex(" ").upper(),
            response_hex=response_frame.hex(" ").upper(),
        )
        with self._lock:
            self._events.append(event)

    def record_raw(self, transport: str, peer: str, summary: str, data: bytes) -> None:
        """Like record(), but for streaming mode: no Command/Status protocol
        to decode, so the caller supplies a plain-text summary directly
        instead of running it through the framed-protocol decoder (which
        would misparse a raw frame as garbage command/area/offset fields)."""
        event = TrafficEvent(
            timestamp=time.time(),
            transport=transport,
            peer=peer,
            request_summary=summary,
            response_summary="",
            request_hex=data.hex(" ").upper(),
            response_hex="",
        )
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[TrafficEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
