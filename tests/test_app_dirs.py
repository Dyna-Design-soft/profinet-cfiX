import sys
from pathlib import Path

from cfix_api.gui.app_dirs import default_data_dir


def test_default_data_dir_uses_home_when_not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert default_data_dir() == Path.home() / ".cfix_gateway"


def test_default_data_dir_uses_exe_folder_when_frozen(monkeypatch, tmp_path):
    exe_path = tmp_path / "dist" / "CFIX Gateway.exe"
    exe_path.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))
    assert default_data_dir() == exe_path.parent / ".cfix_gateway"
