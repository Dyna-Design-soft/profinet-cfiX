"""Error and state constants from Hilscher's public cifX Device Driver API
(cifXErrors.h / cifXUser.h). Only the subset needed by this gateway is kept.
"""

from __future__ import annotations

CIFX_NO_ERROR = 0x00000000

# Common cifX API error codes (see cifXErrors.h)
CIFX_INVALID_HANDLE = 0x800A0001
CIFX_INVALID_PARAMETER = 0x800A0002
CIFX_INVALID_COMMAND = 0x800A0003
CIFX_FUNCTION_FAILED = 0x800A0004
CIFX_INVALID_BOARD = 0x800A0005
CIFX_INVALID_CHANNEL = 0x800A0006
CIFX_DRV_NOT_INITIALIZED = 0x800A0009
CIFX_DRV_CMD_ACTIVE = 0x800A000A
CIFX_DEV_NOT_READY = 0x800A0011
CIFX_INVALID_ACCESS_SIZE = 0x800A0012
CIFX_DEV_GET_TIMEOUT = 0x800A0035
CIFX_NO_MORE_ENTRIES = 0x800A0043

# Channel host state commands (xChannelHostState)
CIFX_HOST_STATE_READY = 1
CIFX_HOST_STATE_NOT_READY = 0

CIFX_HOST_STATE_CMD_SET = 0
CIFX_HOST_STATE_CMD_READ = 1

# Channel bus state commands (xChannelBusState)
CIFX_BUS_STATE_ON = 1
CIFX_BUS_STATE_OFF = 0

CIFX_BUS_STATE_CMD_SET = 0
CIFX_BUS_STATE_CMD_READ = 1

# Watchdog commands (xChannelWatchdog)
CIFX_WATCHDOG_CMD_STOP = 0
CIFX_WATCHDOG_CMD_START = 1
CIFX_WATCHDOG_CMD_TRIGGER = 2
CIFX_WATCHDOG_CMD_STATUS = 3

# IO read/write "area" numbers (per channel process data image)
CIFX_IO_AREA_DEFAULT = 0


class CifXError(Exception):
    """Raised when a cifX driver call returns a non-zero (error) status."""

    def __init__(self, function: str, code: int):
        self.function = function
        self.code = code
        super().__init__(f"{function} failed with cifX error 0x{code & 0xFFFFFFFF:08X}")
