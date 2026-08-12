"""Gateway configuration: loaded from a JSON file (no extra dependency).

See config/gateway.example.json for a documented example.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TcpConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 9800


@dataclass
class UdpConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 9801


@dataclass
class CifxConfig:
    board_name: str = "cifX0"
    channel: int = 0
    # How long a single xChannelIORead/Write/etc. driver call is allowed to
    # block waiting for a result - not the PROFINET fieldbus cycle time
    # (that's configured on the card itself via Hilscher's bus config
    # tool). Kept low so one stalled driver call can't by itself blow a
    # tight end-to-end cyclic latency budget; raise it if your setup needs
    # more headroom than a fast cyclic target allows.
    io_timeout_ms: int = 20
    dll_path: Optional[str] = None
    mock: bool = False


@dataclass
class GatewayConfig:
    tcp: TcpConfig = field(default_factory=TcpConfig)
    udp: UdpConfig = field(default_factory=UdpConfig)
    cifx: CifxConfig = field(default_factory=CifxConfig)
    log_level: str = "INFO"

    @classmethod
    def from_dict(cls, raw: dict) -> "GatewayConfig":
        return cls(
            tcp=TcpConfig(**raw.get("tcp", {})),
            udp=UdpConfig(**raw.get("udp", {})),
            cifx=CifxConfig(**raw.get("cifx", {})),
            log_level=raw.get("log_level", "INFO"),
        )

    @classmethod
    def load(cls, path: str | Path) -> "GatewayConfig":
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return cls.from_dict(raw)
