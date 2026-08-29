# PlotRuler

A translucent desktop overlay for accurately reading (X, Y) values off a graph shown on screen. Calibrate once against the known plot coordinates (click at two points on each axis, and type their labeled values), then hover to read coordinates anywhere else, and click to copy.

The graph itself is not rendered by PlotRuler — it is whatever other app is on screen underneath the overlay (a browser, a PDF viewer, a plotting window, etc.) PlotRuler is a live translucent overlay that reads through it, not a screenshot workflow.

## Development

```sh
conda activate plotruler
python -m plotruler        # run the app
pytest                     # run tests
ruff check .               # lint
ruff format .              # auto-format
```

## Linux

Linux requires an X11 session; Wayland support is deferred (see `LINUX_PLAN.md`).
Qt 6.5+ also needs the `xcb-cursor` system library for the X11 backend, which
pip cannot install:

```sh
# Debian / Ubuntu
sudo apt install libxcb-cursor0
# Fedora / RHEL
sudo dnf install xcb-util-cursor
# Arch
sudo pacman -S xcb-util-cursor
```

Install and run (no frozen binary on Linux):

```sh
./build/install_linux.sh    # or: pip install -e . then plotruler
plotruler
```

The global hotkey (Win+Alt+P) is Windows-only for now; use the tray icon to
show/hide the overlay.

## Build a stand-alone executable

```sh
python -m pip install pyinstaller
python build/build.py
```

Produces a single-file, windowed `dist/PlotRuler.exe` with a tray icon and
version metadata. The app bundles Qt, so the exe is ~46 MB but needs no
Python install to run.

See `AGENTS.md` for development conventions.

## License

MIT License (see `LICENSE`).

(This was generated almost entirely by AI under human direction, so likely lacks the human authorship required for copyright in the US and is therefore in the public domain.  MIT license applies anywhere else.)
