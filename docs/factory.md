# Engineering Guard Factory

The factory runs one feature at a time through a fixed loop of agents, reusing
the other Engineering Guard skills as stages. A human approves the spec before
any code is written and makes the final decision on the result. The factory
never commits, pushes or merges.

Design and approval history: `decisions/engineering-guard-factory.md`.

## The loop

```
feature ─► spec-writer ─► [human: approve-spec] ─► builder ◄──────────────────┐
                                                      │                        │
                                                test-auditor ── CHANGES ───────┤
                                                      │ PASS                   │
          ┌─────────────┬───────────┬────────────────┼────────────────┐
          ▼             ▼           ▼                ▼                ▼
      security         ux          ui              code         architecture
          └─────────────┴──────── WAIT FOR ALL ──────┴────────────────┘
                                               │ all PASS/N/A (≤ 2 review rounds) ┘
                                               ▼
                                            stride (whole-repo, once per job) ──CHANGES──┘
                                               │ PASS (no new CRITICAL/HIGH)
                                               ▼
                                            quality-gate (script, once per job) ──findings──► one gate-fix build ─┐
                                               │ pass/warn, or tamper for the human            (back to the gate) ◄┘
                                               ▼
                                            approver ─► ESCALATE ─► needs-human
```

| Stage | Reuses | Default tier | Writes |
|-------|--------|--------------|--------|
| spec-writer | better-prompt, then research | expensive | `prompt.md`, `spec.md`, optionally `handover.md` (reads `feature.md`) |
| builder | implement + testing | expensive | code changes, `build.md`, updates `handover.md` |
| test-auditor | testing (audit mode) | cheap | `round-N/test-audit.md` |
| security | security | expensive | `round-N/review-security.md` |
| ux | UX checklist (`N/A` if no user-facing change) | cheap | `round-N/review-ux.md` |
| ui | UI design checklist (`N/A` if no visual change) | cheap | `round-N/review-ui.md` |
| code | verify | cheap | `round-N/review-code.md` |
| architecture | proposal vs built (`N/A` if nothing to compare) | expensive | `round-N/review-architecture.md` |
| stride | stride (whole-repo threat model) | expensive | `round-N/review-stride.md`, plus its own git-excluded profile/report |
| approver | verify (final pass) | expensive | `decision.md` |

Rules enforced by the board script:

- `handover.md` is optional and living. It holds an executive summary and, only where a
  picture helps, mermaid architecture, flow or sequence diagrams. The spec-writer writes the
  proposal, the builder updates it each round to describe what was built (the approved
  `spec.md` is never edited), and the approver finalises it; `decision.md` then shrinks to
  `ESCALATE`, a one-line recommendation and a pointer. `spec-written`, `build-done` and
  `decision` parse every mermaid block and reject an invalid one, naming the diagram and
  line, before the job changes stage. This needs the optional validator packages
  (`npm install --prefix .agents/skills/factory/validator`, Node.js 20.19+, 22.13+ or 24+);
  without Node or the packages the board records a warning and continues. A syntax check says
  nothing about whether a diagram is true, so the board also warns when code changed in a
  round but the handover was not updated, and the architecture reviewer judges the content.
- The **architecture** reviewer compares the approved proposal and the handover's diagrams
  with `change.patch` and may answer `N/A`. The board writes that `N/A` itself when the spec
  says `Architecture impact: no` and the handover has no diagram; a diagram keeps the review
  on. Rounds that began before this reviewer existed are treated as `N/A` for it.

- Agents read context from job files and write only their own file.
- The test audit, security, code and STRIDE reviews start with `VERDICT: PASS`
  or `VERDICT: CHANGES`; UX and UI reviews may also use `VERDICT: N/A`. A
  `CHANGES` verdict must be followed by at least one finding. A security or
  STRIDE `CHANGES` must additionally cite a finding with `SEVERITY: CRITICAL`
  or `SEVERITY: HIGH`; MEDIUM/LOW/hardening-only findings are reported under
  `PASS` instead and do not block a round.
- `build-done` freezes the change into `round-N/change.patch` and
  `round-N/files.txt` (untracked files included); every auditor and reviewer
  reads that snapshot.
- Reviewers run only after the test audit passes. A test-audit `CHANGES` sends
  the job back to the builder once per attempt, without using a review round;
  after that the reviewers run anyway and the open test findings appear as a
  warning on the board and in `decision.md`.
- When the spec says `UI impact: no` and no changed file is user-facing
  (markup, styles, scripts, templates, images), the script writes the UI
  `N/A` review itself and the UI reviewer is not spawned. UX always runs,
  because CLI output and messages can change in any source file.
- A round closes only when all five reviews exist and are valid. The
  builder is never restarted mid-round.
- Any review `CHANGES` sends the job back to a fresh builder; each attempt
  (initial build or rework) gets two review rounds. After that the approver
  runs with the open findings listed.
- After the five reviewers all pass (or N/A), **stride** runs once against
  the job's full diff and the repository's whole trust-zone model — not once
  per round. Its `CHANGES` (a new or newly-confirmed CRITICAL/HIGH threat on
  a changed component) sends the job back to the builder and consumes the
  same two-round budget as the other reviewers.
- After STRIDE, the board runs the **quality gate** itself (`quality_gate.py`; there is no agent to
  skip). It runs once per job, not on every build/test iteration. Fixable findings (banners,
  secret-shaped literals, swallowed errors, a failing declared lint/type/test command) get one
  gate-fix build round that returns straight to the gate, so the reviews predate that edit and
  `decision.md` says so. Naming issues are warnings the builder must answer in `build.md`.
  Loosened checks (suppression comments, linter or gate config edits, skipped, deleted or
  weakened tests) are **tamper**: never sent back to the builder, listed for you, and cleared only
  by `accept-suppression`. A missing optional tool (gitleaks, bandit) warns and never fails the gate.
  bandit reports only issues on lines the change added, so existing issues in a touched file do not
  fail the job; a file bandit cannot parse fails, because it was not scanned. A failed check's
  command output appears in `round-N/quality-gate.md`.
- `decision.md` must start with `ESCALATE`: the human always decides.
- `approve-spec` rewrites the spec's `Status` line to `Approved`, because
  builders read the spec file, not the board.
- A build must change something. A builder that cannot proceed starts
  `build.md` with `BLOCKED: <reason>` and the job goes straight to
  needs-human instead of spending review rounds on an empty change.
- The build only starts on a clean worktree (ignoring `.factory/`), and only
  one job can be building at a time.

## Declaring the repository's own checks

The gate runs a repository's lint, format, type and test commands only if they are declared in
`.quality-gate.json` at the repository root. Otherwise each reports `not_configured`, which is
neutral: a repository with none declared gets only the built-in rules and the scanners.

To avoid writing it by hand, run once from the target repository:

```sh
python3 /path/to/engineering-guard/.agents/skills/factory/scripts/quality_gate.py --init
```

It reads the repository's files (it never runs a command) and writes a proposed config plus a note
per check saying where each command came from or why it was left out. Review it, then **commit it
before starting a job**: an uncommitted or edited config is reported as tamper and needs
`accept-suppression`. `--init` never overwrites an existing file.

Detection prefers the repository's own entry point, because it carries the repository's environment
wrapper (a conda or venv `run`): a Makefile target, then an npm script, then a tool configured in
project files (ruff, mypy, pytest, cargo, go). Only these names are recognised, so `system-test`,
`deploy-*` and other targets that need credentials are never proposed:

| Check | Recognised names |
|-------|------------------|
| lint | `lint`, `check-lint`, `lint-check` |
| format | `format-check`, `format:check`, `check-format`, `fmt-check`, `format_check` |
| types | `typecheck`, `type-check`, `types`, `check-types`, `mypy`, `tsc` |
| test | `test`, `tests`, `unit`, `test-unit`, `check-test` |

Format is proposed only in check mode. A gate that ran a formatter would rewrite code the reviewers
never saw and hide the failure it exists to report; if a repository has only a mutating `format`
target, `--init` says so and proposes nothing for format.

The schema, if you edit it yourself. Each command is an argv list (no shell):

```json
{
  "checks": {
    "lint":   ["ruff", "check", "{changed}"],
    "format": ["ruff", "format", "--check", "{changed}"],
    "types":  ["make", "typecheck"],
    "test":   ["make", "test"]
  },
  "suffixes": { "lint": [".py"], "format": [".py"] }
}
```

- `{changed}` expands to the changed files that still exist, so existing debt in files the change never
  touched cannot fail the job. Use it only with a tool called directly: `make` and `npm run` cannot pass
  a file list through, so those run repo-wide.
- `suffixes` keeps files the tool cannot read out of its arguments. With no matching changed file the
  check reports `not_configured`.
- Type and test commands normally stay repo-wide, because a change can break them anywhere.
- Each command has a 300 second timeout. A declared command that is not found fails the check.

## Setup

Requirements: Python 3.9+, Git, and one of Codex, Kilo or Claude Code.

**Codex / Kilo:** the skill is discovered from `.agents/skills/factory/` when
this package is installed (see the README) or when working in this repository.

**Claude Code:** Claude does not read `.agents/skills/`. From the repository you
want to work on, run once (and again after changing models):

```sh
FACTORY="python3 /path/to/engineering-guard/.agents/skills/factory/scripts/factory_board.py"
$FACTORY models opus-sonnet --cli claude
$FACTORY install-claude
```

This writes `~/.claude/skills/engineering-guard-factory/SKILL.md` (an
absolute-path pointer to the shared skill) and `~/.claude/agents/eg-*.md`
subagents with their models pinned. Only `eg-builder` may edit files. The
install is user-wide: the last configured models apply in every repository.

## Choosing models

```
/engineering-guard-factory models <preset>
/engineering-guard-factory models <expensive-model> <cheap-model>
```

| Preset | Expensive | Cheap | CLIs |
|--------|-----------|-------|------|
| `opus-sonnet` | Opus | Sonnet | claude, kilo |
| `sonnet-haiku` | Sonnet | Haiku | claude, kilo |
| `sol-luna` | GPT 6.1 sol | GPT 6.1 luna | codex, kilo |
| `luna` | GPT 6.1 luna | GPT 6.1 luna | codex, kilo |

Presets live in `.agents/skills/factory/presets.json`; add one there to make it
selectable. A preset that the current CLI cannot run is rejected rather than
substituted. The preset model IDs have not been verified on every CLI; if one
does not resolve, pass exact IDs with the two-argument form.

The tier each stage uses is listed in the loop table above. If a CLI cannot run
a subagent on a specific model (some Codex versions), that stage uses the
session model and the board records `default (fallback)`.

## Commands

| Command | What it does |
|---------|--------------|
| `models …` | Set the expensive/cheap models (see above). |
| `<feature>` | Create a job, write `prompt.md` and `spec.md`, then stop at **spec-review**. |
| `next` | Same, using the first unchecked `- [ ]` item in `.factory/backlog.md` (and checks it). |
| `approve-spec <id>` | Human approval of the spec. Runs build → reviews → approver until **needs-human**. |
| `approve <id>` | Suggests a branch name, commit message and PR description that follow the repo's conventions, then archives the job. You commit and push. |
| `rework <id> <note>` | Send a **needs-human** job back to the builder with your note; the budget resets (two review rounds, one test-audit rebuild). |
| `resume <id>` | Continue an interrupted job from its current stage. |
| `archive <id> [reason]` | Close an approved **needs-human** job as **Complete** and move it to Archive. |
| `abandon <id> <reason>` | Close a job for good without finishing it, for example after a crash; it ends **Abandoned** and stops blocking new builds. Code changes stay in the worktree. |

The orchestrator's first step is always to create the job and show you its
id; it saves your full feature text to `feature.md` for the spec-writer and
never acts on it directly. If a run starts reading code or editing files
without first showing a job id, it has drifted: stop it and re-invoke.
Long or detailed features (code blocks, logs, hypotheses) are fine — they
are passed through verbatim. Wording the feature as instructions
("investigate…", "fix…") is fine too; the spec-writer turns those into
research and acceptance criteria.

To give feedback on a spec instead of approving it, just reply with the
feedback; it is saved as `spec-feedback-N.md`, the spec-writer revises
`spec.md`, and the job returns to spec-review.

## A typical run

1. `/engineering-guard-factory Add rate limiting to the login endpoint`
2. Read `.factory/jobs/001-add-rate-limiting-to-the-login-endpoint/spec.md`.
   Check the acceptance criteria and the `UI impact` and `Architecture impact` lines. If the
   spec-writer wrote a `handover.md`, read its diagrams too.
3. `/engineering-guard-factory approve-spec 001-add-rate-limiting-to-the-login-endpoint`
4. Watch the dashboard. When the job reaches **needs-human**, read
   `handover.md` (when the job has one), `decision.md`, the reviews, and `git diff`.
5. Either `rework <id> "<what to change>"`, or `approve <id>` and use the
   suggested branch, commit message and PR description to commit yourself.
   Approving also archives the job as **Complete**, including the same action
   from the dashboard's **Archive job** button.

Commit (or stash) the job's changes before approving the next spec: the next
build refuses to start on a dirty worktree.

## Files

Everything lives in `.factory/` in the repository you are working on. It is
added to `.git/info/exclude` on first run, so nothing is committed and the
repository's `.gitignore` is not modified.

```
.factory/
  config.json        # selected models per stage
  board.json         # job state; written only by factory_board.py
  backlog.md         # queue for `next`
  jobs/001-<slug>/
    feature.md  prompt.md  spec.md  handover.md  spec-feedback-N.md  build.md  decision.md  rework-N.md
    round-1/change.patch  files.txt  test-audit.md  review-security.md  review-ux.md  review-ui.md  review-code.md  review-architecture.md  review-stride.md
```

The STRIDE reviewer also maintains its own profile and living threat
register at a separate, git-excluded location in the target repository
(see `.agents/skills/stride/SKILL.md`) — that state persists across jobs
and is not part of any single job's folder.

## Dashboard

The dashboard is the central factory server plus the Svelte UI in `ui/`. The server aggregates every active repository into one view, and each factory pushes its state to it when something changes. Start it from this checkout:

```
npm run dashboard
```

`npm run dashboard` builds the Svelte UI in `ui/` when it is missing or older than its sources (the first run installs its packages, which needs Node.js 20.19+ or 22.12+), then runs the central server in the foreground at <http://localhost:5173/>; stop it with Ctrl-C. There is no per-repository mode: every factory pushes its state to the central server, which is the only source for the dashboard.

Jobs are cards across the stage columns (Pipeline view, which scrolls sideways so every stage stays in order) or grouped by repository (Grouped view); each round shows a `tests` chip followed by reviewer chips (green PASS, amber CHANGES, grey N/A or pending). Jobs waiting on you (spec-review, needs-human) are outlined in teal. Click a card to open the job. A job with a `handover.md` opens on an **Overview** tab: status chips, warnings, the recommendation from `decision.md`, and the handover rendered as a document with its mermaid diagrams drawn. A diagram that cannot be drawn shows a plain error card with its source instead of leaving a gap; a top bar switches between Overview, Stats, Notes, Documents (`spec.md`, `build.md`, ...) and one scope per round (`Round 1`, `Round 2`, ...); the sidebar lists only the files of the selected Documents or Round scope. Jobs from before `handover.md` existed have no Overview and open on their first file. Use **Archive job** in the viewer to close an approved job as Complete. Use **Abandon** (shown for every job that is still open, at any stage) to stop a job that is stuck or no longer wanted: it asks for a reason, records it in the job history, moves the job to the Archive tab, and leaves worktree changes untouched. If the board has already closed the job (for example it was archived from another checkout of the same repository, or the dashboard missed the update), either button just brings the dashboard in line with the board: the entry leaves In Progress, the board's recorded outcome and history are not changed, and no error is shown. Jobs closed before the `complete` stage existed are stored as `abandoned` with an `archived_from` history entry; the dashboard shows them as Complete without rewriting them. One board reached through two paths (a worktree whose `.factory` is a symlink to the main checkout's) is one job in the Archive, not two.

Job markdown is written by agents, so the UI treats it as untrusted: HTML in it is shown as text, scripts and `javascript:` links are removed, and diagrams are drawn in mermaid's strict mode. Keep the server bound to `127.0.0.1`: specs, security reviews and STRIDE's living threat register can describe unfixed vulnerabilities. STRIDE's profile and report live outside `.factory/`, at a separate git-excluded location, so they are not shown by this dashboard.

### Tasks, notes and job statistics

The **Tasks** tab is a board for work you have not started: Backlog, Ready, In Progress and Done. A strip above it shows the jobs running now. Add a task by title, open it to write its **prompt**, and press **Copy prompt** when you are ready to start a session; paste it into your agent to run the factory. The dashboard never starts a session itself. A task can be linked to a job by hand, and moves between columns by dragging or from the task's **Column** menu. Both tasks and notes are plain text, so anything in them is shown as text, never as markup.

Notes attach to a task or to a job (the job viewer's **Notes** tab). The job viewer's **Stats** tab shows total time, time waiting on you versus the factory working, build rounds, rebuilds and an agent count, plus the time spent in each stage.

The stats come from a timestamped event the board records each time a job changes stage and sends with its normal push. They measure when each stage began and ended, not how long an agent computed. Agents run is derived from the stages a job passed through, and counts all five reviewers each round even when one was marked N/A. Jobs that finished before events were recorded have no timing and say so. Tokens, cost and exit codes are not recorded.

Storage: jobs stay in `data.json` and `archive.json` in `~/.engineering-guard-factory/`, which remain a mirror of each repository's `board.json`. Tasks, notes and events are kept in `factory.db` (SQLite) in the same folder, readable only by you. The dashboard owns that file: a repository's board never reads it, so `backlog.md` and `next` are unchanged and the board still works with the server stopped. If a sync's events cannot be stored, the job update still lands and the server says so in its response. A database written by a newer version is refused at startup rather than downgraded.

## Board script reference

The orchestrator drives state through
`.agents/skills/factory/scripts/factory_board.py`, run from the target
repository. Output is JSON; exit code 2 means a rule was violated and `error`
says why. You normally never call it yourself except for the Claude setup.

| Command | Transition / effect |
|---------|---------------------|
| `init` | Create `.factory/`, add the Git exclude, refresh the dashboard. |
| `models <preset> \| <exp> <cheap> --cli <cli>` | Write `config.json`. |
| `new "<feature>"` / `new --from-backlog` [`--issue <url>`] | Create a job in `spec`. `--issue` records a GitHub issue link (`https://github.com/<owner>/<repo>/issues/<number>`, exactly that form: no `http`, other host, pull request, trailing slash, query or fragment; anything else exits 2 and creates no job). The dashboard shows it as an `owner/repo#<number>` link on the card and in the job viewer. |
| `spec-written <id>` | `spec` → `spec-review` (needs `prompt.md`, `spec.md`). |
| `spec-feedback <id> "<note>"` | `spec-review` → `spec`; writes `spec-feedback-N.md`. |
| `approve-spec <id>` | `spec-review` → `build`; marks `spec.md` approved and records the base commit. |
| `build-done <id>` | `build` → `test-audit` (needs `build.md` and a change since the base; writes the round snapshot), or → `needs-human` if `build.md` starts with `BLOCKED`. |
| `test-audit-done <id>` | Reads `round-N/test-audit.md` → `review` (returns the reviewers to `spawn`), or `build` on `CHANGES`. |
| `round-status <id>` | Never changes the stage: saves and prints reviewer verdicts, `invalid` files and whether the round is complete. |
| `close-round <id>` | Closes a complete round → `build` or `stride-review`. |
| `stride-review-done <id>` | Reads `round-N/review-stride.md` → `quality-gate`, or `build` on `CHANGES` (consumes a review round, same budget as the five reviewers). |
| `quality-gate-done <id>` | Runs `quality_gate.py` itself (no agent) → `approver`, or one gate-fix `build` round for fixable findings. Tamper entries never loop back. |
| `accept-suppression <id> <entry> <reason>` | Human only: accepts one loosened check recorded by the gate. |
| `decision <id>` | `approver` → `needs-human` (needs `ESCALATE`). |
| `rework <id> "<note>"` | `needs-human` → `build`; also marks `spec.md` approved. |
| `abandon <id> "<reason>"` | Any open stage → `abandoned`; records `abandoned_from`. |
| `archive <id> [reason]` | `needs-human` → `complete` (Archive); records `archived_from`. |
| `resume <id>` | Prints the next step for the job's current stage. |
| `record-model <id> <stage> <model>` | Note the model a stage actually ran on (stage must be known). |
| `show [<id>]` | Print the board or one job. |
| `install-claude [--claude-home DIR]` | Install the Claude skill pointer and subagents. |

## Customising

- **Change a stage's behaviour:** edit its file in `.agents/skills/factory/roles/`.
- **Change the loop or commands:** edit `.agents/skills/factory/SKILL.md`, and
  the matching rules in `factory_board.py` plus `test/test_factory_board.py`.
- **Add a model combo:** add an entry to `presets.json`.

## Limitations

- One job builds at a time in a single worktree.
- Preset model IDs are unverified defaults.
- Per-stage models depend on the CLI's subagent support.
- The full agent loop is verified manually per CLI; `npm test` covers only the
  board rules.
