// Pure helpers for the task board and the job statistics. Kept free of Svelte so the rules that
// decide what a person sees can be tested directly, like jobs.js.

import { STAGES } from "./jobs.js";

export const COLUMN_LABELS = {
  backlog: "Backlog",
  ready: "Ready",
  "in-progress": "In Progress",
  done: "Done",
};

// The server owns the list of columns (it validates against it); the UI only labels them. A task
// whose status the UI has never heard of is shown in an "Unknown" column instead of vanishing.
export function columnsFor(tasks, statuses) {
  const known = new Set(statuses);
  const columns = statuses.map((key) => ({
    key,
    name: COLUMN_LABELS[key] || key,
    tasks: tasks.filter((task) => task.status === key).sort((a, b) => a.position - b.position),
  }));
  const unknown = tasks.filter((task) => !known.has(task.status));
  if (unknown.length) columns.push({ key: "unknown", name: "Unknown", tasks: unknown });
  return columns;
}

export function promptPreview(prompt, limit) {
  const flat = (prompt || "").replace(/\s+/g, " ").trim();
  return flat.length <= limit ? flat : `${flat.slice(0, limit - 1).trimEnd()}…`;
}

// A task links to a job by repository and id: ids restart at 001 in every repository.
export function jobForTask(task, jobs) {
  if (!task.job_id || !task.repo_path) return null;
  return jobs.find((job) => job.id === task.job_id && job.repo_path === task.repo_path) ?? null;
}

export function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  const parts = [];
  if (days) {
    parts.push(`${days}d`);
    if (hours) parts.push(`${hours}h`);
  } else if (hours) {
    parts.push(`${hours}h`);
    if (minutes) parts.push(`${minutes}m`);
  } else if (minutes) {
    parts.push(`${minutes}m`);
    if (rest) parts.push(`${rest}s`);
  } else {
    parts.push(`${rest}s`);
  }
  return parts.join(" ");
}

const STAGE_LABELS = Object.fromEntries(STAGES);

// Turns the server's stats into what the modal shows. Stage order follows the pipeline, not the
// order the server happened to list them in; each stage carries its share of the total so the
// view can size a bar without recomputing.
export function statLines(stats) {
  const pipelineOrder = STAGES.map(([key]) => key);
  const stages = Object.entries(stats.seconds_by_stage)
    .sort(([a], [b]) => pipelineOrder.indexOf(a) - pipelineOrder.indexOf(b))
    .map(([stage, seconds]) => ({
      stage,
      label: STAGE_LABELS[stage] || stage,
      seconds,
      value: formatDuration(seconds),
      share: stats.total_seconds > 0 ? seconds / stats.total_seconds : 0,
    }));
  return {
    status: stats.finished ? "Finished" : "Running: time is still counting",
    summary: [
      { label: "Total time", value: formatDuration(stats.total_seconds) },
      { label: "Waiting on you", value: formatDuration(stats.human_seconds) },
      { label: "Factory working", value: formatDuration(stats.agent_seconds) },
      { label: "Build rounds", value: String(stats.rounds) },
      { label: "Rebuilds", value: String(stats.rebuilds) },
      { label: "Agents run", value: String(stats.agents) },
    ],
    stages,
  };
}
