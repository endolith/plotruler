# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the PlotRuler executable.

Build with:
    pyinstaller build/plotruler.spec

Produces a single-file, windowed (no console) exe at dist/PlotRuler.exe.
The app is a tray-resident overlay, so no console is needed; crash and
debug output goes to %LOCALAPPDATA%\\PlotRuler\\crash.log.
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = (
    collect_submodules("PySide6")
    + collect_submodules("shiboken6")
    + collect_submodules("plotruler")
)

datas = collect_data_files("PySide6")

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PlotRuler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="plotruler.ico",
    version="version_info.txt",
)
