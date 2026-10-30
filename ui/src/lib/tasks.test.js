import { describe, expect, it } from "vitest";
import { COLUMN_LABELS, columnsFor, formatDuration, jobForTask, promptPreview, statLines } from "./tasks.js";

describe("columnsFor", () => {
  // The backlog tasks arrive out of position order, as they do after a task is dragged upward.
  const tasks = [
    { id: 1, status: "ready", position: 3 },
    { id: 3, status: "backlog", position: 2 },
    { id: 2, status: "backlog", position: 1 },
  ];

  it("builds one column per status the server named, in that order", () => {
    const columns = columnsFor(tasks, ["backlog", "ready", "in-progress", "done"]);
    expect(columns.map((column) => column.key)).toEqual(["backlog", "ready", "in-progress", "done"]);
  });

  it("keeps each column in position order and leaves empty columns empty", () => {
    const columns = columnsFor(tasks, ["backlog", "ready", "in-progress", "done"]);
    expect(columns[0].tasks.map((task) => task.id)).toEqual([2, 3]);
    expect(columns[1].tasks.map((task) => task.id)).toEqual([1]);
    expect(columns[2].tasks).toEqual([]);
  });

  it("labels columns for people", () => {
    const [backlog, , inProgress] = columnsFor([], ["backlog", "ready", "in-progress", "done"]);
    expect(backlog.name).toBe(COLUMN_LABELS.backlog);
    expect(inProgress.name).toBe("In Progress");
  });

  it("does not hide a task whose status the UI does not know", () => {
    const columns = columnsFor([{ id: 9, status: "someday", position: 1 }], ["backlog"]);
    expect(columns.at(-1)).toMatchObject({ key: "unknown", tasks: [{ id: 9 }] });
  });

  it("does not depend on the server list being complete when there are no tasks", () => {
    expect(columnsFor([], [])).toEqual([]);
  });
});

describe("promptPreview", () => {
  it("collapses whitespace and shortens long prompts with an ellipsis", () => {
    const preview = promptPreview("first line\n\n   second   line " + "x".repeat(300), 40);
    expect(preview.length).toBeLessThanOrEqual(40);
    expect(preview.endsWith("…")).toBe(true);
    expect(preview).not.toMatch(/\s{2,}|\n/);
  });

  it("returns short prompts unchanged and an empty prompt as empty", () => {
    expect(promptPreview("short", 40)).toBe("short");
    expect(promptPreview("", 40)).toBe("");
    expect(promptPreview(undefined, 40)).toBe("");
  });
});

describe("jobForTask", () => {
  const jobs = [
    { id: "001-x", repo_path: "/a" },
    { id: "001-x", repo_path: "/b" },
  ];

  it("finds the linked job by repository and id, since ids repeat across repositories", () => {
    expect(jobForTask({ job_id: "001-x", repo_path: "/b" }, jobs)).toBe(jobs[1]);
  });

  it("returns null for an unlinked task, or a link to a job that is gone", () => {
    expect(jobForTask({ job_id: null, repo_path: null }, jobs)).toBeNull();
    expect(jobForTask({ job_id: "009-gone", repo_path: "/a" }, jobs)).toBeNull();
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "0s"],
    [45, "45s"],
    [60, "1m"],
    [125, "2m 5s"],
    [3600, "1h"],
    [3725, "1h 2m"],
    [90061, "1d 1h"],
  ])("formats %i seconds as %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });

  it("does not show negative or fractional time", () => {
    expect(formatDuration(-5)).toBe("0s");
    expect(formatDuration(59.9)).toBe("59s");
  });
});

describe("statLines", () => {
  const stats = {
    total_seconds: 5400,
    human_seconds: 3600,
    agent_seconds: 1800,
    rounds: 2,
    rebuilds: 1,
    agents: 9,
    finished: true,
    seconds_by_stage: { build: 1200, "spec-review": 3000, spec: 600 },
  };

  it("summarises totals, with the human wait separate from agent time", () => {
    const lines = Object.fromEntries(statLines(stats).summary.map(({ label, value }) => [label, value]));
    expect(lines["Total time"]).toBe("1h 30m");
    expect(lines["Waiting on you"]).toBe("1h");
    expect(lines["Factory working"]).toBe("30m");
    expect(lines["Build rounds"]).toBe("2");
    expect(lines["Rebuilds"]).toBe("1");
    expect(lines["Agents run"]).toBe("9");
  });

  it("lists stages in pipeline order with their share of the total, not in arrival order", () => {
    const stages = statLines(stats).stages;
    expect(stages.map((stage) => stage.stage)).toEqual(["spec", "spec-review", "build"]);
    expect(stages[2]).toMatchObject({ label: "Build", value: "20m" });
    expect(stages[1].share).toBeCloseTo(3000 / 5400);
  });

  it("says plainly that a running job is still counting", () => {
    expect(statLines({ ...stats, finished: false }).status).toMatch(/running/i);
    expect(statLines(stats).status).toMatch(/finished/i);
  });

  it("does not divide by zero for a job with no elapsed time", () => {
    const empty = { ...stats, total_seconds: 0, seconds_by_stage: { spec: 0 } };
    expect(statLines(empty).stages[0].share).toBe(0);
  });
});
