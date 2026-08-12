"""Backend abstraction over a cifX channel's cyclic process-data image.

CifXBackend is the seam the gateway talks to. HilscherCifXBackend drives a
real Hilscher CIFX PROFINET card through the ctypes bindings; MockCifXBackend
holds the same IO areas in memory so the gateway and protocol can be
developed and tested on any machine, without the card or driver installed.
"""

from __future__ import annotations

import abc
import ctypes as ct
import threading
from typing import Optional

from . import errors as e
from .bindings import CifXLibrary
from .structures import HANDLE


class CifXBackend(abc.ABC):
    """Minimal operations the gateway needs from a cifX channel."""

    @abc.abstractmethod
    def open(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def io_read(self, area: int, offset: int, length: int) -> bytes: ...

    @abc.abstractmethod
    def io_write(self, area: int, offset: int, data: bytes) -> None: ...

    @abc.abstractmethod
    def get_status(self) -> tuple[int, int]:
        """Returns (bus_state, host_state)."""

    @abc.abstractmethod
    def set_host_state(self, ready: bool) -> None: ...

    @abc.abstractmethod
    def watchdog_trigger(self) -> None: ...

    @abc.abstractmethod
    def reset(self) -> None: ...

    def __enter__(self) -> "CifXBackend":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class HilscherCifXBackend(CifXBackend):
    """Talks to a real Hilscher CIFX card through the cifX driver DLL."""

    def __init__(
        self,
        board_name: str,
        channel: int = 0,
        io_timeout_ms: int = 100,
        dll_path: Optional[str] = None,
    ):
        self.board_name = board_name
        self.channel = channel
        self.io_timeout_ms = io_timeout_ms
        self._lib = CifXLibrary(dll_path)
        self._hdriver: HANDLE = HANDLE()
        self._hchannel: HANDLE = HANDLE()
        self._lock = threading.Lock()

    def open(self) -> None:
        dll = self._lib.dll
        rc = dll.xDriverOpen(ct.byref(self._hdriver))
        if rc != e.CIFX_NO_ERROR:
            raise e.CifXError("xDriverOpen", rc)

        rc = dll.xChannelOpen(
            self._hdriver,
            self.board_name.encode("ascii"),
            self.channel,
            ct.byref(self._hchannel),
        )
        if rc != e.CIFX_NO_ERROR:
            dll.xDriverClose(self._hdriver)
            raise e.CifXError("xChannelOpen", rc)

    def close(self) -> None:
        dll = self._lib.dll
        if self._hchannel:
            dll.xChannelClose(self._hchannel)
            self._hchannel = HANDLE()
        if self._hdriver:
            dll.xDriverClose(self._hdriver)
            self._hdriver = HANDLE()

    def io_read(self, area: int, offset: int, length: int) -> bytes:
        buf = ct.create_string_buffer(length)
        with self._lock:
            rc = self._lib.dll.xChannelIORead(
                self._hchannel, area, offset, length, buf, self.io_timeout_ms
            )
        if rc != e.CIFX_NO_ERROR:
            raise e.CifXError("xChannelIORead", rc)
        return buf.raw[:length]

    def io_write(self, area: int, offset: int, data: bytes) -> None:
        buf = ct.create_string_buffer(data, len(data))
        with self._lock:
            rc = self._lib.dll.xChannelIOWrite(
                self._hchannel, area, offset, len(data), buf, self.io_timeout_ms
            )
        if rc != e.CIFX_NO_ERROR:
            raise e.CifXError("xChannelIOWrite", rc)

    def get_status(self) -> tuple[int, int]:
        bus_state = ct.c_uint32()
        host_state = ct.c_uint32()
        with self._lock:
            rc = self._lib.dll.xChannelBusState(
                self._hchannel,
                e.CIFX_BUS_STATE_GETSTATE,
                ct.byref(bus_state),
                self.io_timeout_ms,
            )
            if rc != e.CIFX_NO_ERROR:
                raise e.CifXError("xChannelBusState", rc)

            rc = self._lib.dll.xChannelHostState(
                self._hchannel,
                e.CIFX_HOST_STATE_READ,
                ct.byref(host_state),
                self.io_timeout_ms,
            )
            if rc != e.CIFX_NO_ERROR:
                raise e.CifXError("xChannelHostState", rc)
        return bus_state.value, host_state.value

    def set_host_state(self, ready: bool) -> None:
        # The cmd argument itself is the target state to set (confirmed
        # against Hilscher's PyCifx demo) - not a separate "set" command
        # plus a state value passed by pointer.
        cmd = e.CIFX_HOST_STATE_READY if ready else e.CIFX_HOST_STATE_NOT_READY
        state = ct.c_uint32(0)
        with self._lock:
            rc = self._lib.dll.xChannelHostState(
                self._hchannel,
                cmd,
                ct.byref(state),
                self.io_timeout_ms,
            )
        if rc != e.CIFX_NO_ERROR:
            raise e.CifXError("xChannelHostState", rc)

    def watchdog_trigger(self) -> None:
        dummy = ct.c_uint32(0)
        with self._lock:
            rc = self._lib.dll.xChannelWatchdog(
                self._hchannel, e.CIFX_WATCHDOG_CMD_TRIGGER, ct.byref(dummy)
            )
        if rc != e.CIFX_NO_ERROR:
            raise e.CifXError("xChannelWatchdog", rc)

    def reset(self) -> None:
        with self._lock:
            rc = self._lib.dll.xChannelReset(self._hchannel, 0, self.io_timeout_ms)
        if rc != e.CIFX_NO_ERROR:
            raise e.CifXError("xChannelReset", rc)


class MockCifXBackend(CifXBackend):
    """In-memory stand-in for a cifX channel, for tests and dev without hardware."""

    def __init__(self, area_size: int = 512):
        self._lock = threading.Lock()
        self._areas: dict[int, bytearray] = {}
        self._area_size = area_size
        self._bus_state = e.CIFX_BUS_STATE_OFF
        self._host_state = e.CIFX_HOST_STATE_NOT_READY
        self._is_open = False

    def _area(self, area: int) -> bytearray:
        if area not in self._areas:
            self._areas[area] = bytearray(self._area_size)
        return self._areas[area]

    def open(self) -> None:
        self._is_open = True
        self._bus_state = e.CIFX_BUS_STATE_ON

    def close(self) -> None:
        self._is_open = False
        self._bus_state = e.CIFX_BUS_STATE_OFF

    def _check_open(self) -> None:
        if not self._is_open:
            raise e.CifXError("MockCifXBackend", e.CIFX_DRV_NOT_INITIALIZED)

    def io_read(self, area: int, offset: int, length: int) -> bytes:
        self._check_open()
        with self._lock:
            buf = self._area(area)
            if offset + length > len(buf):
                raise e.CifXError("io_read", e.CIFX_INVALID_PARAMETER)
            return bytes(buf[offset : offset + length])

    def io_write(self, area: int, offset: int, data: bytes) -> None:
        self._check_open()
        with self._lock:
            buf = self._area(area)
            if offset + len(data) > len(buf):
                raise e.CifXError("io_write", e.CIFX_INVALID_PARAMETER)
            buf[offset : offset + len(data)] = data

    def get_status(self) -> tuple[int, int]:
        self._check_open()
        return self._bus_state, self._host_state

    def set_host_state(self, ready: bool) -> None:
        self._check_open()
        self._host_state = e.CIFX_HOST_STATE_READY if ready else e.CIFX_HOST_STATE_NOT_READY

    def watchdog_trigger(self) -> None:
        self._check_open()

    def reset(self) -> None:
        self._check_open()
        for buf in self._areas.values():
            buf[:] = bytes(len(buf))
