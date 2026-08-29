# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the PlotRuler executable.

Build with:
    pyinstaller build/plotruler.spec

Produces a single-file, windowed (no console) exe at dist/PlotRuler.exe.
The app is a tray-resident overlay, so no console is needed; crash and
debug output goes to %LOCALAPPDATA%\\PlotRuler\\crash.log.

The app uses only QtCore/QtGui/QtWidgets, so we let PyInstaller's PySide6
hooks pull the few DLLs and plugins those need and explicitly exclude the
dozens of Qt modules we never import (QtWebEngine etc.). Bundling them all
would balloon the exe past 250 MB. The plotruler package is small and pure
Python, so its own submodules are collected without data files.
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("plotruler")

# Qt modules the app never uses. Most are huge (QtWebEngine alone can add
# 100+ MB); excluding them keeps the exe well under the size a full PySide6
# bundle would produce. Only the clearly-heavy, clearly-unused ones are
# listed; light libraries that QtCore/Gui can pull transitively (QtNetwork,
# QtXml, QtDBus, QtConcurrent) are left alone so nothing breaks.
_HEAVY_QT_EXCLUDES = [
    "PySide6.Qt3D*",
    "PySide6.QtAxContainer",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia*",
    "PySide6.QtNfc",
    "PySide6.QtPdf*",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick*",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg*",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngine*",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
]

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
    ]
    + _HEAVY_QT_EXCLUDES,
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
