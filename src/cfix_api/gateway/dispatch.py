"""Executes decoded gateway requests against a CifXBackend."""

from __future__ import annotations

import logging

from ..cifx.backend import CifXBackend
from ..cifx.errors import CifXError
from .protocol import Command, ProtocolError, Request, Response, Status, decode_request

logger = logging.getLogger("cfix_api.gateway")


def handle_frame(backend: CifXBackend, frame: bytes) -> bytes:
    """Decodes one request frame, runs it against backend, returns a response frame."""
    try:
        request = decode_request(frame)
    except ProtocolError as exc:
        return Response(status=exc.status, command=frame[0] if frame else 0xFF).encode()

    try:
        return _execute(backend, request).encode()
    except CifXError as exc:
        logger.warning("backend error handling command 0x%02X: %s", request.command, exc)
        return Response(status=Status.BACKEND_ERROR, command=request.command).encode()


def _execute(backend: CifXBackend, request: Request) -> Response:
    if request.command == Command.READ_INPUT:
        data = backend.io_read(request.area, request.offset, request.length)
        return Response(status=Status.OK, command=request.command, data=data)

    if request.command == Command.WRITE_OUTPUT:
        backend.io_write(request.area, request.offset, request.data)
        return Response(status=Status.OK, command=request.command)

    if request.command == Command.READ_OUTPUT:
        data = backend.io_read(request.area, request.offset, request.length)
        return Response(status=Status.OK, command=request.command, data=data)

    if request.command == Command.GET_STATUS:
        bus_state, host_state = backend.get_status()
        return Response(
            status=Status.OK,
            command=request.command,
            data=bytes((bus_state & 0xFF, host_state & 0xFF)),
        )

    if request.command == Command.SET_HOST_STATE:
        backend.set_host_state(bool(request.data[0]))
        return Response(status=Status.OK, command=request.command)

    if request.command == Command.WATCHDOG_TRIGGER:
        backend.watchdog_trigger()
        return Response(status=Status.OK, command=request.command)

    if request.command == Command.RESET:
        backend.reset()
        return Response(status=Status.OK, command=request.command)

    return Response(status=Status.UNKNOWN_COMMAND, command=request.command)
