// Pure helpers over the job objects the central server returns. Kept free of Svelte so the
// rules that decide what a person sees (which column, which chips, which file opens first)
// can be tested directly.

// Mirrors PIPELINE_STAGES in .agents/skills/factory/scripts/factory_board.py.
export const STAGES = [
  ["spec", "Spec"],
  ["spec-review", "Spec Review"],
  ["build", "Build"],
  ["test-audit", "Test Audit"],
  ["review", "Review"],
  ["stride-review", "STRIDE"],
  ["quality-gate", "Quality Gate"],
  ["approver", "Approver"],
  ["needs-human", "Needs Human"],
  ["abandoned", "Abandoned"],
];

const HUMAN_STAGES = new Set(["spec-review", "needs-human"]);
export const REVIEWERS = ["security", "ux", "ui", "code", "architecture"];

export const OVERVIEW = "overview";
export const HANDOVER_FILE = "handover.md";

export function isWaitingOnHuman(job) {
  return HUMAN_STAGES.has(job.stage);
}

export function isHumanStage(stageKey) {
  return HUMAN_STAGES.has(stageKey);
}

export function groupByStage(jobs) {
  const columns = STAGES.map(([key, name]) => ({
    key,
    name,
    jobs: jobs.filter((job) => job.stage === key),
  }));
  const known = new Set(STAGES.map(([key]) => key));
  const unknown = jobs.filter((job) => !known.has(job.stage));
  if (unknown.length) columns.push({ key: "unknown", name: "Unknown Stage", jobs: unknown });
  return columns;
}

export function groupByRepository(jobs) {
  const byRepository = new Map();
  for (const job of jobs) {
    const name = job.repository || "Unknown";
    if (!byRepository.has(name)) byRepository.set(name, []);
    byRepository.get(name).push(job);
  }
  return [...byRepository.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export function reviewChips(reviews) {
  if (!reviews || Object.keys(reviews).length === 0) return [];
  const chips = [];
  for (const name of REVIEWERS) {
    // Rounds recorded before the architecture reviewer existed have no entry for it; a
    // "pending" chip on those finished rounds would be wrong.
    if (name === "architecture" && !(name in reviews)) continue;
    chips.push({ name, verdict: reviews[name] || "pending" });
  }
  return chips;
}

// The gate reports pass/warn/fail/fixing/pending; chips are coloured by the review verdict
// names, so map onto those instead of adding a second palette. A warn still passes the gate.
export function gateVerdict(status) {
  if (status === "pass" || status === "warn") return "PASS";
  if (status === "fail" || status === "fixing") return "CHANGES";
  return "pending";
}

// The documents a person reads at the human gates come first; everything else keeps the
// order the server gave (round folders sort naturally).
const READING_ORDER = [HANDOVER_FILE, "decision.md", "spec.md", "build.md"];

export function orderFiles(fileNames) {
  const first = READING_ORDER.filter((name) => fileNames.includes(name));
  return [...first, ...fileNames.filter((name) => !first.includes(name))];
}

// Jobs written before handover.md existed have no overview, so they open on a raw file.
export function initialFile(fileNames) {
  if (fileNames.includes(HANDOVER_FILE)) return OVERVIEW;
  return fileNames.length ? orderFiles(fileNames)[0] : null;
}
