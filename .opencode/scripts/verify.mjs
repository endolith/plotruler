#!/usr/bin/env node
// Lint, format-check, and run the test suite. Exits nonzero on failure.
import { spawnSync } from "node:child_process";

const steps = [
  ["ruff lint", ["-m", "ruff", "check", "."]],
  ["ruff format check", ["-m", "ruff", "format", "--check", "."]],
  ["pytest", ["-m", "pytest", "-q"]],
];

// Run the conda env's python as-is (assuming it is already active).
const python = process.env.PYTHON || "python";

let ok = true;
for (const [label, args] of steps) {
  const res = spawnSync(python, args, { stdio: "inherit", cwd: process.cwd() });
  if (res.status !== 0) {
    console.error(`\nFAILED: ${label} (exit ${res.status})`);
    ok = false;
    break;
  }
}
process.exit(ok ? 0 : 1);
