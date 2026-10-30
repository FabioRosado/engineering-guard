// Pan and zoom maths for a diagram, kept free of the DOM so it can be tested directly.
//
// A view is { scale, x, y }: the diagram is scaled about its top-left corner and then translated
// by (x, y) pixels. Every function returns a new view rather than mutating the old one.

export const MIN_SCALE = 0.25;
export const MAX_SCALE = 6;
export const BUTTON_STEP = 1.25;

export const IDENTITY = Object.freeze({ scale: 1, x: 0, y: 0 });

function clampScale(scale) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

// Zoom by `factor` while keeping the point under the cursor (px, py, relative to the viewport's
// top-left) fixed on screen. Without this the diagram would slide away from the pointer.
export function zoomAt(view, factor, px, py) {
  const scale = clampScale(view.scale * factor);
  const applied = scale / view.scale;
  return {
    scale,
    x: px - (px - view.x) * applied,
    y: py - (py - view.y) * applied,
  };
}

export function panBy(view, dx, dy) {
  return { ...view, x: view.x + dx, y: view.y + dy };
}

// Zoom about the viewport's centre, for buttons and the keyboard, which have no pointer position.
export function zoomAtCentre(view, factor, viewport) {
  return zoomAt(view, factor, viewport.width / 2, viewport.height / 2);
}

// The view that shows the whole diagram, centred, never enlarged past 1:1 so a small diagram is
// not blown up into a blurry billboard.
export function fitView(content, viewport, padding = 16) {
  if (!content.width || !content.height || !viewport.width || !viewport.height) return IDENTITY;
  const available = { width: Math.max(1, viewport.width - padding * 2), height: Math.max(1, viewport.height - padding * 2) };
  const scale = clampScale(Math.min(1, available.width / content.width, available.height / content.height));
  return {
    scale,
    x: (viewport.width - content.width * scale) / 2,
    y: (viewport.height - content.height * scale) / 2,
  };
}

// Keep some of the diagram on screen so it cannot be dragged out of reach and lost. At least
// `keep` pixels of it must stay inside the viewport on each axis.
export function constrain(view, content, viewport, keep = 48) {
  const width = content.width * view.scale;
  const height = content.height * view.scale;
  const clamp = (value, size, limit) => Math.min(limit - keep, Math.max(keep - size, value));
  return { ...view, x: clamp(view.x, width, viewport.width), y: clamp(view.y, height, viewport.height) };
}

// Wheel deltas arrive in pixels, lines or pages depending on the device; normalise to pixels.
export function wheelDeltaPixels(event) {
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1;
  return event.deltaY * unit;
}

// Smooth, direction-correct zoom factor for a wheel event. A pinch gesture on a trackpad arrives
// as a ctrlKey wheel event with small deltas, so the factor is exponential in the delta.
export function wheelFactor(event) {
  return Math.exp(-wheelDeltaPixels(event) * 0.0025);
}
