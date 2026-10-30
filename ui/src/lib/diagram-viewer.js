// Gives a rendered diagram pan and zoom controls.
//
// The diagram placeholders are created by {@html}, outside Svelte's control, and a theme change
// redraws the SVG inside them. So the controls are a plain DOM controller attached to the
// placeholder: it owns the toolbar and the view state, and `setSvg` swaps only the picture, which
// means a redraw never resets what the reader was looking at.

import { BUTTON_STEP, IDENTITY, constrain, fitView, panBy, wheelFactor, zoomAt, zoomAtCentre } from "./panzoom.js";

const PAN_STEP = 60;
const DRAG_THRESHOLD = 3;

function button(label, title, onclick) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "diagram-button";
  element.textContent = label;
  element.title = title;
  element.setAttribute("aria-label", title);
  element.addEventListener("click", onclick);
  return element;
}

// Returns { setSvg(markup), destroy() }.
export function attachDiagramViewer(placeholder, { onexpand } = {}) {
  placeholder.replaceChildren();
  placeholder.classList.add("diagram-interactive");

  const viewport = document.createElement("div");
  viewport.className = "diagram-viewport";
  viewport.tabIndex = 0;
  viewport.setAttribute("role", "group");
  viewport.setAttribute("aria-label", "Diagram. Drag to move; Ctrl or Command with the wheel, or plus and minus, to zoom; 0 to fit.");

  const stage = document.createElement("div");
  stage.className = "diagram-stage";
  viewport.append(stage);

  const label = document.createElement("span");
  label.className = "diagram-scale";
  label.setAttribute("aria-live", "off");
  label.textContent = "100%";

  let view = IDENTITY;
  let hasBeenFitted = false;
  // Until the reader moves or zooms, the diagram follows the box as it resizes; Fit hands control back.
  let userHasMoved = false;

  const sizes = () => ({
    viewport: { width: viewport.clientWidth, height: viewport.clientHeight },
    // The SVG's own size, which the stage is laid out at before any scaling.
    content: { width: stage.offsetWidth, height: stage.offsetHeight },
  });

  function apply(next) {
    const { viewport: box, content } = sizes();
    view = box.width && content.width ? constrain(next, content, box) : next;
    stage.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
    label.textContent = `${Math.round(view.scale * 100)}%`;
  }

  const fit = () => {
    const { viewport: box, content } = sizes();
    apply(fitView(content, box));
  };
  const fitAndFollow = () => {
    userHasMoved = false;
    fit();
  };
  const zoomBy = (factor) => {
    userHasMoved = true;
    apply(zoomAtCentre(view, factor, sizes().viewport));
  };

  const toolbar = document.createElement("div");
  toolbar.className = "diagram-toolbar";
  toolbar.append(
    button("−", "Zoom out", () => zoomBy(1 / BUTTON_STEP)),
    label,
    button("+", "Zoom in", () => zoomBy(BUTTON_STEP)),
    button("Fit", "Fit the whole diagram", fitAndFollow),
    button("1:1", "Actual size", () => {
      userHasMoved = true;
      apply({ scale: 1, x: 0, y: 0 });
    }),
  );
  if (onexpand) toolbar.append(button("Expand", "Open the diagram larger", () => onexpand()));

  placeholder.append(toolbar, viewport);

  // Ctrl or Command with the wheel (also how a trackpad pinch arrives) zooms. A plain wheel is
  // left alone so scrolling the document past a diagram never gets trapped inside it. The
  // listener is added by hand because it must be non-passive to be allowed to preventDefault.
  const onWheel = (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const rect = viewport.getBoundingClientRect();
    apply(zoomAt(view, wheelFactor(event), event.clientX - rect.left, event.clientY - rect.top));
  };
  viewport.addEventListener("wheel", onWheel, { passive: false });

  // Dragging pans. Pointer capture keeps the drag alive if the pointer leaves the box.
  let drag = null;
  viewport.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
    viewport.setPointerCapture(event.pointerId);
  });
  viewport.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    drag.moved = true;
    viewport.classList.add("dragging");
    drag.x = event.clientX;
    drag.y = event.clientY;
    apply(panBy(view, dx, dy));
  });
  const endDrag = (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
    drag = null;
    viewport.classList.remove("dragging");
  };
  viewport.addEventListener("pointerup", endDrag);
  viewport.addEventListener("pointercancel", endDrag);
  viewport.addEventListener("dblclick", fitAndFollow);

  viewport.addEventListener("keydown", (event) => {
    const handlers = {
      "+": () => zoomBy(BUTTON_STEP),
      "=": () => zoomBy(BUTTON_STEP),
      "-": () => zoomBy(1 / BUTTON_STEP),
      "_": () => zoomBy(1 / BUTTON_STEP),
      "0": fitAndFollow,
      ArrowLeft: () => apply(panBy(view, PAN_STEP, 0)),
      ArrowRight: () => apply(panBy(view, -PAN_STEP, 0)),
      ArrowUp: () => apply(panBy(view, 0, PAN_STEP)),
      ArrowDown: () => apply(panBy(view, 0, -PAN_STEP)),
    };
    const handler = handlers[event.key];
    if (!handler || event.ctrlKey || event.metaKey || event.altKey) return;
    event.preventDefault();
    handler();
  });

  // Keep the whole diagram in view as the box resizes (window, dialog, sidebar) until the reader
  // has taken control; after that their view is theirs. Registered after the handlers above, so
  // Fit (which clears the flag) runs first and then this does not set it again.
  const markMoved = (event) => {
    if (event.type === "wheel" && !event.ctrlKey && !event.metaKey) return;
    userHasMoved = true;
  };
  viewport.addEventListener("pointerdown", markMoved);
  viewport.addEventListener("wheel", markMoved, { passive: true });
  viewport.addEventListener("keydown", markMoved);
  const resizeObserver = typeof ResizeObserver === "function"
    ? new ResizeObserver(() => { if (hasBeenFitted && !userHasMoved) fit(); })
    : null;
  resizeObserver?.observe(viewport);

  return {
    // Replace the picture, keeping the reader's view. The first picture is fitted to the box.
    setSvg(markup) {
      stage.innerHTML = markup;
      const svg = stage.querySelector("svg");
      if (svg) {
        // Mermaid sizes the SVG with max-width; a fixed size makes the layout size predictable
        // for the maths and lets the transform do all the scaling.
        const box = svg.viewBox?.baseVal;
        if (box && box.width) {
          svg.setAttribute("width", String(box.width));
          svg.setAttribute("height", String(box.height));
        }
        svg.style.maxWidth = "none";
      }
      if (!hasBeenFitted) {
        hasBeenFitted = true;
        fit();
      } else {
        apply(view);
      }
    },
    destroy() {
      resizeObserver?.disconnect();
      viewport.removeEventListener("wheel", onWheel);
    },
    get view() { return view; },
  };
}
