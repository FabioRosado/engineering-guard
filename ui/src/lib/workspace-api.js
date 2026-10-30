// Talks to the task, note and stats endpoints of central_factory_server.py. Kept apart from
// api.js, which owns the job list and archive polling, so the two can change independently.

import { ApiError } from "./api.js";

async function request(fetchImpl, action, url, options) {
  const response = await fetchImpl(url, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      detail = (await response.json()).error || detail;
    } catch {
      // The body was not JSON; the status line is the best detail available.
    }
    throw new ApiError(`${action}: ${detail}`);
  }
  return response.json();
}

function send(method, body) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

// The server also returns the column names it accepts, so the UI never keeps its own list.
export async function fetchTasks(fetchImpl = fetch) {
  const { tasks, statuses } = await request(fetchImpl, "load tasks", "/api/tasks", { cache: "no-store" });
  return { tasks: tasks || [], statuses: statuses || [] };
}

export function createTask(fields, fetchImpl = fetch) {
  return request(fetchImpl, "create task", "/api/tasks", send("POST", fields));
}

export function updateTask(taskId, fields, fetchImpl = fetch) {
  return request(fetchImpl, "update task", `/api/tasks/${taskId}`, send("PATCH", fields));
}

export function moveTask(taskId, status, index, fetchImpl = fetch) {
  return request(fetchImpl, "move task", `/api/tasks/${taskId}/move`, send("POST", { status, index }));
}

export function deleteTask(taskId, fetchImpl = fetch) {
  return request(fetchImpl, "delete task", `/api/tasks/${taskId}`, send("DELETE"));
}

// A note belongs to a task ({ taskId }) or to a job ({ job }); the job is identified by its
// repository and id because ids repeat across repositories.
function parentQuery({ taskId, job }) {
  if (taskId !== undefined) return `task_id=${taskId}`;
  return `repo_path=${encodeURIComponent(job.repo_path)}&job_id=${encodeURIComponent(job.id)}`;
}

function parentFields({ taskId, job }) {
  if (taskId !== undefined) return { task_id: taskId };
  return { repo_path: job.repo_path, job_id: job.id };
}

export async function fetchNotes(parent, fetchImpl = fetch) {
  const { notes } = await request(fetchImpl, "load notes", `/api/notes?${parentQuery(parent)}`, { cache: "no-store" });
  return notes || [];
}

export function addNote(body, parent, fetchImpl = fetch) {
  return request(fetchImpl, "add note", "/api/notes", send("POST", { body, ...parentFields(parent) }));
}

export function deleteNote(noteId, fetchImpl = fetch) {
  return request(fetchImpl, "delete note", `/api/notes/${noteId}`, send("DELETE"));
}

// null means the board has recorded no events for this job yet (a job from before events existed).
export async function fetchJobStats(job, fetchImpl = fetch) {
  const query = `repo_path=${encodeURIComponent(job.repo_path)}&id=${encodeURIComponent(job.id)}`;
  const { stats } = await request(fetchImpl, "load stats", `/api/jobs/stats?${query}`, { cache: "no-store" });
  return stats;
}
