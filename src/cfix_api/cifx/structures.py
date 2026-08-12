"""ctypes mirrors of the structures used by the cifX Device Driver API
(cifXUser.h). Only fields needed by this gateway are declared.
"""

from __future__ import annotations

import ctypes as ct

HANDLE = ct.c_void_p

BOARD_NAME_LEN = 32
CHANNEL_INFO_LEN = 32


class BOARD_INFORMATION(ct.Structure):
    _fields_ = [
        ("abBoardName", ct.c_char * BOARD_NAME_LEN),
        ("abBoardAlias", ct.c_char * BOARD_NAME_LEN),
        ("ulBoardID", ct.c_uint32),
        ("ulSystemError", ct.c_uint32),
        ("ulChannelCnt", ct.c_uint32),
        ("ulDeviceNumber", ct.c_uint32),
        ("ulSerialNumber", ct.c_uint32),
    ]


class CHANNEL_INFORMATION(ct.Structure):
    _fields_ = [
        ("abBoardName", ct.c_char * BOARD_NAME_LEN),
        ("abBoardAlias", ct.c_char * BOARD_NAME_LEN),
        ("ulDeviceNumber", ct.c_uint32),
        ("ulSerialNumber", ct.c_uint32),
        ("ulChannelError", ct.c_uint32),
        ("ulOpenCnt", ct.c_uint32),
        ("ulPhysicalAddress", ct.c_uint32),
        ("ulIrqCount", ct.c_uint32),
        ("bIrqEnabled", ct.c_uint8),
        ("ulHostFlags", ct.c_uint32),
        ("ulHostCOSFlags", ct.c_uint32),
        ("ulDeviceCOSFlags", ct.c_uint32),
        ("ulNetxFlags", ct.c_uint32),
        ("ulHostState", ct.c_uint32),
        ("ulDeviceState", ct.c_uint32),
        ("ulExtendedDiagFlags", ct.c_uint32),
        ("abDeviceCOSFlags", ct.c_uint8 * CHANNEL_INFO_LEN),
    ]
