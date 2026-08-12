"""ctypes bindings to Hilscher's cifX Device Driver API.

This wraps the public, documented cifX API (cifXUser.h): xDriverOpen,
xDriverClose, xChannelOpen, xChannelClose, xChannelIORead, xChannelIOWrite,
xChannelHostState, xChannelBusState, xChannelWatchdog and xChannelReset.

On a Windows target with the Hilscher cifX driver installed, the driver
DLL is loaded by name. Multiple historical DLL names have been used by
different driver package versions, so a short candidate list is tried;
set the CIFX_DLL_PATH environment variable (or pass dll_path explicitly)
to point at a specific file instead.
"""

from __future__ import annotations

import ctypes as ct
import os
from typing import Optional

from .structures import BOARD_INFORMATION, CHANNEL_INFORMATION, HANDLE

DEFAULT_DLL_CANDIDATES = (
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
        dll.xDriverOpen.restype = ct.c_int32

        dll.xDriverClose.argtypes = [HANDLE]
        dll.xDriverClose.restype = ct.c_int32

        dll.xDriverGetErrorDescription.argtypes = [
            ct.c_int32,
            ct.c_char_p,
            ct.c_uint32,
        ]
        dll.xDriverGetErrorDescription.restype = ct.c_int32

        dll.xDriverEnumBoards.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.c_uint32,
            ct.POINTER(BOARD_INFORMATION),
        ]
        dll.xDriverEnumBoards.restype = ct.c_int32

        dll.xChannelOpen.argtypes = [
            HANDLE,
            ct.c_char_p,
            ct.c_uint32,
            ct.POINTER(HANDLE),
        ]
        dll.xChannelOpen.restype = ct.c_int32

        dll.xChannelClose.argtypes = [HANDLE]
        dll.xChannelClose.restype = ct.c_int32

        dll.xChannelInfo.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(CHANNEL_INFORMATION),
        ]
        dll.xChannelInfo.restype = ct.c_int32

        dll.xChannelIORead.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_void_p,
            ct.c_uint32,
        ]
        dll.xChannelIORead.restype = ct.c_int32

        dll.xChannelIOWrite.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_uint32,
            ct.c_void_p,
            ct.c_uint32,
        ]
        dll.xChannelIOWrite.restype = ct.c_int32

        dll.xChannelHostState.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(ct.c_uint32),
            ct.c_uint32,
        ]
        dll.xChannelHostState.restype = ct.c_int32

        dll.xChannelBusState.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(ct.c_uint32),
            ct.c_uint32,
        ]
        dll.xChannelBusState.restype = ct.c_int32

        dll.xChannelWatchdog.argtypes = [
            HANDLE,
            ct.c_uint32,
            ct.POINTER(ct.c_uint32),
        ]
        dll.xChannelWatchdog.restype = ct.c_int32

        dll.xChannelReset.argtypes = [HANDLE, ct.c_uint32, ct.c_uint32]
        dll.xChannelReset.restype = ct.c_int32
