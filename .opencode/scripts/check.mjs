#!/usr/bin/env node
// Offscreen smoke test: import the overlay (which pulls in the Qt-free
// core, storage, format, tray, hotkey) without showing a window. Catches
// broken imports and mismatched Qt enums before launching the GUI.
import { spawnSync } from "node:child_process";

const python = process.env.PYTHON || "python";
const snippet =
  "import os;" +
  "os.environ['QT_QPA_PLATFORM']='offscreen';" +
  "from plotruler.overlay import OverlayWindow;" +
  "from plotruler import format, storage;" +
  "print('imports OK')";

const res = spawnSync(python, ["-c", snippet], {
  stdio: "inherit",
  cwd: process.cwd(),
});
process.exit(res.status ?? 1);
