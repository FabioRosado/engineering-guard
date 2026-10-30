# Central Factory Dashboard

**Status:** Revision 2 Approved 2026-10-30 (Revision 1 approved 2026-10-28)  
**Revision:** 2 (2026-10-30)

## Objective

Add a system-wide factory dashboard that aggregates job state from all active repositories without requiring per-repository dashboard setup. Developers can see all in-progress and archived jobs from a single, persistent UI. Factories push updates to a central server when state changes, enabling real-time visibility across multiple repositories and worktrees.

### Acceptance criteria

1. Central server runs independently at a fixed location (`~/.engineering-guard-factory/`) on a single port (5173, local-only).
2. Factories push job metadata and full markdown content to the server when `factory_board.py` writes state changes.
3. Central dashboard displays in-progress jobs grouped by repository, with worktree path shown per card.
4. Archive tab shows completed jobs from the last 30 days (configurable).
5. Dashboard renders all markdown files (spec.md, build.md, reviews, decision.md, etc.) in modals without requiring filesystem access.
6. Dashboard polls `/api/jobs` every 2 seconds; multiple worktrees of the same repository sync to the same central server.
7. Network failures do not block factory progress; push failures are logged but non-blocking.
8. Command `/factory-server [start|stop|status]` manages the central server lifecycle.
9. *(Revision 2)* `npm run dashboard` starts the central server in the foreground of a terminal, without an agent session.

## Repository evidence

- Current factory architecture: `.agents/skills/factory/` with orchestrator, roles, and `scripts/factory_board.py` (state machine).
- Per-repository dashboard: `.factory/dashboard.html` and `.factory/board.json` (line 188-199 in `docs/factory.md`).
- Board is the only writer of `.factory/board.json`; each repository's factory is isolated.
- Dashboard is a static HTML file with inline Markdown renderer; no external dependencies.
- Factory jobs live in `.factory/jobs/<id>/` with complete markdown file structure (spec.md, build.md, round-N/reviews, decision.md).

## Developer decisions

| # | Decision |
|---|----------|
| D12 | Central server runs independently with persistent storage at `~/.engineering-guard-factory/`. |
| D13 | Factories push full job metadata (all markdown files) to central server on every state change. |
| D14 | Central dashboard displays jobs grouped by repository (first option), with worktree path as card sub-label when multiple worktrees exist. |
| D15 | Push is non-blocking: 2-second timeout; network failures logged but do not block factory progress. |
| D16 | Archive stores completed jobs for 30 days; retention is configurable. |
| D17 | Port 5173 (Vite default, unlikely conflicts); bind to 127.0.0.1 (local-only). |
| D18 | Central server storage: simple JSON files (`data.json` for in-progress, `archive.json` for completed); no external database required. **Superseded for new data only by D52 in `factory-workspace.md` (2026-10-30):** tasks, notes and job events are stored in SQLite (`factory.db`); jobs and the archive stay JSON as decided here. |

## Architecture

### Components

**1. Central Factory Server** (`scripts/central_factory_server.py`, ~350 lines)
- HTTP server on port 5173, bound to `127.0.0.1`
- REST endpoints:
  - `POST /api/jobs/sync` — receives job updates from factories
  - `POST /api/jobs/archive` — archives a needs-human job when the dashboard's Archive job button is used
  - `POST /api/jobs/abandon` — abandons a job in any open stage when the dashboard's Abandon button is used; a reason is required
  - `GET /api/jobs` — returns all in-progress jobs (JSON)
  - `GET /api/jobs/archive` — returns archived jobs
  - `GET /health` — readiness check
- Data storage:
  - `~/.engineering-guard-factory/data.json` — in-progress jobs
  - `~/.engineering-guard-factory/archive.json` — completed jobs
  - Job data includes full markdown content for all files
  - Automatic cleanup of archived jobs older than 30 days (configurable)
- Handles concurrent pushes; idempotent job updates

**2. Modified factory_board.py** (`scripts/factory_board.py`, ~50 lines added)
- After writing `.factory/board.json`, calls `_push_to_central_server(job_state)` helper
- Helper reads all markdown files from `.factory/jobs/<id>/` and `round-N/` subdirectories
- Constructs job payload with full content
- Makes POST request to `http://127.0.0.1:5173/api/jobs/sync`
- 2-second timeout; catches exceptions and logs warning
- Continues factory progress regardless of push success/failure

**3. Central Dashboard UI** (`assets/central-dashboard.html`, ~400 lines)
- Single-page app served at `http://127.0.0.1:5173/`
- Polls `GET /api/jobs` every 2 seconds
- Two-tab interface:
  - **In Progress:** Jobs grouped by repository name, each card shows worktree path as sub-label
  - **Archive:** Completed jobs with similar layout
- Job cards display:
  - Repository name + worktree path (e.g., "myapp (/Users/fabio/projects/myapp-feature)")
  - Job ID and title
  - Stage column + round badges
  - Reviewer chips (PASS/CHANGES/N/A/pending)
  - Warnings (e.g., test audit failed but approved)
- Clicking card opens a modal. A top bar switches between Overview, Stats, Notes, Documents (root files) and one scope per round; a sidebar lists only the files of the current Documents or Round scope, so Overview, Stats and Notes use the full width
- The modal's Archive job button closes an approved needs-human job without
  leaving the dashboard (no copied shell command)
- The modal's Abandon button stops a job at any open stage (build, review, ...) and moves it
  to the Archive tab. It lives in the modal, not on the card: a card is one button, and a
  destructive action should not sit one mis-click away on a dense board. A reason is required
  and recorded in the job history; worktree changes are left alone. Archived jobs have no Abandon.
- Stage columns: spec → spec-review → build → test-audit → review → stride-review → approver → needs-human → abandoned
- Markdown rendering: inline renderer (same as per-repo dashboard)
- Repository grouping (decided D14, first option):
  - Cards grouped under repository name header
  - When multiple worktrees of same repo exist, each card shows its worktree path

**4. Command** (`.kilo/commands/factory-server.md`)
- `/factory-server start` — launches central server in background
- `/factory-server stop` — gracefully shuts down server
- `/factory-server status` — shows running status and port
- Server persists across sessions; can be left running

### Data flow

```
[Repo A worktree 1]  [Repo A worktree 2]  [Repo B]
    factory              factory           factory
      │                    │                 │
      └─ factory_board.py ─┬─ factory_board.py ─┬─ factory_board.py
         (write .factory)  │ (write .factory)   │ (write .factory)
                           │                    │
                           ▼ POST /api/jobs/sync ▼
                   
              Central Factory Server (port 5173)
                   │
                   ├─ Store job metadata + markdown content
                   ├─ Maintain in-progress and archive
                   └─ Serve REST API
                   
                   ▲
                   │ GET /api/jobs (poll every 2s)
                   │
            ┌──────────────────────┐
            │ Central Dashboard    │
            │ (browser)            │
            │ (grouped by repo)    │
            └──────────────────────┘
```

### Job payload structure

When a factory syncs, it sends:

```json
{
  "repository": "myapp",
  "repo_path": "/Users/fabio/projects/myapp",
  "worktree_path": "/Users/fabio/projects/myapp",
  "job": {
    "id": "001-add-rate-limiting",
    "title": "Add rate limiting to the login endpoint",
    "stage": "review",
    "round": 1,
    "test_audit": "PASS",
    "reviews": {
      "security": "PENDING",
      "ux": "PASS",
      "ui": "N/A",
      "code": "PENDING"
    },
    "stride": null,
    "created_at": "2026-10-28T17:30:00Z",
    "updated_at": "2026-10-28T17:45:00Z",
    "base_commit": "abc123def456",
    "warnings": [],
    "files": {
      "feature.md": "# Feature\n\nAdd rate limiting...",
      "spec.md": "# Specification\n\n...",
      "build.md": "# Build\n\n...",
      "round-1/test-audit.md": "# Test audit\n\nVERDICT: PASS\n...",
      "round-1/review-security.md": "# Security review\n\nVERDICT: PENDING\n...",
      "round-1/review-ux.md": "...",
      "round-1/review-ui.md": "...",
      "round-1/review-code.md": "...",
      "round-1/change.patch": "diff --git...",
      "round-1/files.txt": "src/auth/limiter.py\n..."
    }
  }
}
```

## Alternatives considered

| Option | Status | Rationale |
|--------|--------|-----------|
| Pull-based aggregator (Option A, Research) | Rejected | Requires scanning multiple repos on every poll; push model is more efficient and gives real-time visibility. Developer explicitly chose push architecture. |
| Job summary only (Option B, Align Q3) | Rejected | Developer wants to view all markdown files from central dashboard without navigating to local repos. Full job object enables that. |
| Database persistence (SQLite/PostgreSQL) | Deferred | JSON files sufficient for current use case; can migrate to database if jobs exceed thousands. Simple, no external dependencies. |
| Separate archive storage | Rejected | Archive stored in same `archive.json` file; simpler than separate mechanism. |

## Constraints and trade-offs

| Aspect | Constraint | Mitigation |
|--------|-----------|-----------|
| **Network resilience** | Central server unavailability blocks factory progress IF push is synchronous. | Non-blocking 2-second timeout; factory logs warning and continues. |
| **Storage growth** | JSON files grow unbounded if not pruned. | Automatic cleanup: archive jobs older than 30 days deleted daily. Retention configurable. |
| **Multi-machine access** | Central server only accessible locally (127.0.0.1). | By design: specs and security reviews may contain unfixed vulnerabilities. Sharing across machines deferred. |
| **Concurrent worktree writes** | Multiple worktrees pushing simultaneously could cause data race. | Central server uses file locking; POST /api/jobs/sync is atomic. |
| **Filesystem access in push** | `factory_board.py` must read markdown files from `.factory/jobs/`. | Already has access; reading additional files is safe and within scope. |

## Implementation steps

### Phase 1: Central Server Core
1. Create `scripts/central_factory_server.py`
   - HTTP server on port 5173 (127.0.0.1)
   - Job sync endpoint with atomic file updates
   - Archive management and cleanup
   - In-progress and archive JSON storage
   
2. Create `assets/central-dashboard.html`
   - Two-tab UI (In Progress, Archive)
   - Repository grouping with worktree labels
   - Modal viewer for markdown files
   - 2-second polling of `/api/jobs`

### Phase 2: Factory Integration
3. Modify `scripts/factory_board.py`
   - Add `_push_to_central_server()` helper
   - Call after every state write
   - Collect all markdown files from job directory
   - Handle push timeout gracefully

### Phase 3: User Commands
4. Create `.kilo/commands/factory-server.md`
   - Start/stop/status commands
   - Manage server lifecycle

### Phase 4: Documentation
5. Update `docs/factory.md`
   - Document central dashboard setup
   - Explain server lifecycle
   - Port and configuration details

## Testing and verification

- Unit tests for central server: job sync, archive cleanup, concurrent writes, endpoint validation
- Integration test: spawn multiple factories in parallel, verify real-time sync on central dashboard
- Verify factories continue when central server is unavailable (timeout handling)
- Manual test: view markdown files in dashboard modal for various job types
- Verify archive cleanup removes jobs older than 30 days
- Verify worktree grouping displays correctly with multiple worktrees of same repo

## Security and safety

- Central server bound to `127.0.0.1` only (no network exposure)
- Job data includes specs with unfixed vulnerabilities; file permissions control access
- Markdown content stored in plaintext JSON; no encryption (local-only scope)
- Push is idempotent; duplicate syncs overwrite safely
- Archive retention configurable; jobs can be permanently deleted

## Open questions / Risks

1. **Archive retention:** Currently fixed at 30 days. Should this be user-configurable or adaptive?
2. **Large jobs:** If a single job has many rounds, payload could exceed MB. Observe and optimize if needed.
3. **Server restart:** On restart, in-progress jobs are reloaded from disk. Verify no data loss during restart.

## Revision 2 — Terminal launcher (approved)

Extends Revision 1 without changing D12–D18. Adds a terminal entry point for the lifecycle already required by criterion 8, which is currently implemented only as an agent slash command (`.kilo/commands/factory-server.md`).

### Developer decisions (this revision)

| # | Decision |
|---|----------|
| D19 | Launcher is an npm script, `npm run dashboard`, not a Makefile (developer: "not married to make"). |
| D20 | Scope is the central server only. The per-repo static dashboard is out of scope (developer: "I don't want to start the factory for each repo"). |

### Recommendations R1–R3 (approved with the revision on 2026-10-30)

- **R1.** Hard-code defaults: pass no `--host`/`--port`; the script's own `127.0.0.1:5173` stays the single source of truth. Reason: D17 fixes these, and `factory_board.py:123` hardcodes the push URL to port 5173, so a different port would silently break sync (push failures are non-blocking, D15) and a non-loopback host would breach the local-only constraint.
- **R2.** No `test` target is needed. `npm test` already exists.
- **R3.** Foreground only. `stop`/`status`/`logs` remain with `/factory-server`.

### Proposed change

`package.json` gains one script:

```json
"dashboard": "python3 .agents/skills/factory/scripts/central_factory_server.py"
```

Plus one-line mentions of `npm run dashboard` in `docs/factory.md` ("Central Dashboard") and `.kilo/commands/factory-server.md`. No Python changes.

### Repository evidence (observed 2026-10-30)

- Server already runs in the foreground, serves the dashboard at `/`, answers `/health`, stops cleanly on Ctrl-C (smoke-tested on a spare port).
- It detects a live instance via `/health` and exits with a message, so a repeat `npm run dashboard` is safe (`central_factory_server.py:446`).
- `package.json` already holds the project's scripts (`test`, `demo:*`); no Makefile or `pyproject.toml` exists.
- `scripts/verification_runner.py` runs only explicitly requested scripts and merely lists the others (lines 419-422, 478), so a long-running `dashboard` script will not be executed by verification unless someone requests it.
- README states Node 18+ and npm are already prerequisites (README.md:36); Node 22 and npm 10.9 are present locally. The script itself needs only Python 3, which the README also requires.

### Alternatives (Revision 2)

| Option | Status | Rationale |
|--------|--------|-----------|
| `npm run dashboard` | **Selected (D19)** | Developer's choice. Matches existing script convention; no new tool or file. |
| `Makefile` with `run` | Rejected by developer | Introduces a new build tool for one command. Revisit only if the project adopts make elsewhere. |
| Overridable `PORT`/`HOST` | Rejected (R1, approved) | Conflicts with D17 and the hardcoded push client. Revisit if the push client's URL is first made configurable (env var read by both sides); that is a separate change requiring approval. |
| Wrapper CLI / entry point | Rejected | No demonstrated need (YAGNI). |
| Daemonise (nohup/launchd) | Rejected | Developer wants a terminal session; `/factory-server start` covers background use. |

### Implementation steps

1. Add the `dashboard` script to `package.json`.
2. Add one line to `docs/factory.md` under "Central Dashboard" and to `.kilo/commands/factory-server.md`.
3. No new tests: the change is a one-line launcher over an already-tested script. Verify manually.

### Verification

- `npm run dashboard` prints the listening URL; `http://127.0.0.1:5173/` returns the dashboard and `/health` returns `{"status":"ok"}`.
- Ctrl-C stops it cleanly.
- A second `npm run dashboard` while one is running exits with the "already running" message.
- `npm test` still passes.

### Non-goals

Configurable port/host; background lifecycle; per-repo dashboard; fixing `/factory-server` `stop`/`status`/`logs` having no code behind them; the stale `central-dashboard.html` references in `PRODUCT.md`/`DESIGN.md`.

### Risks

- The `dashboard` script name appears in `available` output of the verification runner; harmless unless requested explicitly.
- Doc drift above is pre-existing and not made worse.

## Revision and approval status

**Status (Revision 2):** Approved 2026-10-30. Developer approved the complete revision, including D19–D20 and R1–R3 ("approve let's do it").  
**Status (Revision 1):** Approved 2026-10-28  
**Developer approval:** Yes, explicit. Decisions D12-D18 approved.  
**Approval date:** 2026-10-28  
**Approved by:** Developer (Fabio Rosado)

Revision 1 is implemented. Revision 2 is approved for implementation.
