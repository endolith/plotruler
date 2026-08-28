"""Render PlotRuler's icon at multiple sizes and pack them into an .ico.

Qt's QPixmap.save only writes a single frame per ICO, so this script
renders each size to a temporary PNG and assembles the multi-image ICO
container by hand (the Windows ICO format stores PNG-compressed frames).
"""

import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

from plotruler.tray import make_icon

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(app, size):
    icon = make_icon(size)
    pixmap = icon.pixmap(size, size)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = handle.name
    pixmap.save(path, "PNG")
    with open(path, "rb") as handle:
        data = handle.read()
    os.unlink(path)
    return data


def build_ico(app, out_path):
    frames = {size: png_bytes(app, size) for size in SIZES}
    header = struct.pack("<HHH", 0, 1, len(SIZES))
    entries = []
    offset = 6 + 16 * len(SIZES)
    for size in SIZES:
        data = frames[size]
        w = size if size < 256 else 0
        h = size if size < 256 else 0
        entries.append(
            struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        )
        offset += len(data)
    with open(out_path, "wb") as handle:
        handle.write(header)
        for entry in entries:
            handle.write(entry)
        for size in SIZES:
            handle.write(frames[size])
    print(f"wrote {out_path}")


def main():
    app = QApplication([])
    out = os.path.join(os.path.dirname(__file__), "plotruler.ico")
    build_ico(app, out)
    app.quit()


if __name__ == "__main__":
    main()
