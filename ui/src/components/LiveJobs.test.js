import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import LiveJobs from "./LiveJobs.svelte";

// The shared store reads the theme at import time; jsdom has no matchMedia.
vi.hoisted(() => { window.matchMedia = () => ({ matches: false }); });

let component;

function render(jobs) {
  const target = document.createElement("div");
  document.body.append(target);
  component = mount(LiveJobs, { target, props: { jobs, onopen: vi.fn() } });
  flushSync();
  return target;
}

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.replaceChildren();
});

const job = (id, stage, extra = {}) => ({ id, title: `Job ${id}`, stage, repo_path: "/work/a", ...extra });

describe("LiveJobs strip", () => {
  it("lists only jobs that are still open", () => {
    const target = render([
      job("001-build", "build"),
      job("002-done", "complete"),
      job("003-stopped", "abandoned"),
      job("004-legacy", "abandoned", { history: [{ archived_from: "needs-human", reason: "approved" }] }),
    ]);
    const ids = [...target.querySelectorAll(".live-job-id")].map((node) => node.textContent);
    expect(ids).toEqual(["001-build"]);
    expect(target.querySelector(".live-count").textContent).toBe("1");
  });

  it("shows the empty message when every job is closed", () => {
    const target = render([job("001-done", "complete")]);
    expect(target.querySelector(".live-job")).toBeNull();
    expect(target.querySelector(".live-empty")).not.toBeNull();
  });
});
