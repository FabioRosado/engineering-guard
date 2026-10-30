# Factory Workspace: SQLite store, job events and stats, notes, task board

**Status:** Approved 2026-10-30 (Revision 1)
**Revision:** 1 (2026-10-30)

Items marked *(developer)* were stated by the developer. Items marked *(proposal)* are agent
recommendations and are not approved until the developer approves the complete revision.
Approval does not itself authorise implementation.

This record revises one point of `central-factory-dashboard.md`: D18 ("simple JSON files, no
database") is superseded for **new data only**. Jobs, archive and the job mirror stay JSON.

## Objective

Add to the central factory dashboard:

1. A SQLite store for new data (tasks, notes, prompts, job events).
2. Per-job run statistics, viewable in the job modal.
3. Notes attached to jobs and to tasks.
4. A task board (kanban) where the developer keeps tasks, each with a prompt, and copies a
   prompt to the clipboard to start a factory session.

### Acceptance criteria (proposed)

1. `~/.engineering-guard-factory/factory.db` is created on server start with a versioned
   schema; mode 600 like the existing stores; Python standard library `sqlite3` only.
2. Tasks can be created, edited, moved between columns, reordered and deleted from the UI.
3. Each task holds a title, a prompt, and notes. A "Copy prompt" action puts the prompt on the
   clipboard. No process is spawned by the server.
4. Notes can be added to a job or to a task, and are listed newest first.
5. The board records a timestamped event on every stage transition and it reaches the store
   through the existing sync push. A job's modal shows: total wall time, time per stage,
   human-wait versus agent time, rounds, rebuilds, and agent count derived from events.
6. Job state (`board.json`, `data.json`, `archive.json`) and the push contract keep working
   unchanged; a down server still never blocks the board (D15).
7. `backlog.md` and `next` are unchanged.
8. New server endpoints and the store have tests, and the existing untested
   `/api/jobs/sync` and `/api/jobs/archive` endpoints are covered first.

## Repository evidence (observed 2026-10-30)

- Central store is two JSON files rewritten whole on every sync
  (`central_factory_server.py:388-436`). Today: 7 in-progress jobs (279 KB), 14 archived
  (1.17 MB); largest job about 138 KB of markdown.
- D18 deferred a database "if jobs exceed thousands" (`central-factory-dashboard.md:171`).
  That trigger has not been reached; this record does not claim it has.
- Server is single-threaded on purpose to avoid locking read-modify-write
  (`central_factory_server.py:85-90`). The existing record's "file locking" claim is not what
  the code does.
- Board is stdlib only, the only writer of `board.json`, and its push is best-effort with a
  2 s timeout (`factory_board.py:204-252`); `FACTORY_DISABLE_CENTRAL_SYNC` disables it in tests.
- `take_backlog_item` is a local file operation (`factory_board.py:619-627`), tested at
  `test/test_factory_board.py:402`.
- Job fields carry only `created`, `updated` (overwritten each save, `factory_board.py:353`)
  and, centrally, `completed_at`. `history` has no timestamps. No agent count, exit code,
  token or cost data exists. `models` is orchestrator-reported and often `"default (fallback)"`.
- The UI starts no sessions; the orchestrator agent spawns them inside its own CLI.
- UI reuse points: `ui/src/lib/jobs.js` (`STAGES`, `groupByStage`), `Pipeline.svelte`,
  `JobCard.svelte`, `JobViewer.svelte`, `ui/src/lib/api.js`.
- Python `sqlite3` is in the standard library (3.54.1 locally); README promises no
  third-party Python packages.
- Not verified: how much agent runtime data each CLI exposes to the orchestrator.

## Developer decisions

| # | Decision |
|---|----------|
| D52 | Accept SQLite for **new** data (tasks, notes, prompts, job events). Jobs, archive and the job mirror stay JSON. Supersedes D18 for new data only. *(developer)* |
| D53 | Starting a session from a task is **copy to clipboard only**. The server spawns nothing. Spawning a CLI may be explored later. *(developer: "yes do a copy to clipboard, we can explore remove toggles in the future")* |
| D54 | Stats are stage timing, rounds, rebuilds and derived agent count. Tokens, cost and exit codes are out of scope. Shown in the job modal. *(developer)* |
| D55 | Notes attach to jobs **and** to tasks. *(developer)* |

## Recommendations awaiting approval

| # | Recommendation |
|---|----------------|
| R1 | **Tasks are central-only; `backlog.md` and `next` stay untouched** (Q4). The copy-prompt flow covers the stated use case with no change to the board and no coupling of the local state machine to an optional server. |
| R2 | The board, not the server, records stage events, because only the board sees transitions. Events ride on the existing sync payload as a new `events` list; the server stores them in SQLite. Old servers ignore the extra key. |
| R3 | Add tests for `/api/jobs/sync`, `/api/jobs/archive` and archive cleanup **before** changing the server, since none exist. |
| R4 | The task board's column list lives in one place (a constant in the UI, with the allowed values validated by the server), not a third copy next to `PIPELINE_STAGES` and `STAGES`. |
| R5 | Land after the in-flight factory-intelligence change (uncommitted edits in `factory_board.py`), since both touch the same file. |

## Architecture (proposed)

```
factory_board.py ──POST /api/jobs/sync {job, events}──► central server
                                                         ├─ data.json / archive.json  (jobs, unchanged)
                                                         └─ factory.db                (new)
                                                              tasks, task_notes/job_notes,
                                                              job_events
browser ◄─ GET /api/jobs, /api/tasks, /api/jobs/<id>/stats
        ─► POST/PATCH/DELETE /api/tasks, POST /api/notes
```

- **Store:** one `sqlite3` connection module in the server directory, `PRAGMA user_version`
  migrations, WAL mode, foreign keys on. The server stays single-threaded, so there is one
  writer; SQLite removes the whole-file rewrite for new data without a locking design.
- **Tables (names indicative):** `tasks(id, title, prompt, status, position, repo_path?,
  job_id?, created, updated)`, `notes(id, task_id?, job_key?, body, created)` with a CHECK that
  exactly one parent is set, `job_events(id, repo_path, job_id, stage, round, at, kind)`.
- **Job key:** `(repo_path, id)`, same as the JSON store, because ids restart at 001 per repo.
- **Events:** the board appends `{stage, round, at}` on each transition in `Factory.save`.
  Events are idempotent on `(repo_path, job_id, stage, round, at)` so repeated pushes do not
  duplicate rows.
- **Stats** are computed on read from events: time in each stage, human-wait (stages
  `spec-review`, `needs-human`) versus agent time, rounds, rebuilds, agent count (derived per
  stage: one builder, one test-auditor, up to five reviewers, STRIDE, approver).
- **UI:** a new Tasks view alongside Pipeline and Grouped, built with the impeccable skill
  following `PRODUCT.md` and `DESIGN.md`. Running jobs appear as cards that resemble but are
  visually distinct from the pipeline cards. A task detail panel holds the prompt (with Copy),
  notes and linked job. The job modal gains a Stats tab and a Notes section.
- **Security:** server stays bound to `127.0.0.1`. Task and note text is plain text rendered
  through the existing sanitising path (`markdown.js`/DOMPurify), never as HTML. No new
  command-execution path (D53). SQL uses parameter binding only.

## Alternatives considered

| Option | Status | Evidence / rationale | Revisit if |
|--------|--------|----------------------|-----------|
| A. Keep JSON, add tasks/notes as more JSON files | Rejected | UI-edited data written alongside board syncs; whole-file read-modify-write makes lost updates likely and queries become hand-written code. Assumption "volume stays small" is true today but does not fix concurrency. | Task and note volume stays trivial and the UI never edits concurrently. |
| B. SQLite for new data only; JSON jobs unchanged | **Proposed (D52 accepts the storage choice)** | Relational, UI-edited data fits SQLite; leaves the working job mirror and board untouched. Cost: one new file and a migration step. | — |
| C. Move jobs and archive into SQLite too | Deferred | At 21 jobs there is no measured problem; atomic rename and corrupt-file quarantine work today. Would also fix the `created_at` cleanup bug as a side effect, but that is cheaper to fix alone. | Jobs reach hundreds, or the JSON mirror causes observed data loss or slow polls. |
| D. Per-repo SQLite under `.factory/` | Rejected | The dashboard is cross-repo and the UI writes to the central server; per-repo files would need aggregation again. | Dashboard becomes per-repo. |
| Q4-B. `next` pulls from the central server | Rejected for now | Makes a local, server-optional state machine depend on HTTP; needs a `backlog.md` fallback anyway; breaks D15's spirit. | Developer maintains both lists and wants one. Add with `backlog.md` fallback. |
| Q4-C. Board reads SQLite directly | Rejected | Board is stdlib, repo-scoped; reading a global DB crosses repos and adds a second writer-path to shared state. | — |
| Q4-D. Server writes `backlog.md` from tasks | Rejected | Second writer to repo state; needs path and sync rules. | — |
| Spawn a CLI from the UI | Deferred (D53) | Adds command execution to an unauthenticated local server; needs a dedicated security review and per-CLI invocation knowledge (unverified). | Developer wants it and accepts a security review. |
| Tokens/cost stats | Out of scope (D54) | Board never sees the agent runtime; not available on every CLI (unverified). | An agent runtime exposes it through a stable channel. |

## Constraints and trade-offs

- **D15 stays:** push failure never blocks the board. Events are best-effort; stats for a job
  are incomplete if the server was down during a transition. Accepted.
- **Backfill is limited:** existing jobs have only `created`, `updated` and `completed_at`.
  Stats for them show wall time only, not per-stage time. Accepted.
- **Event timestamps are the board's clock** (second precision, UTC, like `utc_now()`), not the
  agent's. They measure stage transitions, not agent compute time. Labelled accordingly in the UI.
- **Two stores:** jobs in JSON, new data in SQLite. Accepted as the cost of not migrating
  working storage. Backups cover both files in `~/.engineering-guard-factory/`.
- **Single-threaded server:** unchanged. SQLite is safe under it; threading remains out of scope.
- **Compatibility:** sync payload gains an optional `events` key; the server must accept
  payloads without it, and an old server must ignore it.

## Implementation steps (proposed)

1. Tests for `/api/jobs/sync`, `/api/jobs/archive` and archive cleanup against the current
   JSON server. Fix the `created_at` versus `created` fallback in `_cleanup_archive`
   (`central_factory_server.py:449`) as a separate, small change.
2. Board: record `{stage, round, at}` events in `Factory.save`, include them in the push
   payload; board tests for event content and ordering. (After the in-flight change lands.)
3. Server: SQLite module with migrations; ingest events from sync; endpoints for tasks,
   notes and stats; server tests with a temporary data directory.
4. UI data layer: `api.js` functions and a single board-columns constant with tests.
5. UI: Tasks board, task panel (prompt, Copy, notes), job modal Stats and Notes, designed with
   the impeccable skill; refresh `PRODUCT.md` and `DESIGN.md`, which are stale.
6. Docs: `docs/factory.md` (store, endpoints, stats meaning), and a revision note on
   `central-factory-dashboard.md` D18.

## Verification (expected)

- `npm test` and `npm run ui:test` pass, with new coverage for each step above.
- With the server stopped, a board command still succeeds and exits 0.
- A transition sequence produces the expected events; replaying a push adds no duplicates.
- Stats for a job with events match the transitions; a legacy job shows wall time only.
- Task and note text containing HTML renders inert.
- Copy puts the exact prompt on the clipboard; no process is created.

## Open questions and risks

- Task-to-job link: set manually in the UI, or automatically when a pasted prompt becomes a
  job? Not decided; proposal is a manual "link job" action in v1.
- Task board columns: proposal is Backlog, Ready, In Progress, Done, fixed in v1.
- Whether tasks should be scoped to a repository or global. Proposal: optional `repo_path`.
- Agent-count accuracy is derived, not measured (assumption, unverified per CLI).
- Overlap with uncommitted edits in `factory_board.py` and `decisions/factory-intelligence.md`.
- Pre-existing duplicated stage lists (`PIPELINE_STAGES` and `STAGES`) remain a drift risk.

## Re-check against project constraints

- README: no third-party Python packages — met (`sqlite3` is stdlib).
- D10 (factory output stays out of git) — met; the DB lives in the home directory.
- D15 (non-blocking push) and D17 (local-only, port 5173) — unchanged.
- D18 — knowingly superseded for new data; to be noted in `central-factory-dashboard.md`.
- Repository security posture (`127.0.0.1`, sanitised rendering, no spawn) — preserved.
- No `AGENTS.md` exists in the repo; the global credential-safety rules are not affected.

## Revision and approval status

**Status:** Approved (Revision 1), including R1-R5 and the proposed defaults for the open
questions (manual task-to-job link, fixed columns Backlog/Ready/In Progress/Done, optional
`repo_path` on tasks). Developer: "approve and implement".
**Approved revision:** 1.
**Approval date:** 2026-10-30.

## Implementation status (2026-10-30)

Implemented against approved Revision 1. Acceptance criteria 1-8 are met; the verification run is
recorded below. Deviations from the plan, all within the approved architecture:

- **Store module:** `.agents/skills/factory/scripts/factory_store.py`, loaded by path from the
  server like `factory_board.py`. The server is the only consumer.
- **Events are recorded in `Factory.save`**, the single place every stage change passes through,
  rather than at each of the ~20 transition sites (`record_stage_event`).
- **Stats ride on a separate endpoint** (`GET /api/jobs/stats`) rather than on the job payload, so
  the 2-second job poll stays unchanged.
- **Columns are served by the API** (`GET /api/tasks` returns `statuses`), which satisfies R4
  without a third hand-kept stage list in the UI.
- **Sync reports partial work:** if events cannot be stored, the job update still lands and the
  response carries `events_stored: false` and `events_error`.
- **Pre-existing bug fixed:** archive cleanup read `created_at` but the board writes `created`, so
  an archived job without `completed_at` was deleted at the next cleanup. Fixed with a regression
  test (plan step 1).
- **Open questions resolved as proposed:** manual task-to-job link, fixed four columns, optional
  `repo_path` on tasks.

Not changed: `backlog.md`, `next`, `board.json`, the sync contract (an extra optional `events` key
is the only addition), the `127.0.0.1` binding.
