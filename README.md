# PlotRuler

A translucent desktop overlay for accurately reading (X, Y) values off a graph shown on screen.

PlotRuler does not render the graph; it is a live see-through overlay.  The graph is whatever is running underneath — a browser, a PDF viewer, a plotting window. Calibrate once by clicking a couple of known points and typing their labels, then hover to read coordinates anywhere else, and click to copy coordinates to clipboard.

## Quick start

### Windows (exe)

grab `PlotRuler.exe` from the [latest release](https://github.com/endolith/plotruler/releases), run it, and press **Win+Alt+P** to summon the overlay.

### All platforms (Python)

```sh
pip install plotruler
plotruler
```

> On Linux, an **X11 session** is required, and the Qt X11 backend needs the `libxcb-cursor` system library (pip cannot install it):
>
> ```sh
> sudo apt install libxcb-cursor0        # Debian / Ubuntu
> sudo dnf install xcb-util-cursor       # Fedora / RHEL
> sudo pacman -S xcb-util-cursor         # Arch
> ```

The first time, press **Ctrl+N** to calibrate: click two points on the X axis and two on the Y axis, typing each point's labeled value. Readout works immediately after.

## Features

- **Hover to read** — a crosshair and a live `(X, Y)` readout follow the cursor once calibrated.
- **Click to copy** — a click copies the hovered coordinate (e.g. `12.5, 4.0`) and flashes confirmation.
- **Number formats** — plain, scientific, engineering, E-notation, and SI prefixes; cycle with the number keys `1`–`6` or from the tray menu.
- **Linear or log axes** — each axis is calibrated independently and can be linear or log scale.
- **Persists** — calibration, window position, and number format survive restarts, so the overlay reopens already calibrated.
- **Frameless & tray-resident** — a custom translucent title bar; the overlay lives in the system tray and toggles with a tray click or hotkey.

## Usage

- **Ctrl+N** — start a calibration.
- **Ctrl+Z** — undo the last calibration step.
- **Esc** — cancel a calibration, or hide the overlay.
- **Win+Alt+P** — toggle the overlay (Windows, configurable).
- **1**–**6** — switch the readout number format (when the overlay is focused).
- **Tray icon** — show/hide, start a calibration, change the hotkey, change the number format, quit.

The calibration prompt, its hints, and the `(X, Y)` readout are drawn on the overlay itself; see the on-screen instructions while calibrating. Without a system tray there's no way to summon a hidden overlay, so on such systems Esc (and minimize) quit instead of hiding, and a close button is shown.

## How it works

Calibration and readout use **absolute screen coordinates** (physical pixels), not coordinates relative to the overlay window. That is what keeps the calibration glued to the graph: you can drag or resize the overlay and the calibrated region stays put over the plot beneath it.

Each axis is a line fit through two reference points — a screen pixel and its value. After you enter the second point on an axis, a **Linear / Log** choice appears; pick one for that axis, then move on to the next. (If a point's value is zero or negative, a log scale is impossible, so that axis is automatically linear and the choice is skipped.)

### Platform support

| | Windows | macOS | Linux (X11) |
| --- | --- | --- | --- |
| Overlay readout | ✅ | ✅ | ✅ |
| Calibration survives window move | ✅ | ✅ | ✅ |
| Global hotkey | ✅ (Win+Alt+P) | ⏳ | ⏳ |
| System tray | ✅ | ✅ | ⚠️ (DE-dependent) |

**Wayland is not supported yet.** Wayland forbids absolute screen coordinates by design, so the overlay model cannot work there today without a window-relative rewrite. Use an X11 session on Linux. Longer-term the plan is to support Wayland as a *regular* (non-overlay) window: a normal window doesn't need absolute coordinates, so it works there. macOS is architecturally supported (Qt provides a native path) but no macOS build exists yet — treat that column as planned, not shipped.

## Configuration

Settings live in a per-user `plotruler.json` config file in the platform's application-data location — `%LOCALAPPDATA%/PlotRuler` on Windows, `~/.config/PlotRuler` on Linux. Calibration, window geometry, the global hotkey, and the number format are all saved there.

## Building from source

For contributors and local development. Requires Python 3.10+:

```sh
git clone https://github.com/endolith/plotruler.git
cd plotruler
pip install -e ".[dev]"
plotruler
```

The test/dev commands are `pytest`, `ruff check .`, and `ruff format .`.

### Build the Windows exe

```sh
python -m pip install pyinstaller
python build/build.py
```

This produces a single-file `dist/PlotRuler.exe` (~46 MB, bundles Qt and needs no Python install) — the artifact attached to a GitHub release.

## License

MIT (see `LICENSE`).

(This was generated almost entirely by AI under human direction, so likely lacks the human authorship required for copyright in the US and is therefore in the public domain. MIT license applies anywhere else.)
