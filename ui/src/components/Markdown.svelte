<script>
  import { renderDiagram } from "../lib/diagrams.js";
  import { decodeDiagram, renderMarkdown } from "../lib/markdown.js";
  import { app } from "../lib/store.svelte.js";

  let { source } = $props();

  // Re-derived only when the text changes. Polling hands the same text back every two seconds,
  // and a new string identity must not rebuild the diagrams or they would flicker.
  let html = $derived(renderMarkdown(source));
  let container = $state();

  // Diagrams are drawn after the HTML is in place. A run counter discards a render that finished
  // after a newer one started (a quick theme toggle, or a job that changed while mermaid loaded).
  let latestRun = 0;

  $effect(() => {
    html; // re-run when the content changes
    const theme = app.theme; // and when the theme changes
    const root = container;
    if (!root) return;
    const run = ++latestRun;
    for (const placeholder of root.querySelectorAll("[data-mermaid]")) {
      drawDiagram(placeholder, theme, run);
    }
  });

  async function drawDiagram(placeholder, theme, run) {
    let diagramSource;
    try {
      diagramSource = decodeDiagram(placeholder.getAttribute("data-mermaid"));
    } catch {
      showError(placeholder, "The diagram could not be read.", "");
      return;
    }
    if (!placeholder.firstChild) {
      placeholder.classList.add("diagram-pending");
      placeholder.textContent = "Rendering diagram…";
    }
    const result = await renderDiagram(diagramSource, theme);
    if (run !== latestRun || !placeholder.isConnected) return;
    placeholder.classList.remove("diagram-pending", "diagram-error");
    if (result.svg) {
      // Mermaid's own output at securityLevel "strict": its labels are already escaped.
      placeholder.innerHTML = result.svg;
    } else {
      showError(placeholder, result.error, diagramSource);
    }
  }

  // A failed diagram shows what went wrong and the source, never an empty gap. Built with DOM
  // calls and textContent so nothing in the error text or the source is read as markup.
  function showError(placeholder, message, diagramSource) {
    placeholder.classList.remove("diagram-pending");
    placeholder.classList.add("diagram-error");
    placeholder.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = "This diagram could not be drawn";
    const detail = document.createElement("pre");
    detail.textContent = message;
    placeholder.append(title, detail);
    if (diagramSource) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Show diagram source";
      const code = document.createElement("pre");
      code.textContent = diagramSource;
      details.append(summary, code);
      placeholder.append(details);
    }
  }
</script>

<div class="markdown" bind:this={container}>{@html html}</div>
