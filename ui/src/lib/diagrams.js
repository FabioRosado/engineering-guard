// Renders mermaid diagrams in the browser.
//
// Mermaid is loaded on first use, so pages without diagrams never pay for it. Diagram source is
// untrusted (an agent wrote it), so mermaid runs at securityLevel "strict": it escapes label
// HTML and disables click handlers. Each diagram renders on its own, and a failure is returned
// as a result for that diagram instead of being thrown, so one bad diagram cannot blank the page.

let mermaidPromise = null;
let configuredTheme = null;
let renderCounter = 0;

function loadMermaid() {
  mermaidPromise ??= import("mermaid").then((module) => module.default);
  return mermaidPromise;
}

async function configure(theme) {
  const mermaid = await loadMermaid();
  if (configuredTheme !== theme) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: theme === "dark" ? "dark" : "neutral",
      fontFamily: "inherit",
    });
    configuredTheme = theme;
  }
  return mermaid;
}

// Resolves to { svg } or { error }; never rejects.
export async function renderDiagram(source, theme) {
  try {
    const mermaid = await configure(theme);
    // A fresh id per render: mermaid keeps a temporary element under this id in the document.
    const { svg } = await mermaid.render(`diagram-${++renderCounter}`, source);
    return { svg };
  } catch (error) {
    // Mermaid leaves a half-built error element behind on failure; remove it.
    document.querySelector(`#ddiagram-${renderCounter}`)?.remove();
    return { error: firstLines(error?.message ?? String(error), 4) };
  }
}

function firstLines(text, count) {
  return text.split("\n").slice(0, count).join("\n");
}
