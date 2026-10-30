import { describe, expect, it } from "vitest";
import { ApiError, archiveJob, fetchJobs } from "./api.js";

function reply(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

// A fake server keyed by path, so each test states what the server said and checks what the
// client did with it; the transport is the only thing replaced.
function server(routes) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    const route = routes[url];
    if (!route) throw new Error(`unexpected request ${url}`);
    return typeof route === "function" ? route(options) : route;
  };
  return { fetchImpl, calls };
}

describe("fetchJobs", () => {
  it("returns in-progress and archived jobs", async () => {
    const { fetchImpl } = server({
      "/api/jobs": reply(200, { jobs: [{ id: "1" }] }),
      "/api/jobs/archive": reply(200, { jobs: [{ id: "2" }] }),
    });
    expect(await fetchJobs(fetchImpl)).toEqual({ inProgress: [{ id: "1" }], archived: [{ id: "2" }], archiveError: null });
  });

  it("still returns in-progress jobs when only the archive request fails", async () => {
    const { fetchImpl } = server({
      "/api/jobs": reply(200, { jobs: [{ id: "1" }] }),
      "/api/jobs/archive": reply(500, { error: "disk full" }),
    });
    const result = await fetchJobs(fetchImpl);
    expect(result.inProgress).toEqual([{ id: "1" }]);
    expect(result.archived).toEqual([]);
    expect(result.archiveError).toContain("disk full");
  });

  it("fails when the in-progress request fails, naming the status", async () => {
    const { fetchImpl } = server({
      "/api/jobs": reply(503, null),
      "/api/jobs/archive": reply(200, { jobs: [] }),
    });
    await expect(fetchJobs(fetchImpl)).rejects.toThrow(/load jobs: HTTP 503/);
  });

  it("treats a missing jobs array as empty rather than crashing", async () => {
    const { fetchImpl } = server({ "/api/jobs": reply(200, {}), "/api/jobs/archive": reply(200, {}) });
    expect(await fetchJobs(fetchImpl)).toMatchObject({ inProgress: [], archived: [] });
  });
});

describe("archiveJob", () => {
  it("posts the job identity and the reason", async () => {
    const { fetchImpl, calls } = server({ "/api/jobs/archive": reply(200, { ok: true }) });
    await archiveJob({ id: "001-x", repo_path: "/repo" }, "shipped", fetchImpl);
    expect(calls[0].options.method).toBe("POST");
    expect(JSON.parse(calls[0].options.body)).toEqual({ id: "001-x", repo_path: "/repo", reason: "shipped" });
  });

  it("falls back to the default reason", async () => {
    const { fetchImpl, calls } = server({ "/api/jobs/archive": reply(200, {}) });
    await archiveJob({ id: "1", repo_path: "/r" }, "", fetchImpl);
    expect(JSON.parse(calls[0].options.body).reason).toBe("approved");
  });

  it("surfaces the server's error message", async () => {
    const { fetchImpl } = server({ "/api/jobs/archive": reply(409, { error: "job is not needs-human" }) });
    const attempt = archiveJob({ id: "1", repo_path: "/r" }, "", fetchImpl);
    await expect(attempt).rejects.toBeInstanceOf(ApiError);
    await expect(attempt).rejects.toThrow(/job is not needs-human/);
  });
});
