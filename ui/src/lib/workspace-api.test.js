import { describe, expect, it } from "vitest";
import {
  addNote,
  createTask,
  deleteNote,
  deleteTask,
  fetchJobStats,
  fetchNotes,
  fetchTasks,
  moveTask,
  updateTask,
} from "./workspace-api.js";
import { ApiError } from "./api.js";

function reply(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

// Each test states what the server said and checks what the client sent; only transport is faked.
function server(routes) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options, body: options.body ? JSON.parse(options.body) : undefined });
    const route = routes[`${options.method || "GET"} ${url}`];
    if (!route) throw new Error(`unexpected request ${options.method || "GET"} ${url}`);
    return route;
  };
  return { fetchImpl, calls };
}

describe("fetchTasks", () => {
  it("returns the tasks and the column names the server accepts", async () => {
    const { fetchImpl } = server({
      "GET /api/tasks": reply(200, { tasks: [{ id: 1 }], statuses: ["backlog", "ready"] }),
    });
    expect(await fetchTasks(fetchImpl)).toEqual({ tasks: [{ id: 1 }], statuses: ["backlog", "ready"] });
  });

  it("surfaces the server's reason when it fails", async () => {
    const { fetchImpl } = server({ "GET /api/tasks": reply(500, { error: "store unavailable: disk" }) });
    await expect(fetchTasks(fetchImpl)).rejects.toThrow(/store unavailable: disk/);
    await expect(fetchTasks(fetchImpl)).rejects.toBeInstanceOf(ApiError);
  });
});

describe("task mutations", () => {
  it("creates a task with exactly the fields given", async () => {
    const { fetchImpl, calls } = server({ "POST /api/tasks": reply(201, { id: 3, title: "T" }) });
    const task = await createTask({ title: "T", prompt: "do it" }, fetchImpl);
    expect(task.id).toBe(3);
    expect(calls[0].body).toEqual({ title: "T", prompt: "do it" });
  });

  it("patches only the changed fields", async () => {
    const { fetchImpl, calls } = server({ "PATCH /api/tasks/4": reply(200, { id: 4 }) });
    await updateTask(4, { title: "New" }, fetchImpl);
    expect(calls[0].body).toEqual({ title: "New" });
  });

  it("moves a task to a column, optionally at a position", async () => {
    const { fetchImpl, calls } = server({ "POST /api/tasks/5/move": reply(200, { id: 5 }) });
    await moveTask(5, "ready", 0, fetchImpl);
    expect(calls[0].body).toEqual({ status: "ready", index: 0 });
  });

  it("deletes a task", async () => {
    const { fetchImpl, calls } = server({ "DELETE /api/tasks/6": reply(200, { status: "ok" }) });
    await deleteTask(6, fetchImpl);
    expect(calls[0].options.method).toBe("DELETE");
  });

  it("reports the server's validation message for a rejected task", async () => {
    const { fetchImpl } = server({ "POST /api/tasks": reply(400, { error: "title is required" }) });
    await expect(createTask({ title: "" }, fetchImpl)).rejects.toThrow(/title is required/);
  });
});

describe("notes", () => {
  it("lists a task's notes by task id", async () => {
    const { fetchImpl } = server({ "GET /api/notes?task_id=7": reply(200, { notes: [{ id: 1, body: "x" }] }) });
    expect(await fetchNotes({ taskId: 7 }, fetchImpl)).toEqual([{ id: 1, body: "x" }]);
  });

  it("lists a job's notes by repository and id, encoding both", async () => {
    const url = "/api/notes?repo_path=%2Fwork%2Fmy%20repo&job_id=001-x";
    const { fetchImpl } = server({ [`GET ${url}`]: reply(200, { notes: [] }) });
    expect(await fetchNotes({ job: { repo_path: "/work/my repo", id: "001-x" } }, fetchImpl)).toEqual([]);
  });

  it("attaches a note to a task or a job, never both", async () => {
    const { fetchImpl, calls } = server({ "POST /api/notes": reply(201, { id: 1 }) });
    await addNote("task note", { taskId: 7 }, fetchImpl);
    await addNote("job note", { job: { repo_path: "/r", id: "001-x" } }, fetchImpl);
    expect(calls[0].body).toEqual({ body: "task note", task_id: 7 });
    expect(calls[1].body).toEqual({ body: "job note", repo_path: "/r", job_id: "001-x" });
  });

  it("deletes a note", async () => {
    const { fetchImpl, calls } = server({ "DELETE /api/notes/9": reply(200, { status: "ok" }) });
    await deleteNote(9, fetchImpl);
    expect(calls[0].url).toBe("/api/notes/9");
  });
});

describe("fetchJobStats", () => {
  it("returns the stats for a job, encoding its identity", async () => {
    const url = "/api/jobs/stats?repo_path=%2Fr&id=001-x";
    const { fetchImpl } = server({ [`GET ${url}`]: reply(200, { stats: { total_seconds: 60 } }) });
    expect(await fetchJobStats({ repo_path: "/r", id: "001-x" }, fetchImpl)).toEqual({ total_seconds: 60 });
  });

  it("returns null for a job that has no events yet", async () => {
    const { fetchImpl } = server({ "GET /api/jobs/stats?repo_path=%2Fr&id=001-x": reply(200, { stats: null }) });
    expect(await fetchJobStats({ repo_path: "/r", id: "001-x" }, fetchImpl)).toBeNull();
  });
});
