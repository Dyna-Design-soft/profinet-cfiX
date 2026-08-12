import pytest

from cfix_api.cifx.backend import MockCifXBackend
from cfix_api.cifx.errors import CifXError


def test_open_close_and_status():
    backend = MockCifXBackend()
    with backend:
        bus_state, host_state = backend.get_status()
        assert bus_state == 1  # CIFX_BUS_STATE_ON
        assert host_state == 0  # CIFX_HOST_STATE_NOT_READY


def test_io_write_then_read():
    backend = MockCifXBackend()
    with backend:
        backend.io_write(0, 10, b"\xde\xad\xbe\xef")
        assert backend.io_read(0, 10, 4) == b"\xde\xad\xbe\xef"


def test_io_read_out_of_bounds_raises():
    backend = MockCifXBackend(area_size=16)
    with backend:
        with pytest.raises(CifXError):
            backend.io_read(0, 10, 100)


def test_operations_before_open_raise():
    backend = MockCifXBackend()
    with pytest.raises(CifXError):
        backend.io_read(0, 0, 4)


def test_set_host_state():
    backend = MockCifXBackend()
    with backend:
        backend.set_host_state(True)
        _, host_state = backend.get_status()
        assert host_state == 1


def test_reset_clears_areas():
    backend = MockCifXBackend()
    with backend:
        backend.io_write(0, 0, b"\x01\x02")
        backend.reset()
        assert backend.io_read(0, 0, 2) == b"\x00\x00"
