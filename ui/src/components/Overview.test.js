import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import Overview from "./Overview.svelte";

// The shared store reads the theme at import time; jsdom has no matchMedia.
vi.hoisted(() => { window.matchMedia = () => ({ matches: false }); });

let component;

function render(job) {
  const target = document.createElement("div");
  document.body.append(target);
  component = mount(Overview, { target, props: { job, handover: "", decision: "" } });
  flushSync();
  return target;
}

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.replaceChildren();
});

describe("Overview stage label", () => {
  const label = (job) => render(job).querySelector(".round-label").textContent.trim();
  const base = { id: "001-x", title: "Do x" };

  it("prints Complete for a complete job and for an old archived record", () => {
    expect(label({ ...base, stage: "complete" })).toBe("Complete");
    unmount(component);
    document.body.replaceChildren();
    expect(label({ ...base, stage: "abandoned", history: [{ archived_from: "needs-human", reason: "approved" }] })).toBe("Complete");
  });

  it("prints Abandoned for any other abandoned job and keeps the round", () => {
    expect(label({ ...base, stage: "abandoned", round: 2, history: [{ abandoned_from: "build", reason: "x" }] })).toBe("Abandoned · round 2");
  });
});
