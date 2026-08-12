"""Encode/decode for the CFIX gateway wire protocol.

See docs/PROTOCOL.md for the full frame layout. This module only handles a
single frame's bytes; transport-specific framing (TCP length prefix vs. one
frame per UDP datagram) lives in tcp_server.py / udp_server.py.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class Command(IntEnum):
    READ_INPUT = 0x01
    WRITE_OUTPUT = 0x02
    READ_OUTPUT = 0x03
    GET_STATUS = 0x10
    SET_HOST_STATE = 0x11
    WATCHDOG_TRIGGER = 0x12
    RESET = 0x13


class Status(IntEnum):
    OK = 0x00
    MALFORMED_FRAME = 0x01
    UNKNOWN_COMMAND = 0x02
    BACKEND_ERROR = 0x03


_REQUEST_HEADER = struct.Struct(">BBHH")  # command, area, offset, length
_RESPONSE_HEADER = struct.Struct(">BBH")  # status, command, data length

MAX_DATA_LENGTH = 0xFFFF


class ProtocolError(Exception):
    """A request frame could not be parsed."""

    def __init__(self, status: Status, message: str):
        self.status = status
        super().__init__(message)


@dataclass
class Request:
    command: int
    area: int
    offset: int
    length: int
    data: bytes = b""


@dataclass
class Response:
    status: int
    command: int
    data: bytes = b""

    def encode(self) -> bytes:
        return _RESPONSE_HEADER.pack(self.status, self.command, len(self.data)) + self.data


def decode_request(frame: bytes) -> Request:
    if len(frame) < _REQUEST_HEADER.size:
        raise ProtocolError(Status.MALFORMED_FRAME, "frame shorter than header")

    command, area, offset, length = _REQUEST_HEADER.unpack_from(frame)
    payload = frame[_REQUEST_HEADER.size :]

    if command == Command.WRITE_OUTPUT:
        if len(payload) != length:
            raise ProtocolError(
                Status.MALFORMED_FRAME,
                f"declared length {length} does not match payload {len(payload)}",
            )
        data = payload
    elif command == Command.SET_HOST_STATE:
        if len(payload) != 1:
            raise ProtocolError(Status.MALFORMED_FRAME, "SET_HOST_STATE needs 1 data byte")
        data = payload
    else:
        data = b""

    return Request(command=command, area=area, offset=offset, length=length, data=data)


def encode_request(req: Request) -> bytes:
    if req.command == Command.WRITE_OUTPUT and len(req.data) > MAX_DATA_LENGTH:
        raise ProtocolError(Status.MALFORMED_FRAME, "data too long")
    header = _REQUEST_HEADER.pack(req.command, req.area, req.offset, req.length)
    if req.command in (Command.WRITE_OUTPUT, Command.SET_HOST_STATE):
        return header + req.data
    return header


def decode_response(frame: bytes) -> Response:
    if len(frame) < _RESPONSE_HEADER.size:
        raise ProtocolError(Status.MALFORMED_FRAME, "frame shorter than header")
    status, command, data_len = _RESPONSE_HEADER.unpack_from(frame)
    data = frame[_RESPONSE_HEADER.size : _RESPONSE_HEADER.size + data_len]
    if len(data) != data_len:
        raise ProtocolError(Status.MALFORMED_FRAME, "truncated response data")
    return Response(status=status, command=command, data=data)
