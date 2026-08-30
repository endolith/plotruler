#!/usr/bin/env node
// Rebuild the standalone PlotRuler executable for Windows.
//
// Kills any running PlotRuler dev instance (never blanket-killing python),
// wipes the PyInstaller work dir and dist, then rebuilds from the spec.
// The build output lands in dist/PlotRuler.exe.
import { spawnSync } from "node:child_process";

const python = process.env.PYTHON || "python";

// Stop only processes whose command line mentions plotruler/PyInstaller.
const kill = spawnSync(
  "powershell.exe",
  [
    "-NoProfile",
    "-Command",
    "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | " +
      "Where-Object { $_.CommandLine -match 'plotruler|PyInstaller' } | " +
      "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
  ],
  { stdio: "inherit" },
);
if (kill.status !== 0) {
  console.error("Failed to kill running instances:", kill.status);
  process.exit(kill.status);
}

// Give the OS a moment to release the previous instance's locks.
spawnSync("node", ["-e", "setTimeout(()=>{}, 1200)"], { stdio: "inherit" });

for (const dir of ["build/plotruler", "dist"]) {
  spawnSync("node", ["-e", `require('fs').rmSync('${dir}', {recursive:true, force:true})`]);
}

const res = spawnSync(
  python,
  ["-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "dist", "build/plotruler.spec"],
  { stdio: "inherit", cwd: process.cwd() },
);
process.exit(res.status ?? 1);
