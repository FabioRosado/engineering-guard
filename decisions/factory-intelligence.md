# Factory Intelligence: Structured Findings, Role Contracts, Spec Fields, Conditional Specialists

**Status:** Approved 2026-10-30 (Revision 3)
**Revision:** 3 (2026-10-30)

The developer explicitly approved the complete Revision 3 on 2026-10-30. Approval applies
to this revision only; a material change to the architecture, scope or acceptance criteria
invalidates it and needs a new decision. Approval does not itself authorise implementation.

Items marked *(developer)* were stated by the developer; items marked *(proposal)* are
agent recommendations that the approval of Revision 3 adopts as the plan, not as
independent developer preferences.

Revision 2 resolved the four open questions from revision 1 (D46-D49) and replaced the
UX skip rule after testing it against real job data. Revision 3 resolves Q5 and Q6
(D50, D51), adds criterion 12, and records the `config.json` overwrite fix found during
the pre-approval check.

## Objective

Make the factory's judgement more reliable without making simple jobs more expensive.
Four questions from the developer, each with a decision below:

1. Should roles have explicit contracts (responsibility, inputs, outputs, permissions,
   blocking conditions)?
2. Should the spec carry acceptance criteria, edge cases, scope boundaries and
   architectural implications, and do `research` / `better-prompt` already do this?
3. Should more conditional specialists exist, like the UX/architecture reviewers?
4. Does each round track findings, convergence, unresolved items, blocked state and
   escalation at the limit?

### Acceptance criteria (proposed)

1. A reviewer finding is a structured record the board can read: stable ID, severity,
   location, status. The narrative stays free text.
2. From those records the board reports, per round, which findings are open, newly
   raised, closed, and re-raised after being closed, with no LLM judgement.
3. At escalation the approver and the human receive the named list of open findings from
   the board, not a prose warning.
4. A reviewer may report `BLOCKED` (could not assess) as a distinct verdict. It stops the
   job and sends it to the human, as the builder's `BLOCKED` does (D46).
5. Each role file declares its contract in one parsed header; the board derives
   `ALLOWED_VERDICTS`, `SEVERITY_GATED_ROLES`, `STAGE_TIERS`, `EDITING_ROLES` and
   `ROLE_STAGES` from it instead of restating them.
6. After each stage the board detects files written outside the role's declared `writes:`
   and records a warning (detection, not prevention).
7. The spec template gains Edge cases, Assumptions, Compatibility and Verification plan
   fields, each omitted when empty.
8. UX and UI reviewers reference their skill, share the CRITICAL/HIGH severity floor, and
   have the tiered skip rule in P4 instead of "UX always runs". A change that touches
   frontend code always keeps both on.
9. A design-time architect reviews the proposal before the job reaches `spec-review`,
   **advisory only**, when the spec says `Architecture impact: yes` (D48).
10. A data/migration reviewer runs only when changed paths match migration/schema
    patterns.
11. A job that triggers no conditional specialist spawns no more agents than it does
    today. This counts spawned agents only: structured findings (P1) and write-scope
    detection (P2) still add board processing on every job and a `FINDING:` line to
    reviewer output on every `CHANGES`.
12. `ui_directories` set in `.factory/config.json` survives a later `models` run.

## Repository evidence (observed)

Source: `factory_board.py`, `roles/*.md`, `quality_gate.py`, `decisions/*.md`, tests.

| Area | Observation | Reference |
|---|---|---|
| Per-round verdicts | Recorded in `history` as verdict tokens only | `factory_board.py:868-870` |
| Budgets | `attempt = {review_rounds, test_rebuilds, gate_fixes}`; caps 2 / 1 / 1 | `:57-62` |
| Limit behaviour | Job moves on; unresolved state is a prose warning; approver forced to `ESCALATE` | `:741, :914, :956, :1051` |
| Finding content | Board reads the first line and checks the body is non-empty. Nothing else is parsed except `SEVERITY:` lines for security/stride | `check_verdict_file`, `:1236-1259` |
| Finding identity | Exists only in the quality gate (`finding_id`, hash of rule/path/detail) | `quality_gate.py:184-187` |
| Role facts duplicated | `REVIEWERS`, `ALLOWED_VERDICTS`, `STAGE_TIERS`, `ROLE_STAGES`, `SEVERITY_GATED_ROLES`, SKILL.md table, Claude install | `factory_board.py:34-134`; adding one reviewer touched ~8 places (`factory-visual-handover.md`, Implementation steps) |
| Write permission | Only `builder` lacks `Edit` withheld on Claude. Every role gets `Write` and `Bash`. Kilo and Codex apply no tool restriction | `:1198-1201` |
| UX/UI roles | 23-24 lines, no `Apply ../../<skill>` reference, no severity floor | `roles/review-ux.md`, `review-ui.md` |
| Architecture reviewer | Already exists and is wired in end to end. It compares proposal with as-built only and explicitly does not assess design quality | `review-architecture.md:3-4, :22`; D35-D36 |
| Spec template | Objective, Findings, Approach, Criteria, UI impact, Architecture impact, Out of scope, Open questions | `spec-writer.md:27-39` |
| `research` / `better-prompt` | Already consider constraints, compatibility, failure paths, boundary and regression cases; `research` forbids inventing criteria | `research/SKILL.md:22-50`, `better-prompt/SKILL.md:34` |

### Real factory data (observed, read-only, sibling repos)

Five real jobs in `../ai-core*/.factory/` (52 verdict files):

| Fact | Evidence |
|---|---|
| Verdict mix: 32 PASS, 16 N/A, 4 CHANGES | `grep '^VERDICT:'` over all round files |
| **All 4 `CHANGES` came from the test auditor.** No reviewer ever returned `CHANGES` | same |
| Findings are long, narrative and self-numbered ("Finding 1", "### 1. ... (blocker)", mutation labels M1-M10) | `002-.../round-1/test-audit.md`, `AISAGE-720/.../round-1/test-audit.md` |
| Findings are fixed and re-verified across rounds ("survived" in round 1, "killed" in round 2) | `001-.../round-2/test-audit.md` |
| Round 3 was reached by a human `rework`, not by the review budget | `001-.../rework-3.md`, `attempt.review_rounds = 1` |
| No job contains `review-architecture.md`; the reviewer has never run on real work | file listing |
| Specs already contain Observed / Inferred / Unknown and Rejected / deferred sections beyond the template | `001-.../spec.md` |
| Specs have `UI impact` but none has `Architecture impact` (jobs predate it) | `grep` over `*/spec.md` |
| Every changed file in all 12 round snapshots was `.py`, `.sql`, `.md` or `.toml`; UX was spawned for each and returned `N/A` | `round-*/files.txt`, `review-ux.md` |
| `USER_FACING_SUFFIXES` already includes `.js .jsx .ts .tsx .vue .svelte .html .css`, so frontend code already keeps **UI** on. `.js`/`.ts` are also backend, so Node services keep it on needlessly | `factory_board.py:78-82` |
| Job 003 changed API error text callers read (`message="Internal server error"`) in `.py` files. The patch adds 12+ string literals, most of them log lines, and UX correctly returned `N/A` | `003-.../round-1/change.patch`, `review-ux.md` |

**Not observed / limits.** No job in the data has ever had a reviewer `CHANGES`, so the
convergence behaviour of the five reviewers is untested on real work; only the test
auditor's cross-round behaviour is evidenced. Five jobs from one project and one
developer is a small sample. Kilo/Codex tool enforcement was not tested.

## Developer decisions

| # | Decision | Date |
|---|---|---|
| D41 | Reviewer findings become a **structured record** (with narrative alongside). *(developer)* | 2026-10-30 |
| D42 | Write-scope violations are handled by **post-hoc detection**, not tool restriction. *(developer: "do the recommended")* | 2026-10-30 |
| D43 | The spec gains four extra fields (Edge cases, Assumptions, Compatibility, Verification plan). *(developer: "accept extra fields")* | 2026-10-30 |
| D44 | The pre-approval architect is **advisory**, not blocking. *(developer: "happy with advise perhaps?"; agent agrees, rationale below)* | 2026-10-30 |
| D45 | Specialist cost principle: **agents match the task**; a simple job should not run all of them. Every conditional specialist needs a deterministic trigger. *(developer)* | 2026-10-30 |
| D46 | A reviewer's `BLOCKED` stops the job and sends it to the human. *(developer: "do blocked so humans can review")* | 2026-10-30 |
| D47 | A finding may be marked `closed` only by the role that raised it. *(developer: "accept recommended")* | 2026-10-30 |
| D48 | The advisory architect runs **before** the job reaches `spec-review`, so its verdict is visible on arrival. *(developer: "lets do before")* | 2026-10-30 |
| D49 | UX/UI should run when frontend/JavaScript code is touched; the developer asked to try to identify user-facing change automatically. The tiered rule in P4 is the agent's proposal under that direction, not a developer-chosen mechanism. *(developer direction; mechanism is a proposal)* | 2026-10-30 |

| D50 | No repo-level frontend-manifest check; UX/UI trigger from changed paths and the spec only. *(developer: Q5 "go with recommended")* | 2026-10-30 |
| D51 | The UI directory list is configurable per repo in `.factory/config.json` (`ui_directories`), with the agent's default list. *(developer: Q6 "yes make configurable")* | 2026-10-30 |

D41-D51 are direction. The mechanisms below are proposals until the revision is approved.

## Proposed design *(proposal)*

### P1. Structured findings (D41)

Each reviewer and the test auditor adds one line per finding to its `CHANGES` body, and
to any open finding under `PASS`:

```
FINDING: <id> | SEVERITY: <level> | LOCATION: <path[:line]|none> | STATUS: open|closed|disputed
```

- **The ID is assigned and reused by the reviewer, never hashed from text.** Real
  findings are long and reworded between rounds, so a content hash would give a new ID
  every round. The reviewer reads the previous round's file, reuses the ID of a
  finding it is re-checking, and mints a new one only for a new problem. The board
  verifies the convention rather than computing the identity.
- ID format `<role>-<n>` (for example `tests-2`, `security-1`), unique per job and role.
- `STATUS: closed` is written by the reviewer that verified the fix, in the later round,
  and **only by the role that raised the finding** (D47). The board rejects a `closed`
  for an id whose prefix is another role's, so one reviewer cannot erase another's finding.
- `STATUS: disputed` is the builder's rebuttal recorded in `build.md`, already allowed by
  `builder.md:27-28`; the reviewer then confirms or reopens.
- **`BLOCKED` (D46).** A reviewer that cannot assess writes `VERDICT: BLOCKED` with a
  one-line reason first. `close-round` treats it like the builder's `BLOCKED`
  (`factory_board.py:679`): the job moves to `needs-human` with a warning naming the
  reviewer and reason, and no further rounds are spent. It is valid for every reviewer
  and the test auditor, not for the approver (which always escalates). The reason is
  required: a bare `BLOCKED` is rejected as a bare `CHANGES` is today. On a human
  `rework` the budgets reset and the blocked reviewer is re-spawned.
- The narrative stays free text. The board never parses the prose.

Board behaviour (all deterministic):

| Signal | Rule |
|---|---|
| Open set per round | ids with `STATUS: open` in that round's files |
| Newly raised | id absent from every earlier round |
| Closed | id was open earlier, `closed` now |
| **Re-raised** | id `closed` earlier, `open` now: the oscillation signal |
| Lost | id open in round N-1, absent in round N with no `closed`: the reviewer silently dropped it; board warns |
| Unresolved at limit | open ids after the last round, named in `job["unresolved"]` and passed to the approver |

`check_verdict_file` already parses `SEVERITY:` lines for security and stride
(`:1252`); this extends the same technique and keeps the CRITICAL/HIGH gate.

New state: `job["findings"]` (id → role, severity, location, first_round, last_round,
status), derived by the board on `round-status`, `test-audit-done` and `close-round`.

### P2. Role contract header (D42)

Each `roles/*.md` starts with a fixed front-matter block:

```
---
stage: security
tier: expensive
writes: [round-N/review-security.md]
verdicts: [PASS, CHANGES, BLOCKED]
severity_floor: HIGH
may_be_na: false
edits_code: false
---
```

The board loads these at start-up and derives `ALLOWED_VERDICTS`,
`SEVERITY_GATED_ROLES`, `STAGE_TIERS`, `EDITING_ROLES`, `ROLE_STAGES` and the reviewer
list. This removes five hand-maintained tables rather than adding a document.

**Write-scope detection (D42).** Before each spawn the board records the set of changed
paths (`git status`, plus a listing of `.factory/`). After the stage it diffs the two
and warns on any path outside the role's `writes:` (builder: code is allowed, `.factory/`
only `build.md` and `handover.md`). This works on all three CLIs and **cannot prevent**
a write; it makes one visible to the human. Warning, not rejection, so a false positive
cannot strand a job.

### P3. Spec fields (D43)

Add to `roles/spec-writer.md`, each omitted when empty:

- **Edge cases:** each tied to a criterion number, or marked `no criterion, for human
  decision`. Never silently promoted to a requirement.
- **Assumptions:** separate from Open questions, so the human can reject one.
- **Compatibility:** public contracts, migrations, behaviour other callers rely on.
- **Verification plan:** the command and evidence that count as proof.
- **User-facing surface:** any CLI output, prompt or message a human reads, including in
  backend files. Drives the UX trigger in P4. Omitted when there is none.

`research` and `better-prompt` are **not changed**: they are general skills used outside
the factory, and the information loss is in the spec template, not the skills. Real
specs already include Observed/Inferred/Unknown and Rejected/deferred sections, so the
spec-writer is partly doing this unprompted; P3 makes it consistent.

### P4. Strengthen UX and UI (D45)

- Add `Apply ../../<skill>` references and the severity floor (`SEVERITY: CRITICAL|HIGH`
  to justify `CHANGES`), so a cosmetic note passes with notes instead of spending a round.
- **Tiered UX/UI trigger (D49).** Today UI is skipped on `UI impact: no` plus no
  user-facing suffix, and UX **never** is, because extensions cannot see CLI output
  (`write_automatic_not_applicable_reviews`). Real data shows that costs one spawn per
  round for jobs that are purely `.py`/`.sql`. Tested alternatives:

  | Signal | Reliable? | Evidence |
  |---|---|---|
  | Frontend suffix changed (`.jsx .tsx .vue .svelte .html .css`) | **Yes** | Already used for UI |
  | `.js`/`.ts` changed | **Partly**: also backend Node | `factory_board.py:78-82` |
  | "Diff adds a string literal" | **No** | Job 003 adds 12+ literals, mostly log text; cannot separate log, exception and user text |
  | Spec says `UI impact: yes` | **Yes**, human-approved | Spec field |
  | Path under a conventional UI directory (`components/`, `pages/`, `views/`, `templates/`, `static/`, `public/`, `ui/`, `web/`, `frontend/`, `cli/`) | **Mostly** | Heuristic; misses unconventional layouts |
  | Spec names a CLI, prompt or message as user-facing | **Yes**, if the spec-writer records it | New spec field, below |

  Rule (D50, D51). **UX and UI both stay on** if any of: the spec says `UI impact: yes`;
  a changed file has a frontend suffix (`.jsx .tsx .vue .svelte .astro .html .htm .css
  .scss .sass .less .hbs .erb .jinja .j2`); or a changed `.js`/`.ts` file sits under a
  UI directory. **UX alone** (UI skipped) stays on when the spec lists a user-facing
  surface under the **User-facing surface** field (CLI output, prompt, message).
  Otherwise both are `N/A`, written by the board. There is **no repo-level frontend
  manifest check** (D50): a `package.json` naming a UI framework would keep UI on for
  every change in a full-stack repo, including pure backend files, against D45.

  **UI directories are configurable (D51).** The default list is `components/`,
  `pages/`, `views/`, `templates/`, `static/`, `public/`, `ui/`, `web/`, `frontend/`,
  `cli/`; it is a heuristic chosen by the agent, not found in the repository. A repo
  overrides it with `ui_directories` in `.factory/config.json`.

  **`models` must not erase it.** `models()` builds a fresh dict and overwrites the whole
  file (`factory_board.py:529-536`), so any other key is lost on the next `models` run.
  The implementation must read the existing config and carry `ui_directories` (and any
  other non-model key) across, with a test that runs `models` twice and asserts the
  setting survives. `backfill_missing_stages` already rewrites the file and needs the
  same care.

  The fallback for the one case the board cannot detect (a backend change to text a
  human reads) is the spec: the spec-writer must name any user-facing surface, and the
  human approves that at the spec gate. Job 003 shows the safe default: its spec said
  `UI impact: no`, and the UX reviewer correctly agreed.

  **Accepted risk:** a change to user-visible text in a backend file, with a spec that
  does not name it, skips UX. This is the same failure mode as a wrong `UI impact: no`
  today, now covering UX too. It is mitigated by the spec gate, not eliminated.
- Add **User-facing surface** to the spec fields in P3 (a fifth optional field).

### P5. Conditional specialists (D44, D45)

**Design-time architect (advisory).** Trigger: spec says `Architecture impact: yes`.
Per D48 it runs **before** the job reaches `spec-review`: `spec-written` validates the
spec as today, then (when triggered) moves the job to a new stage `spec-architecture`
and returns `spawn: ["spec-architect"]`. The architect writes
`spec-review-architecture.md`; `spec-architecture-done` validates its verdict header,
records its verdict and findings as board warnings, and only then moves the job to
`spec-review`. It cannot block `approve-spec`: its verdict is `PASS`, `CHANGES` or `N/A`
for display, and `CHANGES` does not send the job back to the spec-writer. Cost accepted
under D48: one more agent before the human gate, on `Architecture impact: yes` jobs only.

This adds one pipeline stage, so `PIPELINE_STAGES`, `ACTIVE_STAGES` handling,
`resume`, the dashboard column list (`ui/src/lib/jobs.js`) and tests need matching
entries. It is not an `ACTIVE_STAGES` member for the one-job-at-a-time rule, because it
touches no code and precedes the build baseline.

Why advisory (D44): the spec gate is already a human gate (D6). A blocking AI review in
front of it adds a second approval authority and lets a model veto a spec the human has
not read, which conflicts with D8 and the principle in `approver.md` that the factory
never approves. The cost of advisory is that the human can ignore it; the mitigation is
that its output is shown at the gate, not buried in a file.

Scope of its checklist (distinct from the existing as-built reviewer): boundary and
dependency direction against decision records, coupling, whether an existing component
already supports the behaviour, simpler alternative. Uses the `research` skill's
pattern guidance, which already says not to recommend a pattern merely because it is
recognised.

**Data/migration reviewer.** Trigger: any changed path matches migration/schema/model
patterns (same mechanism as `USER_FACING_SUFFIXES`). Skipped automatically otherwise,
with the board writing the `N/A` as it does for UI and architecture.

**Cost principle (D45).** A job that triggers neither runs the same agents as today
(criterion 11). Both specialists are skipped by the board, not by an agent, so a skipped
specialist costs nothing.

## Alternatives

| Option | Status | Evidence and rationale | What would reopen it |
|---|---|---|---|
| Hash finding text to derive IDs | **Rejected** | Real findings are long and reworded between rounds, so hashes change every round (`002-.../round-1/test-audit.md`). Assumption that IDs would be stable was tested and found false | A reviewer format short enough to hash |
| Reviewer assigns and reuses IDs, board verifies | **Proposed** | Matches how reviewers already self-number findings. Unverified: whether LLM reviewers reuse IDs reliably across fresh spawns | Measured ID-reuse failures (see Verification) |
| Replace prose with structured-only findings | **Rejected** | Real findings carry mutation tables and reasoning that a record would lose | None expected |
| Separate `contracts/*.yaml` per role | **Rejected** | A second source of truth that drifts from the role prose unless something reads it | None |
| Header block in each role file, parsed by the board | **Proposed** | One source; replaces five duplicated tables | Parsing proves fragile across CLIs |
| Tool restriction for write scope | **Rejected (D42)** | Claude only; Kilo and Codex apply none | A second CLI gains per-agent tool control |
| Post-hoc write detection | **Proposed (D42)** | Works on every CLI; cannot prevent | Silent damage from a reviewer write is observed |
| Change `research` / `better-prompt` | **Rejected** | General skills; gap is in the spec template | The skills are used only by the factory |
| Blocking pre-approval architect | **Rejected (D44)** | Second approval authority in front of a human gate | Human reports advisory output is routinely ignored and harmful |
| Performance reviewer | **Deferred** | No deterministic trigger; `better-prompt` forbids inventing targets | A spec states a measurable performance goal |
| API/contract reviewer | **Deferred** | No reliable language-agnostic detection of public interfaces | Per-language detectors exist |
| Docs reviewer | **Rejected** | Low severity; adds noise per job | None |
| Separate accessibility reviewer | **Rejected** | Already inside UX (`review-ux.md:21`) | Accessibility becomes a compliance requirement |
| Dependency/supply-chain reviewer | **Deferred** | Partly covered by the quality gate and security | A lockfile-change incident |
| Adding reviewers that always run | **Rejected (D45)** | Roughly 11 agent invocations for a no-rework job already | None |
| UX trigger from "diff adds a string literal" | **Rejected** | Tested on real job 003: 12+ literals, mostly log text; log, exception and user text are indistinguishable in a diff | A language-aware detector that separates logging calls from user output |
| UX trigger from file extension alone | **Rejected** | Skips UX on a Python CLI or prompt change; `.js`/`.ts` are also backend | None |
| UX always runs (current) | **Rejected (D45, D49)** | Spawned and returned `N/A` in every round of every real job reviewed | The spec field proves unreliable (see risks) |
| Tiered rule: frontend suffix, spec `UI impact`, UI directory, spec-named surface | **Proposed (D49, D50, D51)** | Uses only signals the board can read plus a human-approved spec field | Measured spec-writer omissions |
| Frontend-manifest check (`package.json` names a UI framework) | **Rejected (D50)** | Keeps UI on for every change in a full-stack repo, including pure backend files; works against D45 | A repo where nearly every change is user-visible |
| Hard-coded UI directory list only | **Rejected (D51)** | The list is an agent heuristic, not found in the repo; layouts vary | None |
| Reviewer `BLOCKED` as a warning only | **Rejected (D46)** | A reviewer that could not assess did not approve | None |
| Any reviewer may close any finding | **Rejected (D47)** | One reviewer could erase another's finding | None |
| Architect runs after the spec reaches `spec-review` | **Rejected (D48)** | Human may read and approve before the verdict arrives | The extra pre-gate wait proves too costly |

## Constraints and trade-offs

| Aspect | Constraint | Mitigation |
|---|---|---|
| Backwards compatibility | Existing jobs and the five real jobs have no `FINDING:` lines | Missing lines mean "no structured findings"; board falls back to current behaviour. No migration of old jobs |
| Reviewer burden | More output format to follow | Board rejects a `CHANGES` with no `FINDING:` line, as it rejects a bare `CHANGES` today (`:1246`) |
| ID drift | A fresh reviewer may mint a new ID for an old problem | "Lost" and "newly raised" signals are warnings, not blockers; measure before tightening |
| Spec length | Four fields may double the spec; it must stay approvable "in a few minutes" (`spec-writer.md:43`) | Omit empty fields; flag edge cases with no criterion rather than inventing criteria |
| Detection is not prevention | A reviewer can still write outside its file | Warning shown to the human; D42 accepted this |
| Advisory architect | May be ignored | Surfaced as a warning at `spec-review`, the human gate |
| Dashboard | The UI hard-codes reviewer chips and stages (`ui/src/lib/jobs.js`) | Updated with each new specialist, as for architecture (D35); the `spec-architecture` stage needs a column and `BLOCKED` needs a chip state |
| New stage | `spec-architecture` is an eleventh pipeline stage; `PIPELINE_STAGES` is mirrored in `ui/src/lib/jobs.js` | Update both together; add `resume` and board tests for the stage |
| `BLOCKED` verdict | `ALLOWED_VERDICTS`, `VERDICT_HEADER` and every role's first-line rule currently know only PASS/CHANGES/N/A | Add `BLOCKED` through the P2 contract header so it is declared per role, not hard-coded |
| `config.json` overwrite | `models()` replaces the whole file, so a user-set `ui_directories` would vanish | Read-merge-write in `models()` and `backfill_missing_stages`; regression test (criterion 12) |
| Existing jobs | In-flight jobs have no `User-facing surface` field and no `FINDING:` lines | Missing field means "none declared"; an in-flight job keeps today's UX behaviour (always on) so a rule change cannot hide a review mid-job |

## Implementation steps *(proposal, in order)*

1. **P1 structured findings** and its board tests, including re-raised, lost and
   unresolved cases, and the old-job fallback. Highest leverage; unblocks the approver.
2. **P3 spec fields.** One role file; smallest change.
3. **P2 contract header** and derived tables, then write-scope detection. Shares
   parsing work with step 1.
4. **P4 UX/UI strengthening**: skill references and severity floor first (no behaviour
   risk), then the tiered skip rule. The skip rule depends on the P3
   `User-facing surface` field, so P3 must ship first, and the rule should not be
   enabled until the spec-writer measurement in the risks section is done.
5. **P5 design-time architect** (new `spec-architecture` stage), then the
   data/migration reviewer, each with a board trigger and a skip rule.
6. **`BLOCKED` verdict** with P2, since it is declared in the contract header.

Steps are shippable independently; step 1 does not depend on the others.

## Verification and testing (expected)

- Board tests with real parsing, no mocks: structured finding extraction; re-raised and
  lost detection across rounds; unresolved list at the budget limit; `CHANGES` without a
  `FINDING:` line rejected; old jobs without findings still progress.
- A contract-header test that every `roles/*.md` parses and that the derived tables equal
  today's hand-written ones before the old tables are deleted.
- Write-scope test with a stage that writes an undeclared file, asserting the warning.
- **ID-reuse measurement:** run P1 on a few real jobs and count how often a reviewer
  reuses the correct ID versus minting a duplicate. This is the main unverified risk and
  should gate making "lost" a hard rule.
- `BLOCKED`: a reviewer `BLOCKED` moves the job to `needs-human` with a warning naming
  the reviewer; a bare `BLOCKED` is rejected; `rework` re-spawns it; the approver cannot
  return it. A `closed` finding from a non-raising role is rejected (D47).
- UX/UI trigger tests with real parsing: each signal in P4 keeps both on; a pure
  `.py`/`.sql` change with no spec surface skips both and the board writes `N/A`; a
  `.py` change with a declared **User-facing surface** keeps UX on and skips UI; an
  in-flight job keeps UX always on; a `package.json` naming a UI framework does **not**
  by itself keep UI on (D50).
- `ui_directories`: a configured directory keeps a `.js` change on; the default list
  applies when unset; `models` run twice leaves `ui_directories` intact; so does
  `backfill_missing_stages`. This one is a regression guard for the overwrite found in
  `factory_board.py:529-536`.
- `spec-architecture` stage: `spec-written` routes to it only on `Architecture impact:
  yes`; `spec-architecture-done` rejects a bad verdict header; `CHANGES` still reaches
  `spec-review` and never returns to the spec-writer; `resume` names the stage.
- **Spec-writer measurement:** run it against real job 003's feature text and check it
  names the error-message surface under **User-facing surface**. This gates enabling the
  skip rule.
- Dashboard test for any new chip or column. `npm test` and the quality gate stay green.

## Open questions and risks

Resolved in revision 2: former Q1 (`BLOCKED` stops the job, D46), Q2 (only the raising
role closes, D47), Q3 (tiered UX/UI rule, D49 and P4), Q4 (architect runs before
`spec-review`, D48).

Resolved in revision 3: former Q5 (no manifest check, D50) and Q6 (configurable list,
D51).

Open, non-blocking (do not change the architecture; decide during implementation):

- The default UI directory list is a heuristic. Whether a `.js`/`.ts` file under `web/` or
  `public/` is really UI varies by repo; the `ui_directories` override is the remedy.
- Whether `ui_directories` entries match as path prefixes or as any path segment. Prefix
  is stricter and less likely to misfire; segment catches nested layouts such as
  `services/x/ui/`. Recommend segment match, with a test for both.

Risks:

- **The UX skip now depends on an LLM-written field.** The spec-writer must name any
  user-facing surface for a backend-only change to keep UX on. If it omits one, UX is
  skipped and the human is the only safeguard. Measure before relying on it: run the
  spec-writer against the real jobs (003 is the test case) and check it names the error
  message surface.
- The "Accepted risk" in P4 widens the existing `UI impact: no` blind spot to UX.
- **Plan size against thin evidence.** Six shippable steps, one new pipeline stage, a
  state-machine change and a config change, resting on five real jobs from one project
  in which no reviewer returned `CHANGES`. Each step ships independently, so the
  implementation should stop and re-measure after step 1 rather than treat all six as
  one commitment. This is a recommendation to the implementer, not a change to scope.
- The data/migration reviewer has one supporting example in the real data (job 001,
  one `.sql` migration) and the least evidence of the five additions.

- Only the test auditor has produced `CHANGES` in real data, so reviewer-side convergence
  is untested. P1 may therefore be mostly exercised by one role in practice.
- LLM ID reuse across fresh spawns is unverified.
- The data/migration trigger is path-based and will miss migrations in unconventional
  locations.
- This extends a state machine that already has ten stages; each new stage needs
  matching UI, resume and tests.

## Not changed

- The 2-review-round, 1-test-rebuild and 1-gate-fix budgets.
- The forced `ESCALATE` and human-only approval, commit and archive.
- `research`, `better-prompt` and every non-factory skill.
