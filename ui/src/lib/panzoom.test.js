import { describe, expect, it } from "vitest";
import {
  BUTTON_STEP, IDENTITY, MAX_SCALE, MIN_SCALE,
  constrain, fitView, panBy, wheelFactor, zoomAt, zoomAtCentre,
} from "./panzoom.js";

const viewport = { width: 800, height: 400 };

// Where a point of the diagram (in its own coordinates) lands on screen for a given view.
const onScreen = (view, point) => ({ x: point.x * view.scale + view.x, y: point.y * view.scale + view.y });

describe("zoomAt", () => {
  it("keeps the point under the cursor fixed on screen", () => {
    const view = { scale: 1.5, x: 40, y: -20 };
    const cursor = { x: 300, y: 150 };
    // The diagram point currently under the cursor.
    const underCursor = { x: (cursor.x - view.x) / view.scale, y: (cursor.y - view.y) / view.scale };
    const zoomed = zoomAt(view, 2, cursor.x, cursor.y);
    const after = onScreen(zoomed, underCursor);
    expect(after.x).toBeCloseTo(cursor.x, 6);
    expect(after.y).toBeCloseTo(cursor.y, 6);
    expect(zoomed.scale).toBeCloseTo(3, 6);
  });

  it("zooms out around the cursor too", () => {
    const view = { scale: 2, x: 10, y: 10 };
    const underCursor = { x: (500 - view.x) / view.scale, y: (200 - view.y) / view.scale };
    const after = onScreen(zoomAt(view, 0.5, 500, 200), underCursor);
    expect(after.x).toBeCloseTo(500, 6);
    expect(after.y).toBeCloseTo(200, 6);
  });

  it("clamps to the scale limits", () => {
    expect(zoomAt(IDENTITY, 1000, 0, 0).scale).toBe(MAX_SCALE);
    expect(zoomAt(IDENTITY, 0.0001, 0, 0).scale).toBe(MIN_SCALE);
  });

  it("does not drift when already at a limit", () => {
    // Asking for more zoom at the maximum must not move the diagram, or it would creep away.
    const atMax = { scale: MAX_SCALE, x: 120, y: 80 };
    expect(zoomAt(atMax, 2, 400, 200)).toEqual(atMax);
  });
});

describe("zoomAtCentre", () => {
  it("keeps the viewport centre fixed", () => {
    const view = { scale: 1, x: 30, y: 10 };
    const centreOnDiagram = { x: (400 - view.x) / view.scale, y: (200 - view.y) / view.scale };
    const after = onScreen(zoomAtCentre(view, BUTTON_STEP, viewport), centreOnDiagram);
    expect(after.x).toBeCloseTo(400, 6);
    expect(after.y).toBeCloseTo(200, 6);
  });
});

describe("panBy", () => {
  it("moves the view without changing the scale", () => {
    expect(panBy({ scale: 2, x: 5, y: 6 }, 10, -4)).toEqual({ scale: 2, x: 15, y: 2 });
  });

  it("returns a new object", () => {
    const view = { scale: 1, x: 0, y: 0 };
    expect(panBy(view, 1, 1)).not.toBe(view);
    expect(view).toEqual({ scale: 1, x: 0, y: 0 });
  });
});

describe("fitView", () => {
  it("shrinks a diagram larger than the viewport so all of it shows, centred", () => {
    const content = { width: 1600, height: 400 };
    const view = fitView(content, viewport, 0);
    expect(view.scale).toBeCloseTo(0.5, 6);
    expect(view.x).toBeCloseTo(0, 6);
    expect(view.y).toBeCloseTo((400 - 400 * 0.5) / 2, 6);
  });

  it("never enlarges a small diagram past actual size", () => {
    const view = fitView({ width: 100, height: 50 }, viewport);
    expect(view.scale).toBe(1);
    expect(view.x).toBeCloseTo((800 - 100) / 2, 6);
  });

  it("leaves room for the padding", () => {
    const view = fitView({ width: 800, height: 400 }, viewport, 20);
    expect(view.scale).toBeLessThan(1);
    expect(800 * view.scale).toBeLessThanOrEqual(800 - 40 + 1e-9);
  });

  it("falls back to the identity view when a size is not known yet", () => {
    // A diagram measured before layout has zero size; fitting it would give NaN.
    expect(fitView({ width: 0, height: 0 }, viewport)).toEqual(IDENTITY);
    expect(fitView({ width: 100, height: 100 }, { width: 0, height: 0 })).toEqual(IDENTITY);
  });

  it("never returns NaN or Infinity", () => {
    for (const content of [{ width: 1e9, height: 1 }, { width: 1, height: 1e9 }, { width: 1, height: 1 }]) {
      const view = fitView(content, viewport);
      expect(Number.isFinite(view.scale) && Number.isFinite(view.x) && Number.isFinite(view.y)).toBe(true);
    }
  });
});

describe("constrain", () => {
  const content = { width: 400, height: 200 };

  it("leaves a view that is comfortably on screen alone", () => {
    const view = { scale: 1, x: 100, y: 50 };
    expect(constrain(view, content, viewport)).toEqual(view);
  });

  it("stops the diagram being dragged out of the viewport on every side", () => {
    const keep = 48;
    const far = constrain({ scale: 1, x: 5000, y: 5000 }, content, viewport, keep);
    expect(far.x).toBe(viewport.width - keep);
    expect(far.y).toBe(viewport.height - keep);
    const back = constrain({ scale: 1, x: -5000, y: -5000 }, content, viewport, keep);
    expect(back.x).toBe(keep - content.width);
    expect(back.y).toBe(keep - content.height);
  });

  it("accounts for the scale when deciding how much is still visible", () => {
    const view = constrain({ scale: 2, x: -5000, y: 0 }, content, viewport, 48);
    expect(view.x).toBe(48 - content.width * 2);
  });
});

describe("wheelFactor", () => {
  it("zooms in when scrolling up and out when scrolling down", () => {
    expect(wheelFactor({ deltaY: -100, deltaMode: 0 })).toBeGreaterThan(1);
    expect(wheelFactor({ deltaY: 100, deltaMode: 0 })).toBeLessThan(1);
    expect(wheelFactor({ deltaY: 0, deltaMode: 0 })).toBe(1);
  });

  it("treats opposite deltas as exact inverses", () => {
    const up = wheelFactor({ deltaY: -80, deltaMode: 0 });
    const down = wheelFactor({ deltaY: 80, deltaMode: 0 });
    expect(up * down).toBeCloseTo(1, 10);
  });

  it("scales line and page deltas to pixels", () => {
    const pixels = wheelFactor({ deltaY: -48, deltaMode: 0 });
    expect(wheelFactor({ deltaY: -3, deltaMode: 1 })).toBeCloseTo(pixels, 10); // 3 lines x 16px
    expect(wheelFactor({ deltaY: -1, deltaMode: 2 })).toBeGreaterThan(pixels);
  });

  it("gives a small, smooth step for a trackpad pinch", () => {
    const pinch = wheelFactor({ deltaY: -2, deltaMode: 0, ctrlKey: true });
    expect(pinch).toBeGreaterThan(1);
    expect(pinch).toBeLessThan(1.02);
  });
});
