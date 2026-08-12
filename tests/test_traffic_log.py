from cfix_api.gateway.protocol import Command, Request, Response, Status, encode_request
from cfix_api.gateway.traffic_log import TrafficLog


def test_record_and_snapshot():
    log = TrafficLog()
    req = encode_request(Request(command=Command.WRITE_OUTPUT, area=0, offset=10, length=4, data=b"\xde\xad\xbe\xef"))
    resp = Response(status=Status.OK, command=Command.WRITE_OUTPUT).encode()

    log.record("TCP", "127.0.0.1:12345", req, resp)

    events = log.snapshot()
    assert len(events) == 1
    event = events[0]
    assert event.transport == "TCP"
    assert event.peer == "127.0.0.1:12345"
    assert "WRITE_OUTPUT" in event.request_summary
    assert "offset=10" in event.request_summary
    assert "length=4" in event.request_summary
    assert "status=OK" in event.response_summary
    assert event.request_hex == "02 00 00 0A 00 04 DE AD BE EF"


def test_malformed_frame_does_not_raise():
    log = TrafficLog()
    log.record("UDP", "10.0.0.1:9999", b"\x01", b"")
    events = log.snapshot()
    assert len(events) == 1
    assert "unparsed" in events[0].request_summary


def test_bounded_ring_buffer():
    log = TrafficLog(max_events=3)
    for i in range(5):
        log.record("TCP", "peer", bytes([i]), b"")
    events = log.snapshot()
    assert len(events) == 3
    # keeps the most recent ones
    assert events[-1].request_hex == "04"


def test_clear():
    log = TrafficLog()
    log.record("TCP", "peer", b"\x00", b"")
    assert len(log.snapshot()) == 1
    log.clear()
    assert log.snapshot() == []
