# PlotRuler

PlotRuler is a **cross-platform** desktop overlay for reading (X, Y) values off a graph shown on screen. Calibrate once against a known plot (click two points per axis, type their values), then hover to read coordinates and click to copy.

The graph itself is **never rendered by PlotRuler** — it is whatever other app is on screen underneath the overlay (a browser, a PDF viewer, a plotting window). PlotRuler is a **live translucent overlay** that sits on top and reads through it, not a screenshot/frozen-image workflow. Calibration persists to disk across sessions and across hide/show.

Stack: Python 3.14 (conda env `plotruler`) · PySide6 6.11.2 (Qt) · pytest. The app is tray-resident; **Win+Alt+P** toggles the overlay.

## Quick commands

```sh
conda activate plotruler
python -m plotruler        # run the app
pytest                     # run tests
ruff check .               # lint
ruff format .              # auto-format
```

## Environment

- Work only in the conda env `plotruler` (Python 3.14). Never touch the system Python.
- Dependencies and tool config live in **`pyproject.toml`** (PEP 621, hatchling build backend). No `requirements.txt`.
- Windows is the primary platform, but the app is meant to be **cross-platform and useful to other people**. Keep the math and calibration model platform-agnostic; the overlay/tray/hotkey shell is Windows-first and may use small Win32 shims where needed.

## Code conventions

- **No type hints.** The owner prefers plain old-school Python. Clarity, simple names, and docstrings over annotations. (The codebase is read by humans, not type-checked.)
- Comments explain **why**, not what. If a comment would just restate the code, rewrite the code to be clearer instead. Never delete or omit comments while editing.
- Line length 79 (PEP8), enforced by ruff.
- Pythonic and simple. Write code a reader can follow without mental gymnastics; favor the clear, straightforward approach over clever one-liners and premature optimization.
- Architecture: the pixel→value calibration math must stay **Qt-free** (importable without PySide6) so it stays unit-testable and portable. Everything else (overlay, calibration UI, tray, hotkeys) is ordinary Qt code. No artificial core/shell package split beyond that.

## GUI conventions

- One frameless translucent window. Title bar, crosshair, readout, and instruction box are custom-painted with QPainter — there are no native widgets.
- Calibration is stored in **absolute screen coordinates** (physical pixels). Moving or resizing the overlay never invalidates a calibration.
- DPI-aware: Qt high-DPI scaling is on, and the math must stay correct at 100% and 150% display scaling. This silently corrupting values would be the worst failure mode.

## Testing

- pytest covers the math (`tests/test_*.py`). Every test function needs a docstring stating what behavior it verifies and why. New functions get tests; bug fixes get regression tests.
- The GUI is **not unit-tested** — translucent always-on-top overlays are interaction- heavy and don't test well without a running event loop. Keep widgets thin (logic in testable functions), and verify the GUI by running it. pytest-qt can be added later if a real need shows up.
- Give testing instructions to the user *before* running the program. 

## Hotkey

- **Win+Alt+P** is the default summon/toggle hotkey (P for PlotRuler). It is configurable — this is required, not optional. It is unclaimed on stock Windows; the only known collision is PowerToys' optional "Mouse Pointer Crosshairs", and Win+Ctrl+P is a free alternative if that matters. Avoid plain Ctrl+Alt+Space — Visual Studio and ReSharper both bind it, so IDE users would have to remap.
- **Ctrl+N** (new calibration) and **Esc** (hide) are in-app keys, not global.

## Commits

- Conventional Commits: `feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`.
- Small, atomic commits: one coherent idea plus its tests and docs — nothing else.
- Comprehensive messages: subject summarizes; body explains the problem, the approach, and any trade-offs.
- Add the trailer `Co-authored-by: opencode <opencode@anomalyco.ai>` to every commit.
- Never commit agent-generated scratch files (summary notes, session dumps, chat exports).

## Docs

- Update the README when user-visible behavior changes.
- Update this AGENTS.md when the development guidelines change.

## Scope (current)

MVP is: live translucent overlay; linear-rectangle calibration only (X axis then Y axis, two click-points each); hover-to-read; click-to-copy with "copied" confirmation; custom always-visible translucent title bar with resize handles; calibration + window position persistence; tray icon and global hotkey.

Deferred: corner/homography mode, log axes, X-only/Y-only modes, pins/slope readout, CSV digitizing, PyInstaller packaging.

`spec.md` is the product reference. When it conflicts with decisions recorded here, this file wins — the spec was AI-written and worded more rigidly than the product actually is.
