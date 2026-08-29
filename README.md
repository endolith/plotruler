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
