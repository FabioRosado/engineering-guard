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
// Tabs in the job viewer that show dashboard data rather than a job file. The leading colon cannot
// occur in a file name, so they can never collide with one.
export const STATS = ":stats";
export const NOTES = ":notes";
export const HANDOVER_FILE = "handover.md";

export function isWaitingOnHuman(job) {
  return HUMAN_STAGES.has(job.stage);
}

// Mirrors the board's TERMINAL_STAGES: a job in one of these is already closed, so the board
// refuses to abandon it again.
const CLOSED_STAGES = new Set(["abandoned"]);

// Any job still moving through the pipeline can be abandoned, whether it is building, in review
// or waiting on a human. Archived jobs (which share the closed stage) cannot.
export function canAbandon(job) {
  return Boolean(job) && !CLOSED_STAGES.has(job.stage);
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

// The viewer's top bar switches between scopes; the sidebar lists only the files inside the
// current one. Root files (spec, build, decision...) form "Documents"; each round-N/ folder
// becomes its own scope so a job with many rounds stays navigable.
export const DOCUMENTS = "scope:documents";
const ROUND_FILE = /^round-(\d+)\/(.+)$/;

export const roundScope = (n) => `scope:round-${n}`;

export function scopeOf(fileName) {
  const match = ROUND_FILE.exec(fileName);
  return match ? roundScope(Number(match[1])) : DOCUMENTS;
}

// Returns file scopes in display order: Documents first, then rounds numerically. Each file keeps
// its full path as `name` (the key into job.files) and gets a short `label` for the sidebar.
// Handover.md is excluded because the Overview tab already renders it.
export function groupScopes(fileNames) {
  const documents = [];
  const rounds = new Map();
  for (const name of orderFiles(fileNames)) {
    if (name === HANDOVER_FILE) continue;
    const match = ROUND_FILE.exec(name);
    if (!match) {
      documents.push({ name, label: name });
      continue;
    }
    const n = Number(match[1]);
    if (!rounds.has(n)) rounds.set(n, []);
    rounds.get(n).push({ name, label: match[2] });
  }
  const scopes = [];
  if (documents.length) scopes.push({ key: DOCUMENTS, label: "Documents", files: documents });
  for (const n of [...rounds.keys()].sort((a, b) => a - b)) {
    scopes.push({ key: roundScope(n), label: `Round ${n}`, files: rounds.get(n) });
  }
  return scopes;
}

// Jobs written before handover.md existed have no overview, so they open on a raw file.
export function initialFile(fileNames) {
  if (fileNames.includes(HANDOVER_FILE)) return OVERVIEW;
  return fileNames.length ? orderFiles(fileNames)[0] : null;
}
