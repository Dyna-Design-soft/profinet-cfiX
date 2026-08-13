"""Where the desktop app stores its persisted data (gateway config, auth).

When running as a built .exe (PyInstaller sets sys.frozen = True and
sys.executable to the .exe's own path), data is kept in a folder next to
the executable, so the binary and its settings travel together as one
unit - easy to move, copy, or back up. When running from source (no
"exe location" to anchor to), falls back to a per-user folder in the
home directory, same as before.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DATA_DIR_NAME = ".cfix_gateway"


def default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / _DATA_DIR_NAME
    return Path.home() / _DATA_DIR_NAME
