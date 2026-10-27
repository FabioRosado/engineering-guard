# Engineering Guard Factory

**Status:** Revision 3 approved 2026-10-27; revision 4 (D11 test audit) implemented at developer request — awaiting explicit developer approval
**Revision:** 4 (2026-10-27)

Approval does not itself authorise implementation.

## Objective

Add `/engineering-guard-factory`, an orchestrator skill that drives a feature
through: spec → human spec approval → build → parallel reviews (max 2 rounds)
→ approver (always escalates) → human. Reuse existing Engineering Guard skills,
stay model/CLI agnostic (Claude Code, Codex, Kilo), and provide a minimal
visual dashboard.

### Acceptance criteria (proposed)

1. `models <preset>` (or `models <expensive> <cheap>`) persists the model
   choice in `.factory/config.json`; each stage spawn uses the configured model
   when the CLI supports it, and the board records when it fell back.
2. `<feature>` / `next` produce `jobs/<id>/prompt.md` and `spec.md`, then stop
   at stage `spec-review` until the human runs `approve-spec <id>`.
3. After spec approval the loop runs unattended: build → 4 reviews → wait for
   all → rework (≤2 rounds) → approver → `needs-human`.
4. Every review file starts with `VERDICT: PASS|CHANGES|N/A`; `decision.md`
   always starts with `ESCALATE`.
5. `approve <id>` is read-only: outputs a suggested branch name, commit
   message and PR description. No commit, push or merge.
6. `rework <id> <note>` reopens the build with the note as extra input.
7. Dashboard renders board.json stages, review chips per round, highlights
   `spec-review` and `needs-human`, and opens job markdown files.
8. Board transition rules are covered by stdlib `unittest` tests.

## Repository evidence

- Skills: `.agents/skills/*/SKILL.md` (Codex and Kilo discover this path).
  Claude Code uses `.claude/skills/` and `.claude/agents/` — not wired today.
- Packaging is Codex-only: `.codex-plugin/plugin.json`, README "Scope".
- Tooling is Python 3.9+ stdlib only; tests via `python3 -m unittest`
  (`package.json` `test`).
- `better-prompt` produces a prompt only and must not write files or invoke
  other skills (`.agents/skills/better-prompt/SKILL.md:8,59`); the orchestrator
  must therefore persist its output.
- `research` must not invent acceptance criteria; spec criteria are therefore
  explicitly proposals, which the human spec gate approves.
- `align` forbids autonomous approval — consistent with the spec gate and
  forced `ESCALATE`.
- `.codex/hooks/testing_guard.py` denies the first code/test write per session
  until policy delivery; Codex builder subagents will retry once (expected).
- No frontend in this repo; UX/UI reviewers will normally return `N/A`.

## Developer decisions

| # | Decision |
|---|----------|
| D1 | Option A: neutral role files + thin per-CLI adapters. |
| D2 | spec-writer = better-prompt → research (no new spec skill). |
| D3 | Model selection via named presets in `models`, with free-form `<expensive> <cheap>` override. |
| D4 | Builder lifecycle left to the agent → fresh builder per round (see R1). |
| D5 | UX and UI reviewers are conditional (`N/A` when no UI is touched). |
| D6 | Spec is human-gated; loop runs only after spec approval. |
| D7 | Add Claude Code support. |
| D8 | `approve` is read-only: suggests branch name (repo conventions), commit message, PR description. Human commits/pushes. |
| D10 | All factory artifacts are local dev tooling and must never be committed to the target repo. `.factory/` is excluded via `.git/info/exclude` (local, not `.gitignore`, so the target repo is not modified). Dashboard, presets and role files ship with the skill package and are copied into `.factory/` on first run. |
| D9 | Builder changes stay uncommitted on the current branch; no factory branch. Factory refuses to start a build on a dirty worktree (except `.factory/`). |

## Architecture (proposed)

```
.agents/skills/factory/
  SKILL.md                  # orchestrator: commands, loop, rules
  roles/spec-writer.md      # better-prompt then research → spec.md
  roles/builder.md          # implement + testing → build.md
  roles/review-security.md  # security skill → review-security.md
  roles/review-code.md      # verify skill → review-code.md
  roles/review-ux.md        # short checklist, conditional
  roles/review-ui.md        # short checklist, conditional
  roles/approver.md         # verify summary → decision.md (ESCALATE)
  presets.json              # named model combos
.claude/skills/engineering-guard-factory/SKILL.md   # thin pointer (D7)
.claude/agents/eg-*.md       # generated into the user-level ~/.claude/agents/
                             # (never the target repo, D10)
scripts/factory_board.py     # only writer of board.json
scripts/factory_sync_agents.py  # regenerates .claude wrappers from config
test/test_factory_board.py
.factory/                    # target repo, local only, in .git/info/exclude (D10)
  config.json  board.json  backlog.md  dashboard.html (copied from skill)
  jobs/<id>/prompt.md spec.md build.md round-N/review-*.md decision.md
```

### Stage → skill mapping

| Stage | Reuses | Model tier | Writes |
|-------|--------|-----------|--------|
| spec-writer | better-prompt, then research | expensive | prompt.md (by orchestrator), spec.md |
| builder | implement + testing | expensive | build.md + code changes |
| security | security | expensive | review-security.md |
| code | verify | cheap | review-code.md |
| ux / ui | role checklist | cheap | review-ux.md / review-ui.md |
| approver | verify (summary) | expensive | decision.md |

### Model presets (D3)

`presets.json` maps preset name → `{expensive, cheap}` per CLI, e.g.
`opus-sonnet`, `sonnet-haiku`, `sol-luna`, `luna`. `models <preset>` writes
the resolved pair to `.factory/config.json`; `models <a> <b>` writes raw IDs.
Unverified assumption: exact model IDs for each CLI, and the GPT "sol/luna"
names, must be confirmed during implementation. A preset unavailable on the
current CLI (e.g. GPT on Claude Code) is rejected with a message, not
silently substituted.

Per-CLI application:
- Claude Code: `factory_sync_agents.py` rewrites `model:` in `.claude/agents/eg-*.md`.
- Kilo: model passed at subagent spawn where supported.
- Codex: passed if the running version supports per-agent model; otherwise
  session default, recorded on the board as `model: "default (fallback)"`.

### Loop rules

- Agents read context only from job files; each writes only its own file.
- Orchestrator updates state only through `scripts/factory_board.py`, which
  validates verdict headers, round completeness (all 4 files present), the
  2-round cap, and forces `ESCALATE`.
- R1: fresh builder per round, reading `spec.md`, previous `build.md` and
  `round-(N-1)/*`. Resume is an optional optimisation, never required.
- After round 2 with outstanding CHANGES → approver still runs and escalates
  with unresolved findings listed.
- One job at a time (no concurrent worktrees). Reviewers diff the worktree
  against `HEAD`, recorded as the job's `base` on the board at build start;
  the board warns if `HEAD` moves mid-job.
- `next`/`<feature>` may queue and spec a job while another awaits human
  action, but a build starts only on a clean tree.

### Commands

```
models <preset> | <expensive> <cheap>
<feature>
next
approve-spec <job-id>
approve <job-id>            # read-only suggestion (D8)
rework <job-id> <note>
```

## Alternatives

| Option | Status | Rationale / revisit condition |
|--------|--------|-------------------------------|
| A. Neutral roles + adapters | Selected (D1) | Single source of truth; revisit if runtime model selection proves unreliable. |
| B. Native agent files per CLI | Rejected | Triplicated prompts drift. Revisit if A cannot pin models in practice. |
| C. Python driver calling CLIs headless | Deferred | Most code, couples to CLI flags. Revisit if deterministic unattended runs are required. |
| Resume same builder (SendMessage) | Rejected | Claude-specific; file-based context makes it unnecessary. |
| New spec-writer skill | Rejected (D2) | better-prompt + research already cover it. |
| Factory merges to main | Rejected (D8) | Human owns commit/push. |
| Branch `factory/<id>` (uncommitted or WIP commits) | Rejected (D9) | Simplicity preferred; revisit if parallel jobs or isolation are needed. |

## Testing and verification

- `test/test_factory_board.py`: verdict parsing, round completion, round cap,
  forced ESCALATE, spec gate blocks build, dirty-tree refusal (ignoring
  `.factory/`), `.git/info/exclude` entry added idempotently, invalid
  transitions rejected.
- `npm test` must stay green.
- Manual live run per CLI, logged with the README evaluation-record template.
- Dashboard: manual check via `python3 -m http.server` from `.factory/`.

## Open questions

- Q2 (non-blocking): confirm model IDs for each preset per CLI (implementation-time check).

## Risks

- Per-stage model pinning may be partial on Codex.
- Unattended builder can make broad edits; mitigated by spec gate, reviewers
  and human-only commit.
- README "Scope" (Codex-only) must be updated — scope statement changes.

## Implementation notes (post-approval, not a plan revision)

These local details changed during implementation and review. They stay
within the approved architecture and D10; flag if you consider any material.

- Board script lives in the skill (`.agents/skills/factory/scripts/factory_board.py`)
  so it ships with the package to other repositories.
- Claude support is installed user-wide by `factory_board.py install-claude`
  (`~/.claude/skills/engineering-guard-factory/` and `~/.claude/agents/eg-*.md`)
  instead of a repo-local `.claude/` pointer, which only worked in this checkout.
  Only `eg-builder` receives the `Edit` tool.
- `rework` also refuses while another job is active; the dashboard command binds
  to `127.0.0.1`.
- Usage documentation: `docs/factory.md`; live scenario: `demo/scenarios/factory.md`.

## Revision 4 change (developer request, 2026-10-27)

- **D11 (developer):** after the builder finishes, run the `testing` skill as a
  read-only **test-auditor** stage before the reviewers. It writes
  `round-N/test-audit.md` (`VERDICT: PASS|CHANGES`). `CHANGES` returns the job
  to the builder and consumes a round from the same 2-round budget; at the limit
  the reviewers run and the unresolved audit is carried as a board warning to the
  approver and human. Default model tier: cheap.
- This changes the approved loop. It was implemented at the developer's direct
  request; the revision-3 approval does not cover it, and the record awaits the
  developer's explicit confirmation of revision 4.
