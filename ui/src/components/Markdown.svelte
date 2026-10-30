<script>
  import { attachDiagramViewer } from "../lib/diagram-viewer.js";
  import { renderDiagram } from "../lib/diagrams.js";
  import { decodeDiagram, renderMarkdown } from "../lib/markdown.js";
  import { app } from "../lib/store.svelte.js";

  let { source } = $props();

  // Re-derived only when the text changes. Polling hands the same text back every two seconds,
  // and a new string identity must not rebuild the diagrams or they would flicker.
  let html = $derived(renderMarkdown(source));
  let container = $state();

  // One viewer per placeholder, kept across redraws so a theme change swaps the picture without
  // resetting the reader's zoom and position. A WeakMap drops them with their placeholders.
  const viewers = new WeakMap();
  let openDialogs = [];

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
      let viewer = viewers.get(placeholder);
      if (!viewer) {
        viewer = attachDiagramViewer(placeholder, {
          onexpand: () => expand(decodeDiagram(placeholder.getAttribute("data-mermaid"))),
        });
        viewers.set(placeholder, viewer);
      }
      // Mermaid's own output at securityLevel "strict": its labels are already escaped.
      viewer.setSvg(result.svg);
    } else {
      viewers.get(placeholder)?.destroy();
      viewers.delete(placeholder);
      showError(placeholder, result.error, diagramSource);
    }
  }

  // The same diagram in a large dialog, drawn in the current theme with its own pan and zoom.
  async function expand(diagramSource) {
    const dialog = document.createElement("dialog");
    dialog.className = "diagram-dialog";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "diagram-dialog-close";
    close.textContent = "Close";
    close.addEventListener("click", () => dialog.close());
    const holder = document.createElement("div");
    holder.className = "diagram diagram-expanded";
    dialog.append(close, holder);
    document.body.append(dialog);
    openDialogs.push(dialog);

    const viewer = attachDiagramViewer(holder);
    dialog.addEventListener("close", () => {
      viewer.destroy();
      dialog.remove();
      openDialogs = openDialogs.filter((open) => open !== dialog);
    });
    dialog.showModal();
    const result = await renderDiagram(diagramSource, app.theme);
    if (result.svg) viewer.setSvg(result.svg);
    else showError(holder, result.error, diagramSource);
  }

  // A dialog is appended to the body, outside this component, so it must be closed with it.
  $effect(() => () => {
    for (const dialog of openDialogs) dialog.close();
  });

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
