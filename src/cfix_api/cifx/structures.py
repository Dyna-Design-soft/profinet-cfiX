"""ctypes mirrors of structures used by the cifX Device Driver API.

Field layout verified against Hilscher's own "PyCifx" reference demo
(hilscher/cifXUser.py) rather than guessed from header names alone -
including `_pack_ = 1`, which matters here: the driver's C structs are
byte-packed, and ctypes' default alignment padding would silently produce
the wrong layout on a call like xDriverEnumBoards/xChannelInfo.
"""

from __future__ import annotations

import ctypes as ct

HANDLE = ct.c_void_p

CIFX_MAX_INFO_NAME_LENGTH = 16


class SYSTEM_CHANNEL_SYSTEM_INFO_BLOCK(ct.Structure):
    _fields_ = [
        ("abCookie", ct.c_char * 4),
        ("ulDpmTotalSize", ct.c_uint32),
        ("ulDeviceNumber", ct.c_uint32),
        ("ulSerialNumber", ct.c_uint32),
        ("ausHwOptions", ct.c_uint16 * 4),
        ("usManufacturer", ct.c_uint16),
        ("usProductionDate", ct.c_uint16),
        ("ulLicenseFlags1", ct.c_uint32),
        ("ulLicenseFlags2", ct.c_uint32),
        ("usNetxLicenseID", ct.c_uint16),
        ("usNetxLicenseFlags", ct.c_uint16),
        ("usDeviceClass", ct.c_uint16),
        ("bHwRevision", ct.c_uint8),
        ("bHwCompatibility", ct.c_uint8),
        ("bDevIdNumber", ct.c_uint8),
        ("bReserved", ct.c_uint8),
        ("ausReserved", ct.c_uint16),
    ]
    _pack_ = 1


class BOARD_INFORMATION(ct.Structure):
    _fields_ = [
        ("lBoardError", ct.c_int32),
        ("abBoardName", ct.c_char * CIFX_MAX_INFO_NAME_LENGTH),
        ("abBoardAlias", ct.c_char * CIFX_MAX_INFO_NAME_LENGTH),
        ("ulBoardID", ct.c_uint32),
        ("ulSystemError", ct.c_uint32),
        ("ulPhysicalAddress", ct.c_uint32),
        ("ulIrqNumber", ct.c_uint32),
        ("bIrqEnabled", ct.c_uint8),
        ("ulChannelCnt", ct.c_uint32),
        ("ulDpmTotalSize", ct.c_uint32),
        ("tSystemInfo", SYSTEM_CHANNEL_SYSTEM_INFO_BLOCK),
    ]
    _pack_ = 1


class CHANNEL_INFORMATION(ct.Structure):
    _fields_ = [
        ("abBoardName", ct.c_char * CIFX_MAX_INFO_NAME_LENGTH),
        ("abBoardAlias", ct.c_char * CIFX_MAX_INFO_NAME_LENGTH),
        ("ulDeviceNumber", ct.c_uint32),
        ("ulSerialNumber", ct.c_uint32),
        ("usFWMajor", ct.c_uint16),
        ("usFWMinor", ct.c_uint16),
        ("usFWBuild", ct.c_uint16),
        ("usFWRevision", ct.c_uint16),
        ("bFWNameLength", ct.c_uint8),
        ("abFWName", ct.c_char * 63),
        ("usFWYear", ct.c_uint16),
        ("bFWMonth", ct.c_uint8),
        ("bFWDay", ct.c_uint8),
        ("ulChannelError", ct.c_uint32),
        ("ulOpenCnt", ct.c_uint32),
        ("ulPutPacketCnt", ct.c_uint32),
        ("ulGetPacketCnt", ct.c_uint32),
        ("ulMailboxSize", ct.c_uint32),
        ("ulIOInAreaCnt", ct.c_uint32),
        ("ulIOOutAreaCnt", ct.c_uint32),
        ("ulHskSize", ct.c_uint32),
        ("ulNetxFlags", ct.c_uint32),
        ("ulHostFlags", ct.c_uint32),
        ("ulHostCOSFlags", ct.c_uint32),
        ("ulDeviceCOSFlags", ct.c_uint32),
    ]
    _pack_ = 1
