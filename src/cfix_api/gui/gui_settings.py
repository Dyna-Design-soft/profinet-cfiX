"""Persists the GUI's gateway configuration across app launches.

Separate from the CLI's config/*.json files: the GUI always starts the
gateway automatically using whatever was last saved here (or sensible
defaults on first run), edited only through its two config dialogs.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from ..gateway.config import CifxConfig, GatewayConfig
from .app_dirs import default_data_dir

DEFAULT_SETTINGS_PATH = default_data_dir() / "gui_config.json"


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> GatewayConfig:
    if path.exists():
        try:
            return GatewayConfig.load(path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    # First run (or an unreadable file): default to the mock backend so the
    # app comes up working with no hardware attached yet. Real deployment
    # settings are then set once via "DLL Configuration" and persist here.
    return GatewayConfig(cifx=CifxConfig(mock=True))


def save_settings(config: GatewayConfig, path: Path = DEFAULT_SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dataclasses.asdict(config), fh, indent=2)
