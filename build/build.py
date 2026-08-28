"""Build the PlotRuler executable.

Regenerates the multi-size .ico from the tray icon, then runs PyInstaller
with the project's spec. Run from the repo root:

    python build/build.py

Requires PyInstaller installed in the active environment:
    python -m pip install pyinstaller
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
sys.path.insert(0, ROOT)

import make_ico  # noqa: E402  (regenerate the .ico first)


def main():
    # Render the .ico (needs a QApplication) before delegating to PyInstaller.
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    make_ico.build_ico(app, os.path.join(BUILD, "plotruler.ico"))
    app.quit()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        os.path.join(ROOT, "dist"),
        os.path.join(BUILD, "plotruler.spec"),
    ]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
