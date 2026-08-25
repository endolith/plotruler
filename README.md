# PlotRuler

A translucent desktop overlay for reading (X, Y) values off a graph shown on screen.
Calibrate once against a known plot (click two points per axis, type their values), then
hover to read coordinates and click to copy.

The graph itself is never rendered by PlotRuler — it is whatever other app is on screen
underneath the overlay (a browser, a PDF viewer, a plotting window). PlotRuler is a live
translucent overlay that reads through it, not a screenshot workflow.

## Development

```sh
conda activate plotruler
python -m plotruler        # run the app
pytest                     # run tests
ruff check .               # lint
ruff format .              # auto-format
```

See `AGENTS.md` for development conventions.
