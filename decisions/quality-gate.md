# Quality Gate

**Status:** Revision 2 — accepted by the developer 2026-10-30 ("accept and let's implement"); Revision 1 superseded
**Revision:** 2 (2026-10-30)

Approval does not itself authorise implementation.

## Objective

Agents skip policy rules that are only advisory text (single-character names,
decorative banners, loosened tests). Add a deterministic **quality gate**: one
script that agents and humans both call, which inspects the uncommitted change,
runs the repository's own checks, and writes a readable JSON report. Findings
must be fixed, never loosened or bypassed. The factory calls the gate at fixed
transitions so a builder cannot skip it.

Delivery order requested by the developer: (1) audit existing scripts,
(2) implement the verify guard, (3) introduce a shared quality-gate command,
(4) wire it into the factory.

### Acceptance criteria (proposed)

1. A single command runs the gate and prints versioned JSON; exit code is 0
   when no check failed, non-zero otherwise. Humans and the factory run the
   same script.
2. Built-in rules (stdlib only) run on the changed code and fail the gate on:
   decorative comment banners, secret-shaped literals, swallowed errors
   (`except: pass` and equivalents), and removed assertions, deleted tests or
   newly added skips.
3. Single-character and generic identifiers produce **warnings**, each listed
   with file and line. The builder must address every warning in `build.md`
   (fix it or justify it); the gate verifies the section lists every warning ID.
4. The gate runs the repository's own lint, format, type and test commands as
   declared in a gate config, reusing `verification_runner.py` for execution.
5. Optional external scanners (gitleaks, bandit) run when installed. When a
   tool is absent the gate **warns** with an install hint and records the check
   as `skipped`. A missing tool never turns into a pass and never fails the gate.
6. Loosening moves (suppression comments, linter/scanner config edits, lowered
   thresholds, weakened tests) are recorded in a **tamper ledger**. The gate
   fails while any entry is unresolved; only a human accepts one, with a reason,
   via a board command. Acceptance is stored in the board.
7. *(Revision 2)* The factory runs the gate once per job, after STRIDE and before the
   approver, as a new `quality-gate` stage run by the board script itself (not an agent),
   so it is not repeated on every build/test iteration and cannot be skipped or
   overridden by an LLM verdict. Fixable findings send the job to one gate-fix build
   round; tamper entries go straight to the human.
8. Gate behaviour is covered by stdlib `unittest` tests that run the real script
   against disposable git repositories, as the existing scripts are tested.

## Repository evidence (observed 2026-10-30)

- `scripts/verification_runner.py` runs only explicitly requested npm scripts,
  emits JSON, and states it records execution evidence only (`assessment:
  execution_evidence_only`). It does not judge sufficiency. It lives in this
  repo's `scripts/`, outside the factory skill, so a target repo does not have it.
- `.codex/hooks/testing_guard.py` delivers policy text and never reads file
  contents or diffs (README L69-73).
- `factory_board.py` is the sole writer of `board.json`; it validates file shape
  (verdict headers, severity floors) but no stage runs a script except the git
  snapshot in `build_done`. Insertion points: `build_done` (after
  `write_change_snapshot`, before the stage moves to `test-audit`),
  `test_audit_done` (between verdict parse and the `CHANGES` branch),
  `close_round`, `decision`.
- `factory_board.py` locates its own files through `SKILL_ROOT`
  (`factory_board.py:27`) and runs from the target repo root.
- No skill states "do not loosen or bypass a check". The nearest rules are
  test-specific (`testing-policy.md:17`).
- No policy states a rule about single-character names or banners. The policy
  says conventional short names are fine "where unambiguous"
  (`implement/SKILL.md:89-92`), so single-character checks are warnings.
- Tooling on this machine: ruff, black, pylint, mypy, bandit, coverage, pytest
  are installed (in another project's environment); gitleaks, semgrep and
  detect-secrets are not.
- External tool facts (web sources, 2026-10-30): gitleaks is MIT, a single Go
  binary, scans stdin or directories, and is described by its author as feature
  complete with security patches only. Bandit is Apache 2.0 and Python-only.
  Semgrep Community Edition analyses within a single function or file, and
  remote rule packs report metrics unless `--metrics=off`.

## Developer decisions

| # | Decision |
|---|----------|
| D21 | The gate lives in `.agents/skills/factory/scripts/` so it ships with the factory (developer: "agreed"). |
| D22 | Single-character and generic names are warnings; the agent must go through each one (developer). |
| D23 | Handover validation and architecture checks are out of scope for now (developer: "next thing, ignore for now"). |
| D24 | Tamper handling: the gate lists everything that loosened a check; the developer reviews the list and accepts or rejects each item (developer). |
| D25 | Built-in rule language scope follows the recommendation: Python via `ast`, JS/TS via regex, language-agnostic regex for other text (developer: "use whatever is recommended"). |
| D26 | Missing optional external tools **warn**, they do not fail (developer: "lets not do fail close, lets show a warning since folks may want to install extra dependencies or not"). This supersedes the earlier fail-closed answer. |
| D27 | *(Revision 2)* The gate runs after STRIDE and before the human, not on every build/test iteration, to keep the build loop short (developer). |
| D28 | *(Revision 2)* Findings that need human review (tamper entries) are not sent back to the builder; fixable findings get one more build round (developer: "run another build loop to fix any findings unless they are human review required"). |

## Agent recommendations (not yet decided by the developer)

- **R1.** Include gitleaks and bandit as the supported external tools, both
  optional per D26. Gitleaks is language-agnostic and fits scanning the frozen
  `change.patch`; bandit is relevant only when the diff touches Python.
- **R2.** Defer semgrep. Its free-tier security analysis is limited, remote
  rules send metrics by default, and the built-in rules already cover the
  policy-specific checks.
- **R3.** Do not evaluate the gitleaks successor (Betterleaks) in this change;
  the tool list is data in the gate config, so swapping is cheap later.
- **R4.** Reuse `verification_runner.py` for executing repo checks rather than
  forking it, by moving or referencing it from the skill. Packaging detail left
  to implementation, with the constraint that a target repo must be able to
  run the gate without this repository's `scripts/`.
- **R5.** Treat a tool's *absence* and a tool's *findings* differently. Absence
  warns (D26). Findings always fail. Built-in rules always run, so a missing
  external tool never reduces their coverage.

## Architecture (proposed)

**`quality_gate.py`** (new, stdlib only, in the factory skill) composes four
layers and emits one report:

1. **Built-in diff rules** on the changed files and `change.patch`: hard-fail
   rules (banners, secret-shaped literals, swallowed errors, weakened or
   deleted tests, new skips) and warning rules (single-character and generic
   names, outside loop and comprehension variables and `_`).
2. **Tamper detection**: suppression comments, config edits, lowered
   thresholds, removed gate-relevant scripts; each becomes a ledger entry with
   an ID, file, line, rule and the exact change.
3. **Repository checks** declared in a gate config (lint, format, types, tests),
   executed through the runner's mechanism. Undeclared checks report
   `not_configured`.
4. **Optional external tools** (gitleaks, bandit) detected on `PATH`. Absent
   tool: `status: skipped`, warning with install hint.

Report shape (versioned JSON): overall `status`, per-check `pass | fail | warn |
skipped | not_configured`, `warnings[]` with stable IDs, `tamper[]` with IDs and
acceptance state. Exit code non-zero when any check is `fail` or any tamper
entry is unresolved.

**Command surface:** `npm run quality` runs the same script locally.

**Board changes (`factory_board.py`), Revision 2:**
- New stage `quality-gate` between `stride-review` and `approver`.
  `stride_review_done` now moves to `quality-gate` (on PASS, or when the review
  budget is spent) instead of `approver`.
- New command `quality-gate-done <job>` runs the gate script itself and records
  the report at `round-N/quality-gate.json`:
  - gate passes: continue to `approver`;
  - gate fails with fixable findings and the gate-fix budget (1) unspent: back to
    `build` for one gate-fix round, then `quality-gate` again;
  - budget spent: continue to `approver` with the findings carried as warnings;
  - unresolved tamper entries never loop back: they continue to `approver` and
    appear in `decision.md` for the human.
- New command `accept-suppression <job> <id> "<reason>"`, stored in the job.
  Orchestrator instructions forbid agents running it, the same way as `approve-spec`.
- Because a gate-fix round changes code after the reviews, `decision.md` must state
  when a gate-fix round happened so the human knows the reviews predate the last edit.
- Warning acknowledgement: `build.md` of a gate-fix round must list every warning ID.

## Alternatives

| Option | Status | Rationale / revisit condition |
|--------|--------|-------------------------------|
| A. Extend `verification_runner.py` with rule checks | Rejected (proposed) | Blurs its explicit "execution evidence only" contract and it is not shipped with the factory. Revisit if the runner is moved into the skill and its contract is deliberately widened. |
| B. New `quality_gate.py` in the factory skill, reusing the runner | Proposed | Matches the "script validates, LLM judges" stance (`engineering-guard-factory.md`, option C deferred). Ships with the skill; testable like existing scripts. |
| C. Only wire existing tools through `package.json` and the current runner | Rejected (proposed) | Cannot express diff-based rules or tamper detection and enforces nothing. This is the status quo that failed. |
| D. Pre-commit or Stop hook | Rejected (proposed) | Hook support is uneven across Codex, Kilo and Claude Code (README disclaims CLI hook support) and the factory never commits. Revisit for plain sessions outside the factory. |
| Gate after every build (`build_done`/`test_audit_done`), Revision 1 | Superseded (D27) | Lengthens every build/test iteration. Revisit if late findings prove costly to fix. |
| Gate fix reruns the full loop (tests, reviews, STRIDE) | Rejected (proposed) | Safest but recreates the long loop D27 avoids. Revisit if gate-fix edits are seen to introduce defects that reviewers would have caught. |
| Fail-closed on missing external tools | Rejected (D26) | Developer wants a warning so users can choose whether to install extras. Revisit if a missing scanner ever lets a leak through unnoticed; the report already makes `skipped` visible. |
| Semgrep as a supported tool | Deferred (R2) | Revisit with a concrete JS/TS or polyglot SAST need and a decision on offline rules and `--metrics=off`. |
| Hard-fail on single-character names | Rejected (D22) | Policy allows unambiguous short names; false positives push agents to bypass. |

## Constraints and trade-offs

- **Stdlib only for the core.** README L36 and L140 promise no third-party
  packages, and `engineering-guard-factory.md:40` records stdlib-only tooling.
  D26 keeps this promise: external tools are optional. No amendment needed.
- **"Never loosen or bypass" is enforceable only partially.** The tamper ledger
  catches the loosening moves, but the board script cannot identify who ran
  `accept-suppression`. "Human only" is enforced by instruction and by the
  orchestrator rules, not cryptographically. Recorded as a known risk.
- **Warning-only external tools reduce coverage silently if ignored.** Mitigation:
  `skipped` appears in the report and the orchestrator summary. This is an
  accepted consequence of D26.
- **Regex rules for JS/TS are approximate.** Python uses `ast`. JS/TS false
  positives and negatives are expected; hard rules are limited to patterns that
  are unambiguous in text.
- **Per-check timeout** in the runner is 120 s; large repos may need a configured
  limit.
- **Security:** reports and the tamper ledger may quote code and could contain
  secret-shaped text. Findings must redact matched values (store file, line and
  rule only), consistent with the credential-safety rule.

## Implementation steps

1. Move or reference the runner so a target repo can run the gate (R4); keep its
   JSON contract and tests intact.
2. Implement `quality_gate.py`: built-in rules, tamper ledger, config loading,
   optional tool detection, versioned JSON report.
3. Add `npm run quality`.
4. Add the `quality-gate` stage, `quality-gate-done` and `accept-suppression` to the
   board; add the warning-acknowledgement check for `build.md`.
5. Update the builder and test-auditor roles and `factory/SKILL.md` to run the
   gate, fix findings rather than loosen them, and never run
   `accept-suppression`.
6. Document in `docs/factory.md` and README; note the amended verification flow.

## Testing and verification

- Real-subprocess `unittest` tests against disposable git repositories, per the
  existing pattern: each hard rule fires on a positive case and stays quiet on a
  negative case; warning rules do not fail the gate; a missing external tool
  yields `skipped` and a warning with exit code unchanged; a present tool's
  finding fails the gate; each tamper move creates a ledger entry and fails until
  accepted; acceptance clears only that entry.
- Redaction test: a secret-shaped literal appears in the diff, and the report
  contains no matched value.
- Factory tests: STRIDE PASS moves to `quality-gate`; a failing gate sends the job to
  one gate-fix build round and then back to the gate; a spent budget continues to the
  approver with warnings; tamper entries do not loop; the gate is not run in earlier
  stages; the central sync is disabled in tests (`FACTORY_DISABLE_CENTRAL_SYNC`).
- `npm test` stays green; manual run of `npm run quality` on this repo.

## Non-goals

Handover validation and architecture checks (D23); semgrep (R2); a pre-commit or
Stop hook; enforcing who may run `accept-suppression`; coverage-delta analysis
beyond reporting runner evidence; changing existing role verdict formats.

## Open questions and risks

1. **Gate config format and location.** Per-repo file name and schema are not yet
   chosen (non-blocking; implementation proposal subject to review).
2. **Generic-name list.** The set of names flagged as generic (`data`, `tmp`,
   `val`, `res`, `obj`) needs your review before it ships (non-blocking).
3. **Runner packaging** (R4): moving it changes a file the README documents.
4. **Risk:** warning-only external tools can be ignored. **Risk:** regex JS/TS rules
   are approximate.
5. **Reviews predate the gate-fix edit.** A gate-fix round changes code after the reviewers and STRIDE ran. Mitigated by the gate re-running and by `decision.md` disclosing it; not eliminated.
6. **Existing-test interaction:** `FACTORY_DISABLE_CENTRAL_SYNC` must be honoured in
   any new test.

## Implementation notes (2026-10-30)

Implemented as approved in Revision 2, with these deviations and findings:

- **R4 not followed: the runner is not reused.** `verification_runner.py` lives outside the
  factory skill and its execution core is private to npm scripts. The gate runs declared
  commands with `subprocess.run` (argv list, no shell, 300 s timeout, output tail kept). The
  runner is unchanged. Revisit if the runner is later moved into the skill.
- **Declared checks can be scoped to changed files.** A `{changed}` argument expands to the changed
  files that exist, filtered by a per-check `suffixes` list in `.quality-gate.json`. Found by
  running the gate on this repo: a repo-wide `ruff check` failed on two errors in a file the change
  never touched, which would trap any job in a repository with existing lint debt. Type and test
  commands stay repo-wide. This extends criterion 4; it does not change an approved boundary.
- **Suppression detection reads real comments only.** Python uses `tokenize`; JS/TS matches after
  `//` or `/*`. Python markers must start the comment text. Skip detection for Python tests uses
  `ast`. Both were found by running the gate on its own code: text scanning flagged the gate's
  own pattern definitions, documentation and test fixtures.
- **The central-server push now uses `http.client`** instead of `urllib.request.urlopen`
  (bandit B310 on `factory_board.py`). The scheme is fixed by construction, and the non-blocking
  failure contract (D15) is unchanged. Verified against an isolated live server and with nothing
  listening. No `# nosec` was added, which the gate itself would have recorded as tamper.
- **Gate-fix round state:** `quality_gate` is `pending | pass | warn | fail | fixing`;
  `gate_fix_rounds` counts gate-fix builds so the approver can tell the human the reviews predate
  the last edit. Acceptances live in `accepted_tamper` (id to reason and time).
- **Dashboard** gains a `quality-gate` column and a GATE chip (gate status mapped onto the existing
  verdict colours; `warn` still shows as passing).

Verified: `npm test` 102 passing (65 before). Each of the gate's key behaviours was mutation-checked
(secret redaction, missing tool never failing, per-entry acceptance, tamper never looping to the
builder, gate-fix build skipping tests and reviews, comment-token and AST detection, changed-file
scoping). One vacuous test was written and replaced during the work.

Not verified: gitleaks was not installed, so its integration path (stdin scan of the patch with
`--redact`) has not been executed. The gate was exercised on this repo but no full factory job has
been run through the new stage with a live agent.

Known follow-ups: the gate currently fails on this repo until you accept the new
`.quality-gate.json` (`config-edit`); the generic-name list and `.quality-gate.json` schema are
implementation proposals awaiting your review; README documentation of the gate is not yet written.

## Post-implementation changes (2026-10-30, requested by the developer; not a new approved revision)

Found by running the gate against a real repository (`model-pipelines`):

- **bandit is scoped to added lines.** It scanned whole files, so existing B108 hits in files a job
  merely touched failed the gate. The gate now runs `bandit -f json` and keeps only issues whose
  `line_range` intersects the added lines, the same rule every other check follows. A file bandit
  cannot parse (JSON `errors`, exit 0) now fails instead of passing, and unreadable output fails.
  Accepted trade-off: an existing line made unsafe by an edit elsewhere is not reported.
- **A failed check explains itself.** `quality-gate.md` omitted a failed check's output, so a failure
  such as bandit's showed only `bandit: fail`. It now prints the output tail for failed checks.
- **`quality_gate.py --init` proposes `.quality-gate.json`.** Criterion 4 still holds: commands run only
  if declared. `--init` reads files (never runs a command), prefers the repository's own entry point
  (Make target, npm script, then a configured tool), recognises only a fixed allowlist of names so
  `system-test` and `deploy-*` are never proposed, proposes format in check mode only, and never
  overwrites. A human reviews and commits the result before a job, so the trust boundary
  (`config-edit` is tamper) is unchanged. Rejected: detecting at run time with no file, because the
  commands would come from files an agent in the same job may have edited and there would be no place
  for a human to correct a wrong guess.
- `not_configured` messages now name `--init`.

Not changed, found while testing: `test_missing_optional_tool_warns_with_install_hint_and_does_not_fail`
fails on any machine where git and gitleaks share a directory (it keeps git's directory on `PATH` to
hide gitleaks). It failed before these changes and is not fixed here.

## Revision and approval status

**Status:** Revision 2 accepted by the developer on 2026-10-30 ("accept and let's implement").
**Developer decisions:** D21-D28. **Recommendations R1-R5** were accepted together with
the revision ("accept").
**Approved revision:** 2. **Approval date:** 2026-10-30.
**Note:** the developer's wording accepted the revision as a whole; the placement change
(D27/D28) was proposed by the developer and recorded here before implementation.
