"""Local password gate for the desktop app's configuration actions.

This is not multi-user security - anyone with access to the machine
already has access to the config files and the gateway process. It exists
to stop an operator from fat-fingering the gateway/DLL configuration or an
accidental Restart Gateway click, not to defend against a determined
attacker. The password hash is salted (PBKDF2-HMAC-SHA256) and stored next
to the GUI's own settings, separate from gui_config.json so a config
export/backup doesn't carry the password hash along with it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

DEFAULT_AUTH_PATH = Path.home() / ".cfix_gateway" / "auth.json"
DEFAULT_PASSWORD = "admin"
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS).hex()


def _load(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def ensure_password_set(path: Path = DEFAULT_AUTH_PATH) -> None:
    """Creates the auth file with DEFAULT_PASSWORD if none exists yet (first run)."""
    if _load(path) is not None:
        return
    set_password(DEFAULT_PASSWORD, path)


def set_password(password: str, path: Path = DEFAULT_AUTH_PATH) -> None:
    salt = os.urandom(16)
    data = {"salt": salt.hex(), "hash": _hash_password(password, salt)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def verify_password(password: str, path: Path = DEFAULT_AUTH_PATH) -> bool:
    data = _load(path)
    if data is None:
        return password == DEFAULT_PASSWORD
    salt = bytes.fromhex(data["salt"])
    return _hash_password(password, salt) == data["hash"]
