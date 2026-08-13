"""Error and state constants from Hilscher's cifX Device Driver API.

Values verified against Hilscher's own "PyCifx" reference demo
(hilscher/cifXError.py, hilscher/cifXUser.py, distributed from Hilscher's
Global Support knowledgebase) rather than guessed from the public header
names alone.
"""

from __future__ import annotations

CIFX_NO_ERROR = 0x00000000

# Generic errors (cifXErrors.h, verified against Hilscher's cifXError.py)
CIFX_INVALID_POINTER = 0x800A0001
CIFX_INVALID_BOARD = 0x800A0002
CIFX_INVALID_CHANNEL = 0x800A0003
CIFX_INVALID_HANDLE = 0x800A0004
CIFX_INVALID_PARAMETER = 0x800A0005
CIFX_INVALID_COMMAND = 0x800A0006
CIFX_INVALID_BUFFERSIZE = 0x800A0007
CIFX_INVALID_ACCESS_SIZE = 0x800A0008
CIFX_FUNCTION_FAILED = 0x800A0009
CIFX_NO_MORE_ENTRIES = 0x800A0014

# Generic driver errors
CIFX_DRV_NOT_INITIALIZED = 0x800B0001
CIFX_DRV_CMD_ACTIVE = 0x800B0004
CIFX_DRV_DRIVER_NOT_LOADED = 0x800B0030
CIFX_DRV_NOT_OPENED = 0x800B0034

# Generic device errors
CIFX_DEV_NOT_READY = 0x800C0011
CIFX_DEV_NOT_RUNNING = 0x800C0012
CIFX_DEV_WATCHDOG_FAILED = 0x800C0013
CIFX_DEV_PUT_TIMEOUT = 0x800C0017
CIFX_DEV_GET_TIMEOUT = 0x800C0018
CIFX_DEV_RESET_TIMEOUT = 0x800C0020
CIFX_DEV_EXCHANGE_FAILED = 0x800C0022
CIFX_DEV_EXCHANGE_TIMEOUT = 0x800C0023

# Channel host state (xChannelHostState): the "cmd" argument IS the target
# state to set, or CIFX_HOST_STATE_READ to query the current state via the
# state-pointer out-argument. (Confirmed from Hilscher's PyCifx demo -
# main.py calls xChannelHostState(hChannel, CIFX_HOST_STATE_READY, ...)
# directly, not a separate "set" command plus a state value.)
CIFX_HOST_STATE_NOT_READY = 0
CIFX_HOST_STATE_READY = 1
CIFX_HOST_STATE_READ = 2

# Channel bus state (xChannelBusState): same convention as host state.
CIFX_BUS_STATE_OFF = 0
CIFX_BUS_STATE_ON = 1
CIFX_BUS_STATE_GETSTATE = 2

# Channel configuration lock (xChannelConfigLock): same (cmd, state-out,
# timeout) shape as host/bus state above. Confirmed against a working
# Hilscher CIFX LabVIEW class library (Hilscher CIFX.lvlib:Hilscher CIFX
# Channel.lvclass:Config Lock.vi) calling xChannelConfigLock(hChannel,
# ulCmd, pulState, ulTimeout) with ulCmd = "Unlock Configuration" and
# getting status = OK back - not just inferred from the sibling functions'
# pattern.
CIFX_CONFIG_UNLOCK = 0
CIFX_CONFIG_LOCK = 1
CIFX_CONFIG_GETSTATE = 2

# Watchdog commands (xChannelWatchdog). Not exercised by Hilscher's PyCifx
# demo, so - unlike the constants above - these are not cross-checked
# against Hilscher's own source; they follow the commonly documented
# cifXUser.h numbering (stop/start/trigger) but should be verified against
# the driver installed on the target machine before relying on them.
CIFX_WATCHDOG_CMD_STOP = 0
CIFX_WATCHDOG_CMD_START = 1
CIFX_WATCHDOG_CMD_TRIGGER = 2

# IO read/write "area" numbers (per channel process data image)
CIFX_IO_AREA_DEFAULT = 0


class CifXError(Exception):
    """Raised when a cifX driver call returns a non-zero (error) status."""

    def __init__(self, function: str, code: int):
        self.function = function
        self.code = code
        super().__init__(f"{function} failed with cifX error 0x{code & 0xFFFFFFFF:08X}")
