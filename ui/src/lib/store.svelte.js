// Application state. A single object holds everything the components share, so the polling loop,
// the theme and the open job have one owner instead of module-level globals.

import { fetchJobs } from "./api.js";
import { fetchTasks } from "./workspace-api.js";

const THEME_KEY = "eg-dark-mode"; // Same key as the single-file dashboard, so a saved choice survives.
const POLL_INTERVAL_MS = 2000;

function initialTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved !== null) return saved === "true" ? "dark" : "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export const app = $state({
  inProgress: [],
  archived: [],
  loaded: false,
  connectionLost: false,
  lastUpdated: null,
  archiveError: null,
  tasks: [],
  taskStatuses: [], // The column names the server accepts; the UI never keeps its own list.
  tasksError: null,
  tab: "in-progress", // "in-progress" | "tasks" | "archive"
  view: "pipeline", // "pipeline" | "grouped"
  theme: initialTheme(),
  openJobKey: null,
  openTaskId: null,
});

// Jobs from different repositories can share an id, so identity is repository plus id.
export function jobKey(job) {
  return `${job.repo_path || job.repository || ""}::${job.id}`;
}

// The open job is looked up from the latest poll, so a job under review updates while read.
// If it disappears (archived elsewhere) the viewer closes instead of showing stale data.
export function openJob() {
  if (!app.openJobKey) return null;
  return [...app.inProgress, ...app.archived].find((job) => jobKey(job) === app.openJobKey) ?? null;
}

export function openTask() {
  if (app.openTaskId === null) return null;
  return app.tasks.find((task) => task.id === app.openTaskId) ?? null;
}

export function setTheme(theme) {
  app.theme = theme;
  localStorage.setItem(THEME_KEY, String(theme === "dark"));
}

export function toggleTheme() {
  setTheme(app.theme === "dark" ? "light" : "dark");
}

let timer = null;

// Tasks are loaded on their own so a task failure never marks the factory connection as lost
// (and the reverse): the job list is the dashboard's core and must not depend on the task store.
export async function refreshTasks() {
  try {
    const { tasks, statuses } = await fetchTasks();
    app.tasks = tasks;
    app.taskStatuses = statuses;
    app.tasksError = null;
  } catch (error) {
    app.tasksError = error.message;
  }
}

export async function poll() {
  try {
    const { inProgress, archived, archiveError } = await fetchJobs();
    app.inProgress = inProgress;
    app.archived = archived;
    app.archiveError = archiveError;
    app.connectionLost = false;
    app.lastUpdated = new Date();
  } catch {
    // Keep showing the last good data: a dropped poll must not blank a page someone is reading.
    app.connectionLost = true;
  } finally {
    app.loaded = true;
  }
  await refreshTasks();
}

export function startPolling() {
  poll();
  timer = setInterval(poll, POLL_INTERVAL_MS);
  return stopPolling;
}

export function stopPolling() {
  clearInterval(timer);
  timer = null;
}
