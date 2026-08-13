"""Tests for HilscherCifXBackend's stale-handle reopen-and-retry logic
(backend.py's _call()) without a real cifX driver - a fake `dll` object
stands in for the ctypes-bound driver library, since only return codes
and call counts matter here, not real hardware I/O.
"""

import threading
import types

import pytest

from cfix_api.cifx import errors as e
from cfix_api.cifx.backend import HilscherCifXBackend
from cfix_api.cifx.structures import HANDLE


class _FakeDll:
    def __init__(self):
        self.driver_open_count = 0
        self.channel_open_count = 0
        self.driver_close_count = 0
        self.channel_close_count = 0
        self.io_read_results = []
        self.reopen_xchannelopen_rc = e.CIFX_NO_ERROR

    def xDriverOpen(self, phDriver):
        self.driver_open_count += 1
        return e.CIFX_NO_ERROR

    def xDriverClose(self, hDriver):
        self.driver_close_count += 1
        return e.CIFX_NO_ERROR

    def xChannelOpen(self, hDriver, board_name, channel, phChannel):
        self.channel_open_count += 1
        return self.reopen_xchannelopen_rc

    def xChannelClose(self, hChannel):
        self.channel_close_count += 1
        return e.CIFX_NO_ERROR

    def xChannelIORead(self, hChannel, area, offset, length, buf, timeout):
        return self.io_read_results.pop(0)


def _make_backend(dll: _FakeDll) -> HilscherCifXBackend:
    backend = HilscherCifXBackend.__new__(HilscherCifXBackend)
    backend.board_name = "cifX0"
    backend.channel = 0
    backend.io_timeout_ms = 50
    backend._lib = types.SimpleNamespace(dll=dll)
    # Simulate an already-open backend (the realistic starting point for a
    # stale-handle scenario - open() already succeeded once, then the
    # handle went stale later) rather than a never-opened one, so
    # _reopen_locked's close step is exercised too.
    backend._hdriver = HANDLE(1)
    backend._hchannel = HANDLE(1)
    backend._lock = threading.Lock()
    backend._last_reopen_attempt = 0.0
    return backend


def test_successful_call_does_not_trigger_reopen():
    dll = _FakeDll()
    dll.io_read_results = [e.CIFX_NO_ERROR]
    backend = _make_backend(dll)

    backend.io_read(0, 0, 4)

    assert dll.channel_open_count == 0
    assert dll.driver_open_count == 0


def test_invalid_handle_triggers_reopen_and_retry_succeeds():
    dll = _FakeDll()
    dll.io_read_results = [e.CIFX_INVALID_HANDLE, e.CIFX_NO_ERROR]
    backend = _make_backend(dll)

    data = backend.io_read(0, 0, 4)  # must not raise - retry after reopen succeeds

    assert data == b"\x00\x00\x00\x00"
    assert dll.channel_open_count == 1
    assert dll.driver_open_count == 1
    assert dll.channel_close_count == 1
    assert dll.driver_close_count == 1


def test_non_recoverable_error_does_not_trigger_reopen():
    dll = _FakeDll()
    dll.io_read_results = [e.CIFX_INVALID_PARAMETER]
    backend = _make_backend(dll)

    with pytest.raises(e.CifXError) as exc_info:
        backend.io_read(0, 0, 4)

    assert exc_info.value.code == e.CIFX_INVALID_PARAMETER
    assert dll.channel_open_count == 0


def test_reopen_cooldown_prevents_repeated_reopen_attempts(monkeypatch):
    dll = _FakeDll()
    dll.io_read_results = [e.CIFX_INVALID_HANDLE, e.CIFX_INVALID_HANDLE]
    backend = _make_backend(dll)

    fake_now = [1000.0]
    monkeypatch.setattr("cfix_api.cifx.backend.time.monotonic", lambda: fake_now[0])

    with pytest.raises(e.CifXError):
        backend.io_read(0, 0, 4)
    assert dll.channel_open_count == 1  # first failure: reopen attempted

    # Still within the cooldown window - no second reopen attempt, so the
    # call fails immediately with the original error and no retry.
    dll.io_read_results = [e.CIFX_INVALID_HANDLE]
    fake_now[0] += 0.5
    with pytest.raises(e.CifXError):
        backend.io_read(0, 0, 4)
    assert dll.channel_open_count == 1

    # Past the cooldown - reopen is attempted again.
    dll.io_read_results = [e.CIFX_INVALID_HANDLE, e.CIFX_NO_ERROR]
    fake_now[0] += 10.0
    backend.io_read(0, 0, 4)
    assert dll.channel_open_count == 2


def test_reopen_failure_still_raises_original_error():
    dll = _FakeDll()
    dll.io_read_results = [e.CIFX_INVALID_HANDLE]
    dll.reopen_xchannelopen_rc = e.CIFX_INVALID_BOARD  # reopen itself fails
    backend = _make_backend(dll)

    with pytest.raises(e.CifXError) as exc_info:
        backend.io_read(0, 0, 4)

    # The error raised to the caller is the original stale-handle error,
    # not the reopen attempt's own failure.
    assert exc_info.value.code == e.CIFX_INVALID_HANDLE
