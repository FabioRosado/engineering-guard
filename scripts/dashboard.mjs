// `npm run dashboard`: build the factory UI when it is missing or stale, then run the central
// server in the foreground (decision D32). Stop it with Ctrl-C.
//
// "Stale" means any UI source is newer than the built index.html (see ui-build-state.mjs). The
// build is skipped otherwise, so starting the dashboard stays fast once the UI is built.

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildReason } from "./ui-build-state.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const uiDirectory = join(root, "ui");
const serverScript = join(root, ".agents", "skills", "factory", "scripts", "central_factory_server.py");

function run(command, args, options) {
  const result = spawnSync(command, args, { stdio: "inherit", ...options });
  if (result.error?.code === "ENOENT") {
    console.error(`Could not run ${command}: it is not installed or not on PATH.`);
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(`${command} ${args.join(" ")} failed (exit ${result.status}).`);
    process.exit(result.status ?? 1);
  }
}

const reason = buildReason(uiDirectory);
if (reason) {
  console.error(`Building the factory UI: ${reason}.`);
  if (!existsSync(join(uiDirectory, "node_modules"))) run("npm", ["install", "--no-audit", "--no-fund"], { cwd: uiDirectory });
  run("npm", ["run", "build"], { cwd: uiDirectory });
}

// Forward the arguments (for example --port) and let the server own the terminal until Ctrl-C.
const server = spawn("python3", [serverScript, ...process.argv.slice(2)], { stdio: "inherit" });
server.on("error", (error) => {
  console.error(`Could not start the server: ${error.message}`);
  process.exit(1);
});
server.on("exit", (code, signal) => process.exit(signal ? 0 : code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
