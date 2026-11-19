import { describe, expect, it } from "vitest";
import {
  STAGES,
  canAbandon,
  gateVerdict,
  githubIssueLink,
  groupByRepository,
  groupByStage,
  groupScopes,
  initialFile,
  scopeOf,
  isWaitingOnHuman,
  orderFiles,
  repositoryName,
  reviewChips,
} from "./jobs.js";

describe("pipeline stages", () => {
  it("lists every stage the board can produce, in pipeline order", () => {
    // Mirrors PIPELINE_STAGES in factory_board.py; a stage missing here would hide jobs.
    expect(STAGES.map(([key]) => key)).toEqual([
      "spec", "spec-review", "build", "test-audit", "review", "stride-review",
      "quality-gate", "approver", "needs-human", "abandoned",
    ]);
  });

  it("flags the two stages that wait on a person", () => {
    expect(isWaitingOnHuman({ stage: "spec-review" })).toBe(true);
    expect(isWaitingOnHuman({ stage: "needs-human" })).toBe(true);
    expect(isWaitingOnHuman({ stage: "build" })).toBe(false);
  });
});

describe("groupByStage", () => {
  it("places jobs in their stage column and keeps unknown stages visible", () => {
    const jobs = [{ id: "1", stage: "build" }, { id: "2", stage: "needs-human" }, { id: "3", stage: "future-stage" }];
    const columns = groupByStage(jobs);
    expect(columns.find((column) => column.key === "build").jobs.map((job) => job.id)).toEqual(["1"]);
    expect(columns.find((column) => column.key === "needs-human").jobs.map((job) => job.id)).toEqual(["2"]);
    // A stage added on the Python side must never silently drop a job from the dashboard.
    const unknown = columns.find((column) => column.key === "unknown");
    expect(unknown.jobs.map((job) => job.id)).toEqual(["3"]);
  });

  it("omits the unknown column when every stage is known", () => {
    expect(groupByStage([{ id: "1", stage: "build" }]).some((column) => column.key === "unknown")).toBe(false);
  });
});

describe("groupByRepository", () => {
  it("groups by repository name, sorted, with a fallback name", () => {
    const groups = groupByRepository([
      { id: "1", repository: "zeta" }, { id: "2", repository: "alpha" }, { id: "3" }, { id: "4", repository: "alpha" },
    ]);
    // Alphabetical regardless of case; the fallback group has no reason to sort first.
    expect(groups.map(([name]) => name)).toEqual(["alpha", "Unknown", "zeta"]);
    expect(groups.find(([name]) => name === "alpha")[1].map((job) => job.id)).toEqual(["2", "4"]);
  });
});

describe("reviewChips", () => {
  it("shows pending for a reviewer that has not reported yet", () => {
    const chips = reviewChips({ security: "PASS" });
    expect(chips.find((chip) => chip.name === "security").verdict).toBe("PASS");
    expect(chips.find((chip) => chip.name === "ux").verdict).toBe("pending");
  });

  it("hides the architecture chip for rounds recorded before that reviewer existed", () => {
    const names = reviewChips({ security: "PASS", ux: "N/A", ui: "N/A", code: "PASS" }).map((chip) => chip.name);
    expect(names).not.toContain("architecture");
  });

  it("shows the architecture chip once it is recorded", () => {
    const names = reviewChips({ security: "PASS", architecture: "pending" }).map((chip) => chip.name);
    expect(names).toContain("architecture");
  });

  it("returns nothing when a job has no reviews yet", () => {
    expect(reviewChips({})).toEqual([]);
    expect(reviewChips(undefined)).toEqual([]);
  });
});

describe("gateVerdict", () => {
  it("maps gate states onto review verdict colours", () => {
    expect(gateVerdict("pass")).toBe("PASS");
    expect(gateVerdict("warn")).toBe("PASS");
    expect(gateVerdict("fail")).toBe("CHANGES");
    expect(gateVerdict("fixing")).toBe("CHANGES");
    expect(gateVerdict("pending")).toBe("pending");
  });
});

describe("orderFiles and initialFile", () => {
  const files = ["build.md", "round-1/review-code.md", "decision.md", "spec.md", "handover.md", "feature.md"];

  it("puts the reading documents first and keeps the rest in their given order", () => {
    expect(orderFiles(files)).toEqual([
      "handover.md", "decision.md", "spec.md", "build.md", "round-1/review-code.md", "feature.md",
    ]);
  });

  it("opens a job that has a handover on the Overview, not on a raw file", () => {
    expect(initialFile(files)).toBe("overview");
  });

  it("opens a job without a handover on its first file", () => {
    // Jobs created before handover.md existed keep working.
    expect(initialFile(["spec.md", "build.md"])).toBe("spec.md");
  });

  it("copes with a job that has no files", () => {
    expect(initialFile([])).toBeNull();
  });
});

describe("groupScopes", () => {
  const files = [
    "handover.md", "decision.md", "spec.md", "build.md", "feature.md", "prompt.md",
    "round-10/test-audit.md", "round-2/review-code.md", "round-2/test-audit.md", "round-1/test-audit.md",
  ];

  it("puts root files in Documents and each round folder in its own scope, rounds in numeric order", () => {
    const scopes = groupScopes(files);
    expect(scopes.map((s) => s.label)).toEqual(["Documents", "Round 1", "Round 2", "Round 10"]);
    expect(scopes[0].files.map((f) => f.name)).toEqual(["decision.md", "spec.md", "build.md", "feature.md", "prompt.md"]);
  });

  it("strips the round prefix from the label but keeps the full path as the file key", () => {
    const round2 = groupScopes(files).find((s) => s.label === "Round 2");
    expect(round2.files).toEqual([
      { name: "round-2/review-code.md", label: "review-code.md" },
      { name: "round-2/test-audit.md", label: "test-audit.md" },
    ]);
  });

  it("leaves handover.md to the Overview tab", () => {
    expect(groupScopes(files).flatMap((s) => s.files).map((f) => f.name)).not.toContain("handover.md");
  });

  it("omits Documents when a job only has round files, and copes with no files", () => {
    expect(groupScopes(["round-1/test-audit.md"]).map((s) => s.label)).toEqual(["Round 1"]);
    expect(groupScopes([])).toEqual([]);
  });

  it("maps a file name back to its scope", () => {
    expect(scopeOf("round-3/review-ui.md")).toBe("scope:round-3");
    expect(scopeOf("spec.md")).toBe("scope:documents");
  });
});

describe("canAbandon", () => {
  it("allows every stage a job is still moving through", () => {
    for (const [stage] of STAGES.filter(([key]) => key !== "abandoned")) {
      expect(canAbandon({ stage }), stage).toBe(true);
    }
  });

  it("refuses a job that is already closed, which is also what the Archive tab holds", () => {
    expect(canAbandon({ stage: "abandoned" })).toBe(false);
  });

  it("copes with no job", () => {
    expect(canAbandon(null)).toBe(false);
  });
});

describe("githubIssueLink", () => {
  it("labels a canonical issue URL as owner/repo#number", () => {
    const url = "https://github.com/anaconda/engineering-guard/issues/123";
    expect(githubIssueLink({ issue_url: url })).toEqual({
      href: url,
      label: "anaconda/engineering-guard#123",
      repo: "anaconda/engineering-guard",
      number: "#123",
    });
  });

  it("returns null when the job has no issue", () => {
    expect(githubIssueLink({})).toBeNull();
    expect(githubIssueLink({ issue_url: null })).toBeNull();
    expect(githubIssueLink({ issue_url: "" })).toBeNull();
    expect(githubIssueLink(undefined)).toBeNull();
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,x",
    "http://github.com/o/r/issues/1",
    "https://evil.example/o/r/issues/1",
    "https://github.com.evil.example/o/r/issues/1",
    "https://github.com@evil.example/o/r/issues/1",
    "https://www.github.com/o/r/issues/1",
    "https://github.com/o/r/pull/1",
    "https://github.com/o/r/issues/",
    "https://github.com/o/r/issues/0",
    "https://github.com/o/r/issues/1/",
    "https://github.com/o/r/issues/1#issuecomment-2",
    "https://github.com/o/r/issues/1?x=1",
    "https://github.com/o/../issues/1",
    " https://github.com/o/r/issues/1",
    "https://github.com/o/r/issues/1\n",
    "https://github.com/o/r/issues/1 x",
  ])("rejects %j", (url) => {
    expect(githubIssueLink({ issue_url: url })).toBeNull();
  });

  it.each([42, {}, ["https://github.com/o/r/issues/1"], true])("rejects the non-string %j", (value) => {
    expect(githubIssueLink({ issue_url: value })).toBeNull();
  });
});

describe("repositoryName", () => {
  it("prefers the repository the board recorded", () => {
    expect(repositoryName({ repository: "engineering-guard", repo_path: "/work/other" })).toBe("engineering-guard");
  });

  it("falls back to the last segment of repo_path, then worktree_path", () => {
    expect(repositoryName({ repository: "", repo_path: "/Users/me/code/my-repo/" })).toBe("my-repo");
    expect(repositoryName({ repo_path: "C:\\code\\win-repo" })).toBe("win-repo");
    expect(repositoryName({ worktree_path: "/tmp/wt/feature-tree" })).toBe("feature-tree");
  });

  it("returns null when nothing names the repository", () => {
    expect(repositoryName({})).toBeNull();
    expect(repositoryName({ repository: "  ", repo_path: "/", worktree_path: null })).toBeNull();
    expect(repositoryName({ repository: 5, repo_path: 7 })).toBeNull();
    expect(repositoryName(null)).toBeNull();
  });
});
