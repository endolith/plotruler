#!/usr/bin/env node
// Kill any running PlotRuler dev instance and relaunch it.
//
// Never blanket-kill python: only processes whose command line mentions
// 'plotruler' are stopped. The relaunch then starts the app in the
// foreground. The tray-resident app never exits, so this script blocks
// until the shell times out — that is expected, not a crash.
import { spawn, spawnSync } from "node:child_process";

const python = process.env.PYTHON || "python";

function killPlotRuler() {
  const plat = process.platform;
  let list;
  if (plat === "win32") {
    // PowerShell's CIM query returns process ids to kill.
    const ps = spawnSync(
      "powershell.exe",
      [
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | " +
          "Where-Object { $_.CommandLine -match 'plotruler' } | " +
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
      ],
      { stdio: "inherit" },
    );
    return ps.status ?? 0;
  }
  // Non-Windows: pkill matching the package path.
  const res = spawnSync("pkill", ["-f", "plotruler"], { stdio: "ignore" });
  // pkill returns 1 when nothing matched, which is fine.
  return 0;
}

killPlotRuler();
// Give the OS a moment to release the socket/process before relaunching.
const wait = spawnSync("node", ["-e", "setTimeout(()=>{}, 1000)"], {
  stdio: "inherit",
});
const app = spawn(python, ["-m", "plotruler"], {
  stdio: "inherit",
  cwd: process.cwd(),
});
app.on("exit", (code) => process.exit(code ?? 0));
