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
                       ┌──────────────┬───────────────┼──────────────┐         │
                       ▼              ▼               ▼              ▼         │
                   security          ux              ui            code       │
                       └──────────────┴── WAIT FOR ALL ┴─────────────┘         │
                                               │ all PASS/N/A (≤ 2 review rounds) ┘
                                               ▼
                                            stride (whole-repo, once per job) ──CHANGES──┘
                                               │ PASS (no new CRITICAL/HIGH)
                                               ▼
                                            approver ─► ESCALATE ─► needs-human
```

| Stage | Reuses | Default tier | Writes |
|-------|--------|--------------|--------|
| spec-writer | better-prompt, then research | expensive | `prompt.md`, `spec.md` (reads `feature.md`) |
| builder | implement + testing | expensive | code changes, `build.md` |
| test-auditor | testing (audit mode) | cheap | `round-N/test-audit.md` |
| security | security | expensive | `round-N/review-security.md` |
| ux | UX checklist (`N/A` if no user-facing change) | cheap | `round-N/review-ux.md` |
| ui | UI design checklist (`N/A` if no visual change) | cheap | `round-N/review-ui.md` |
| code | verify | cheap | `round-N/review-code.md` |
| stride | stride (whole-repo threat model) | expensive | `round-N/review-stride.md`, plus its own git-excluded profile/report |
| approver | verify (final pass) | expensive | `decision.md` |

Rules enforced by the board script:

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
- A round closes only when all four reviews exist and are valid. The
  builder is never restarted mid-round.
- Any review `CHANGES` sends the job back to a fresh builder; each attempt
  (initial build or rework) gets two review rounds. After that the approver
  runs with the open findings listed.
- After the four reviewers all pass (or N/A), **stride** runs once against
  the job's full diff and the repository's whole trust-zone model — not once
  per round. Its `CHANGES` (a new or newly-confirmed CRITICAL/HIGH threat on
  a changed component) sends the job back to the builder and consumes the
  same two-round budget as the other reviewers.
- `decision.md` must start with `ESCALATE`: the human always decides.
- `approve-spec` rewrites the spec's `Status` line to `Approved`, because
  builders read the spec file, not the board.
- A build must change something. A builder that cannot proceed starts
  `build.md` with `BLOCKED: <reason>` and the job goes straight to
  needs-human instead of spending review rounds on an empty change.
- The build only starts on a clean worktree (ignoring `.factory/`), and only
  one job can be building at a time.

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
| `archive <id> [reason]` | Close an approved **needs-human** job and move it to Archive. |
| `abandon <id> <reason>` | Close a job for good, for example after a crash; it stops blocking new builds. Code changes stay in the worktree. |

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
   Check the acceptance criteria and the `UI impact` line.
3. `/engineering-guard-factory approve-spec 001-add-rate-limiting-to-the-login-endpoint`
4. Watch the dashboard. When the job reaches **needs-human**, read
   `decision.md`, the reviews, and `git diff`.
5. Either `rework <id> "<what to change>"`, or `approve <id>` and use the
   suggested branch, commit message and PR description to commit yourself.
   Approving also archives the job, including the same action from the
   dashboard's **Archive job** button.

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
  dashboard.html     # copied from the skill on every run
  jobs/001-<slug>/
    feature.md  prompt.md  spec.md  spec-feedback-N.md  build.md  decision.md  rework-N.md
    round-1/change.patch  files.txt  test-audit.md  review-security.md  review-ux.md  review-ui.md  review-code.md  review-stride.md
```

The STRIDE reviewer also maintains its own profile and living threat
register at a separate, git-excluded location in the target repository
(see `.agents/skills/stride/SKILL.md`) — that state persists across jobs
and is not part of any single job's folder.

## Dashboard

### Central Dashboard (Recommended)

The central factory server aggregates all jobs across your active repositories into one unified view. Start it once with:

```
/factory-server start
```

Then visit **http://localhost:5173/** to see all in-progress and archived jobs grouped by repository. Each factory automatically pushes updates when state changes—no per-repository setup needed. A job that reaches **needs-human** can be archived straight from its modal with **Archive job**; the reason is recorded and the repository's board is updated.

This is the recommended way to monitor multiple repositories without managing separate dashboard instances.

### Per-Repository Dashboard (Optional)

For a single repository's dashboard, run:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 -d .factory
```

Open <http://localhost:8000/dashboard.html>. Jobs are cards across the stage columns (Pipeline view) or grouped by repository (Grouped view); each round shows a `tests` chip followed by reviewer chips (green PASS, amber CHANGES, grey N/A or pending). Jobs waiting on you (spec-review, needs-human) are outlined in teal. Click a card to read its markdown files, fetched on demand from `jobs/<job-id>/<file>`. The dashboard tries the central server's `/api/jobs` endpoint first; when that's unavailable (as under this plain static server, which has no backend) it falls back to polling `board.json` directly every two seconds. Static mode is read-only, so use the central dashboard to archive a job from the modal. Keep it bound to `127.0.0.1`: specs, security reviews and STRIDE's living threat register can describe unfixed vulnerabilities. STRIDE's profile and report live outside `.factory/`, at a separate git-excluded location, so they are not shown by this dashboard.

## Board script reference

The orchestrator drives state through
`.agents/skills/factory/scripts/factory_board.py`, run from the target
repository. Output is JSON; exit code 2 means a rule was violated and `error`
says why. You normally never call it yourself except for the Claude setup.

| Command | Transition / effect |
|---------|---------------------|
| `init` | Create `.factory/`, add the Git exclude, refresh the dashboard. |
| `models <preset> \| <exp> <cheap> --cli <cli>` | Write `config.json`. |
| `new "<feature>"` / `new --from-backlog` | Create a job in `spec`. |
| `spec-written <id>` | `spec` → `spec-review` (needs `prompt.md`, `spec.md`). |
| `spec-feedback <id> "<note>"` | `spec-review` → `spec`; writes `spec-feedback-N.md`. |
| `approve-spec <id>` | `spec-review` → `build`; marks `spec.md` approved and records the base commit. |
| `build-done <id>` | `build` → `test-audit` (needs `build.md` and a change since the base; writes the round snapshot), or → `needs-human` if `build.md` starts with `BLOCKED`. |
| `test-audit-done <id>` | Reads `round-N/test-audit.md` → `review` (returns the reviewers to `spawn`), or `build` on `CHANGES`. |
| `round-status <id>` | Never changes the stage: saves and prints reviewer verdicts, `invalid` files and whether the round is complete. |
| `close-round <id>` | Closes a complete round → `build` or `stride-review`. |
| `stride-review-done <id>` | Reads `round-N/review-stride.md` → `approver`, or `build` on `CHANGES` (consumes a review round, same budget as the four reviewers). |
| `decision <id>` | `approver` → `needs-human` (needs `ESCALATE`). |
| `rework <id> "<note>"` | `needs-human` → `build`; also marks `spec.md` approved. |
| `abandon <id> "<reason>"` | Any stage → `abandoned`. |
| `archive <id> [reason]` | `needs-human` → `abandoned` (Archive); records `archived_from`. |
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
