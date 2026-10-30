// Talks to central_factory_server.py. The built app is served by that same server, so all URLs
// are relative; there is no per-repository fallback (decision D31).

export class ApiError extends Error {}

async function readJson(response, action) {
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

// The archive list is a convenience: if only it fails, the in-progress jobs are still worth
// showing, so its failure is reported separately instead of failing the whole poll.
export async function fetchJobs(fetchImpl = fetch) {
  const [inProgressResponse, archiveResponse] = await Promise.all([
    fetchImpl("/api/jobs", { cache: "no-store" }),
    fetchImpl("/api/jobs/archive", { cache: "no-store" }),
  ]);
  const inProgress = (await readJson(inProgressResponse, "load jobs")).jobs || [];
  let archived = [];
  let archiveError = null;
  try {
    archived = (await readJson(archiveResponse, "load archive")).jobs || [];
  } catch (error) {
    archiveError = error.message;
  }
  return { inProgress, archived, archiveError };
}

export async function archiveJob(job, reason, fetchImpl = fetch) {
  const response = await fetchImpl("/api/jobs/archive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: job.id, repo_path: job.repo_path, reason: reason || "approved" }),
  });
  await readJson(response, "archive");
}
