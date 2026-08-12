import struct

import pytest

from cfix_api.gateway.protocol import (
    Command,
    ProtocolError,
    Request,
    Status,
    decode_request,
    decode_response,
    encode_request,
)


def test_encode_decode_read_input_roundtrip():
    req = Request(command=Command.READ_INPUT, area=0, offset=4, length=16)
    frame = encode_request(req)
    decoded = decode_request(frame)
    assert decoded.command == Command.READ_INPUT
    assert decoded.area == 0
    assert decoded.offset == 4
    assert decoded.length == 16
    assert decoded.data == b""


def test_encode_decode_write_output_roundtrip():
    payload = bytes(range(8))
    req = Request(command=Command.WRITE_OUTPUT, area=0, offset=2, length=len(payload), data=payload)
    frame = encode_request(req)
    decoded = decode_request(frame)
    assert decoded.command == Command.WRITE_OUTPUT
    assert decoded.data == payload


def test_decode_request_too_short_raises():
    with pytest.raises(ProtocolError) as exc_info:
        decode_request(b"\x01\x00")
    assert exc_info.value.status == Status.MALFORMED_FRAME


def test_decode_write_output_length_mismatch_raises():
    header = struct.pack(">BBHH", Command.WRITE_OUTPUT, 0, 0, 4)
    with pytest.raises(ProtocolError):
        decode_request(header + b"\x01\x02")  # only 2 bytes, declared 4


def test_decode_response_roundtrip():
    from cfix_api.gateway.protocol import Response

    resp = Response(status=Status.OK, command=Command.READ_INPUT, data=b"\x01\x02\x03")
    frame = resp.encode()
    decoded = decode_response(frame)
    assert decoded.status == Status.OK
    assert decoded.command == Command.READ_INPUT
    assert decoded.data == b"\x01\x02\x03"
