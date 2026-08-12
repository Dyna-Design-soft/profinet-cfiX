"""ctypes bindings to Hilscher's cifX Device Driver API.

This wraps the public, documented cifX API (cifXUser.h): xDriverOpen,
xDriverClose, xChannelOpen, xChannelClose, xChannelIORead, xChannelIOWrite,
xChannelHostState, xChannelBusState, xChannelWatchdog and xChannelReset.

On a Windows target with the Hilscher cifX driver installed, the driver
DLL is loaded by name. Confirmed names: "cifx32dll.dll" is the 32-bit
driver DLL Hilscher's own PyCifx reference demo loads (via
`ctypes.util.find_library("cifx32dll")`); "cifX32dll64.dll" is the
64-bit driver DLL's real (if confusingly named) filename, per a
Hilscher support interaction on the NI forums - a 64-bit Python
process (required for PySide6, which has no 32-bit Windows wheels)
needs this one, not the 32-bit name despite the similar look. "cifXAPI.dll"
is a distinct, higher-level API DLL name also referenced in that same
support thread for some driver versions. "cifX32DRV.dll"/"cifX64DRV.dll"
are unverified names seen in older driver documentation, kept as
last-resort fallbacks. None of this has been exercised against a real
driver install in this repo's test environment (Linux-only) - if
auto-detection doesn't find the right one, set CIFX_DLL_PATH (or pass
dll_path explicitly) to the exact file from your driver's installation
directory instead of relying on the search order.
"""

from __future__ import annotations

import ctypes as ct
import os
from typing import Optional

from .structures import BOARD_INFORMATION, CHANNEL_INFORMATION, HANDLE

DEFAULT_DLL_CANDIDATES = (
    "cifX32dll64.dll",
    "cifx32dll.dll",
    "cifXAPI.dll",
    "cifX32DRV.dll",
    "cifX64DRV.dll",
)


class CifXBindingError(RuntimeError):
    """Raised when the cifX driver DLL cannot be located or loaded."""


def _load_library(dll_path: Optional[str] = None) -> ct.WinDLL:
    if not hasattr(ct, "WinDLL"):
        raise CifXBindingError(
            "The Hilscher cifX driver is only available through its Windows "
            "DLL; ctypes.WinDLL is not present on this platform."
        )

    candidates = [dll_path] if dll_path else []
    env_path = os.environ.get("CIFX_DLL_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.extend(DEFAULT_DLL_CANDIDATES)

    errors = []
    for name in candidates:
        try:
            return ct.WinDLL(name)  # type: ignore[attr-defined]
        except OSError as exc:
            errors.append(f"{name}: {exc}")

    raise CifXBindingError(
        "Could not load the cifX driver DLL. Tried: "
        + "; ".join(errors)
        + ". Set CIFX_DLL_PATH to the driver DLL installed with the "
        "Hilscher cifX/CIFX PROFINET card."
    )


class CifXLibrary:
    """Thin, typed wrapper around the raw cifX API function pointers."""

    def __init__(self, dll_path: Optional[str] = None):
        self.dll = _load_library(dll_path)
        self._bind()

    def _bind(self) -> None:
        dll = self.dll

        dll.xDriverOpen.argtypes = [ct.POINTER(HANDLE)]
        dll.xDriverOpen.restype = ct.c_uint32

        dll.xDriverClose.argtypes = [HANDLE]
        dll.xDriverClose.restype = ct.c_uint32

        dll.xDriverGetErrorDescription.argtypes = [
            ct.c_int32,
            ct.c_char_p,
            ct.c_uint32,
        ]
        dll.xDriverGetErrorDescription.restype = ct.c_uint32

        dll.xDriverEnumBoards.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.c_uint32,
            ct.POINTER(BOARD_INFORMATION),
        ]
        dll.xDriverEnumBoards.restype = ct.c_uint32

        dll.xChannelOpen.argtypes = [
            HANDLE,
            ct.c_char_p,
            ct.c_uint32,
            ct.POINTER(HANDLE),
        ]
        dll.xChannelOpen.restype = ct.c_uint32

        dll.xChannelClose.argtypes = [HANDLE]
        dll.xChannelClose.restype = ct.c_uint32

        dll.xChannelInfo.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(CHANNEL_INFORMATION),
        ]
        dll.xChannelInfo.restype = ct.c_uint32

        dll.xChannelIORead.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_void_p,
            ct.c_uint32,
        ]
        dll.xChannelIORead.restype = ct.c_uint32

        dll.xChannelIOWrite.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_void_p,
            ct.c_uint32,
        ]
        dll.xChannelIOWrite.restype = ct.c_uint32

        # Reads back the output process-data image as last written by
        # xChannelIOWrite. Confirmed signature (no timeout argument) from
        # Hilscher's PyCifx demo.
        dll.xChannelIOReadSendData.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_void_p,
        ]
        dll.xChannelIOReadSendData.restype = ct.c_uint32

        dll.xChannelHostState.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(ct.c_uint32),
            ct.c_uint32,
        ]
        dll.xChannelHostState.restype = ct.c_uint32

        dll.xChannelBusState.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(ct.c_uint32),
            ct.c_uint32,
        ]
        dll.xChannelBusState.restype = ct.c_uint32

        dll.xChannelWatchdog.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(ct.c_uint32),
        ]
        dll.xChannelWatchdog.restype = ct.c_uint32

        dll.xChannelReset.argtypes = [HANDLE, ct.c_uint32, ct.c_uint32]
        dll.xChannelReset.restype = ct.c_uint32
