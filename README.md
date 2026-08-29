# PlotRuler

A translucent desktop overlay for accurately reading (X, Y) values off a graph
shown on screen. Calibrate once against the known plot coordinates (click at two
points on each axis, and type their labeled values), then hover to read
coordinates anywhere else, and click to copy.

The graph itself is not rendered by PlotRuler — it is whatever other app is on
screen underneath the overlay (a browser, a PDF viewer, a plotting window, etc.)
PlotRuler is a **live translucent overlay** that reads through it, not a
screenshot workflow.

## How it works

Calibration and readout all live in **absolute screen coordinates** (physical
pixels), not coordinates relative to the overlay window. That is what makes the
overlay feel stable: you can drag or resize the window and the calibrated graph
box stays glued to the graph underneath wherever it sits on screen. Windows and
macOS get this natively; Linux/X11 uses the same absolute-coordinate model.

Each axis is calibrated independently with two reference points — click once at
a known pixel on the axis, type its labeled value, then repeat for a second
point. PlotRuler fits a line through those pairs (linear by default, optional
log), so it works for any graph where the scale is straight-line or log.
Everything persists to disk (calibration, window position, number format), so
the overlay reopens already calibrated.

## Features

- **Hover to read** — a crosshair and a (X, Y) readout follow the cursor once
  calibrated, showing the values under it.
- **Click to copy** — a click copies the hovered coordinate as e.g.
  `(12.5, 4.0)` and flashes a confirmation.
- **Number formats** — plain, scientific, engineering, E-notation, SI
  (auto/1..6 via the number keys, or the tray menu).
- **Calibration** — Ctrl+N starts a fresh one; Ctrl+Z undoes a step; Esc
  cancels. Each axis gets its own linear/log choice.
- **Custom frameless title bar** — translucent, with minimize, maximize, and
  (on no-tray systems) a close button.
- **Tray resident** — sits in the system tray; tray click toggles the overlay.

## Platform comparison

| | Windows | macOS | Linux/X11 |
|---|---|---|---|
| Absolute screen coordinates | ✅ native | ✅ native | ✅ (same model) |
| Overlay readout through the graph | ✅ | ✅ | ✅ |
| Move / resize the window | ✅ native | ✅ native | ✅ Qt-driven |
| Calibration survives window move/resize | ✅ | ✅ | ✅ |
| Global hotkey (Win+Alt+P / Cmd+Alt+P) | ✅ RegisterHotKey | ⏳ | ⏳ deferred (XGrabKey) |
| System tray | ✅ | ✅ | ⚠️ depends on DE |
| Build/ship | .exe (PyInstaller) | ⏳ untested | editable install |

**Wayland is not supported yet.** Wayland forbids absolute screen coordinates by
design and GNOME refuses the workarounds, so the overlay model cannot work there
without a window-relative rewrite. Linux requires an **X11** session for now;
see `LINUX_PLAN.md`.

Notes on the platform table:
- **macOS is untested.** The architecture is OS-portable (absolute screen
  coordinates, Qt overlay), and Qt provides a native macOS path, but no macOS
  build or hotkey code exists in this repo yet. Treat the macOS column as a
  design feature, not a shipped one.
- **Global hotkey** — Windows-only today. On Linux the tray (or Ctrl+N/Esc and
  the title-bar buttons) are the controls; an X11 `XGrabKey` hotkey is a
  follow-up.
- **System tray** — always present on Windows; on Linux it depends on the
  desktop environment. GNOME has no tray by default unless the *AppIndicator
  and KStatusNotifier* extension is installed. When no tray exists, PlotRuler
  shows a close button and quits on minimize/close/Esc rather than hiding into
  an unreachable state.

## Development

```sh
conda activate plotruler
python -m plotruler        # run the app
pytest                     # run tests
ruff check .               # lint
ruff format .              # auto-format
```

## Linux

Linux requires an X11 session (Wayland is deferred — see above). Qt 6.5+
also needs the `xcb-cursor` system library for the X11 backend, which pip
cannot install:

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

> The installer checks for `libxcb-cursor` and fails fast with your distro's
> package name if it is missing, since the app would otherwise abort at first
> launch.

## Build a stand-alone executable (Windows)

```sh
python -m pip install pyinstaller
python build/build.py
```

Produces a single-file, windowed `dist/PlotRuler.exe` with a tray icon and
version metadata. The app bundles Qt, so the exe is ~46 MB but needs no Python
install to run.

See `AGENTS.md` for development conventions.

## License

MIT License (see `LICENSE`).

(This was generated almost entirely by AI under human direction, so likely lacks the human authorship required for copyright in the US and is therefore in the public domain.  MIT license applies anywhere else.)
