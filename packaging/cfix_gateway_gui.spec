# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the CFIX Gateway desktop app: single-file
onefile build (one CFIX Gateway.exe, self-extracts to a temp dir on each
launch - a few seconds slower to start than a folder build, but simplest
to hand to someone else or copy around).

Build on Windows (PyInstaller output is platform-specific - this must run
on the Windows machine you want the .exe for, not in CI or another OS):

    cd profinet-cfiX
    .venv\\Scripts\\pip install -e .[gui,build]
    .venv\\Scripts\\pyinstaller packaging\\cfix_gateway_gui.spec

Output: dist\\CFIX Gateway.exe - windowed, no console (the app's own Log
panel already shows gateway output).

Rebuilding after code changes: just re-run the pyinstaller command above;
delete the build\\ and dist\\ folders first if you hit stale-cache issues.

Prefer a faster-starting folder build instead of one file? Swap the EXE()
call below for the onedir form - see packaging/README.md.
"""

from pathlib import Path

repo_root = Path(SPECPATH).resolve().parent
entry_script = str(repo_root / "packaging" / "run_gui.py")

a = Analysis(
    [entry_script],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CFIX Gateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
