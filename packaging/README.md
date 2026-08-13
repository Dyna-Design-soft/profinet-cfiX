# Building the CFIX Gateway .exe

PyInstaller output is platform-specific: build **on the Windows machine**
you want the `.exe` for (this can't be built from Linux/macOS/CI and
produce a working Windows binary).

## One-file build (default)

```powershell
cd profinet-cfiX
.venv\Scripts\pip install -e .[gui,build]
.venv\Scripts\pyinstaller packaging\cfix_gateway_gui.spec
```

Output: `dist\CFIX Gateway.exe` — a single file, windowed (no console
window; the app's own Log panel already shows gateway output). Simplest
to copy around or hand to someone else. Self-extracts to a temp folder on
each launch, so startup is a few seconds slower than a folder build.

## Folder build (faster startup)

If you'd rather have a folder with a fast-starting `.exe` plus its
supporting files alongside it (better for running it often on the same
dev machine), replace the `EXE(...)` block at the bottom of
`cfix_gateway_gui.spec` with:

```python
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CFIX Gateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CFIX Gateway",
)
```

then run the same `pyinstaller` command. Output:
`dist\CFIX Gateway\CFIX Gateway.exe`, with its supporting DLLs/resources
in the same folder — distribute the whole folder, not just the `.exe`.

## What's *not* bundled

The Hilscher cifX driver DLL (`cifX32DLL.dll`/`cifX64DLL.dll`) stays
external — it's loaded at runtime via `ctypes` from whatever path is set
in **DLL Configuration…** (or auto-detected), the same as when running
from source. The built `.exe` still needs the Hilscher driver/DLL
installed on whatever machine runs it, same as today.

## Rebuilding after code changes

Just re-run the `pyinstaller` command above. If you hit a stale-cache
issue (old code seemingly still running from a fresh build), delete the
`build\` and `dist\` folders first and rebuild.

## Troubleshooting

If the build fails to find Qt plugins or crashes on launch with a
PySide6-related import error, try `pip install pyinstaller-hooks-contrib`
in the same venv and rebuild — PyInstaller's built-in PySide6 hook
usually covers this, but the contrib package fills gaps on some PySide6
versions. If it still fails, share the exact error.
