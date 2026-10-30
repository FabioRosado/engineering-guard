// Decides whether the factory UI needs building. Separate from the launcher so the decision can
// be tested without starting a server.

import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

// Everything that changes the built output. node_modules and dist are excluded on purpose.
export const SOURCE_ROOTS = ["src", "index.html", "package.json", "package-lock.json", "vite.config.js", "svelte.config.js"];

function newestModification(path) {
  const stats = statSync(path, { throwIfNoEntry: false });
  if (!stats) return 0;
  if (!stats.isDirectory()) return stats.mtimeMs;
  return readdirSync(path).reduce((newest, name) => Math.max(newest, newestModification(join(path, name))), 0);
}

// Returns why a build is needed, or null when dist/ is current.
export function buildReason(uiDirectory) {
  const builtIndex = join(uiDirectory, "dist", "index.html");
  if (!existsSync(builtIndex)) return "the UI has not been built";
  const builtAt = statSync(builtIndex).mtimeMs;
  const changed = SOURCE_ROOTS.find((name) => newestModification(join(uiDirectory, name)) > builtAt);
  return changed ? `ui/${changed} changed since the last build` : null;
}
