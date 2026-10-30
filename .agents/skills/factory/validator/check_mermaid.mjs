// Validates the ```mermaid blocks in markdown files with mermaid's own parser.
//
// Usage: node check_mermaid.mjs <file.md> [...]
//
// stdout is always one JSON document:
//   {"diagrams": [{"file", "index", "line", "valid", "error"?}]}   exit 0: the check ran
//   {"unavailable": "<reason>"}                                     exit 3: the check could not run
//
// "Invalid diagram" and "could not check" are different outcomes on purpose: the board
// fails the former and only warns about the latter, so a machine without Node or the
// installed packages never blocks a job (decisions/factory-visual-handover.md, D37).
//
// Diagrams are located with marked's lexer, the library the dashboard uses to draw them, so the
// board validates exactly the blocks a person will see. Parsing needs a DOM, so mermaid runs inside jsdom. The bundled UMD build only loads when
// injected as a <script> element; evaluating it directly in the window fails. Rendering is
// not attempted here because it needs a real browser; the dashboard reports render failures.

import { readFileSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const UNAVAILABLE_EXIT_CODE = 3;

function reportUnavailable(reason) {
  process.stdout.write(JSON.stringify({ unavailable: reason }) + "\n");
  process.exit(UNAVAILABLE_EXIT_CODE);
}

// Returns [{ line, source }] where line is the 1-based line of the opening fence. `Lexer` is
// marked's lexer, passed in because it is an installed package: importing it statically would
// crash with a stack trace when the packages are missing, instead of reporting "unavailable".
//
// Diagrams are found with marked's own lexer, the same library and version the dashboard uses
// to draw them (ui/src/markdown.js), so the two cannot disagree about what counts as a diagram.
// A hand-written fence pattern did disagree: it missed ~~~ fences, "Mermaid", longer fences and
// fences inside blockquotes or lists, all of which the dashboard draws, so those diagrams were
// never syntax-checked, and it accepted an indented block that the dashboard shows as code.
export function extractMermaidBlocks(markdown, Lexer) {
  const text = markdown.replace(/\r\n?/g, "\n");
  const blocks = [];

  // `offset` is where this token's raw text starts in the document. Nested tokens carry no
  // absolute position, so each child is located by searching for its raw text from its parent's
  // start, which is exact because a child's raw text always appears inside its parent's.
  const walk = (tokens, offset) => {
    let cursor = offset;
    for (const token of tokens) {
      const found = text.indexOf(token.raw, cursor);
      const start = found < 0 ? cursor : found;
      if (token.type === "code" && (token.lang || "").trim().toLowerCase() === "mermaid") {
        blocks.push({ line: lineOf(text, start), source: token.text });
      }
      walk(childTokens(token), start);
      cursor = start + token.raw.length;
    }
  };

  walk(Lexer.lex(text, { gfm: true }), 0);
  return blocks;
}

function childTokens(token) {
  if (token.type === "list") return token.items ?? [];
  return token.tokens ?? [];
}

function lineOf(text, offset) {
  let line = 1;
  for (let index = 0; index < offset && index < text.length; index++) if (text[index] === "\n") line++;
  return line;
}

// Resolves the installed packages, or reports "unavailable" and exits.
function loadPackages() {
  const here = dirname(fileURLToPath(import.meta.url));
  const require = createRequire(join(here, "package.json"));
  try {
    return {
      JSDOM: require("jsdom").JSDOM,
      bundlePath: require.resolve("mermaid/dist/mermaid.min.js"),
      // marked is ESM-only from v16, so it is loaded with import() once resolved.
      markedPath: require.resolve("marked"),
    };
  } catch {
    reportUnavailable(`validator packages are not installed: run npm install in ${here}`);
  }
}

async function loadMermaid({ JSDOM, bundlePath }) {
  let window;
  try {
    ({ window } = new JSDOM("<!doctype html><html><body></body></html>", {
      runScripts: "dangerously",
      pretendToBeVisual: true,
    }));
    const script = window.document.createElement("script");
    script.textContent = readFileSync(bundlePath, "utf8");
    window.document.body.appendChild(script);
  } catch (error) {
    reportUnavailable(`could not start mermaid under jsdom: ${error.message}`);
  }
  if (typeof window.mermaid?.parse !== "function") {
    reportUnavailable("the mermaid bundle did not expose parse()");
  }
  window.mermaid.initialize({ startOnLoad: false });
  return window.mermaid;
}

async function main(paths) {
  const packages = loadPackages();
  const { Lexer } = await import(pathToFileURL(packages.markedPath).href);
  const files = paths.map((path) => ({ path, blocks: extractMermaidBlocks(readFileSync(path, "utf8"), Lexer) }));
  const hasDiagrams = files.some((file) => file.blocks.length > 0);
  // Nothing to parse: skip starting jsdom and mermaid, the expensive part.
  const mermaid = hasDiagrams ? await loadMermaid(packages) : null;

  const diagrams = [];
  for (const { path, blocks } of files) {
    for (const [position, block] of blocks.entries()) {
      const entry = { file: path, index: position + 1, line: block.line, valid: true };
      try {
        await mermaid.parse(block.source);
      } catch (error) {
        entry.valid = false;
        entry.error = String(error.message ?? error).split("\n").slice(0, 4).join("\n");
      }
      diagrams.push(entry);
    }
  }
  process.stdout.write(JSON.stringify({ diagrams }) + "\n");
}

// Run only when executed directly, so tests can import extractMermaidBlocks. Real paths are
// compared because Node resolves symlinks in import.meta.url but not in argv[1]: on macOS a
// temp or repository path under /var is really /private/var, and a plain string comparison
// would silently skip main() and exit 0 with no output.
function isRunDirectly() {
  try {
    return realpathSync(fileURLToPath(import.meta.url)) === realpathSync(process.argv[1]);
  } catch {
    // argv[1] is not a file (for example `node -e` or an importing test harness), so this
    // module was imported rather than executed.
    return false;
  }
}

if (isRunDirectly()) {
  await main(process.argv.slice(2));
}
