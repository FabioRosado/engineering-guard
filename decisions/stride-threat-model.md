# STRIDE Threat Modeling — Standalone Skill + Factory Integration

**Status:** Approved 2026-10-28 (Revision 1)
**Revision:** 1 (2026-10-28)

Approval does not itself authorise implementation.

## Objective

1. Add a standalone `engineering-guard-stride` skill that performs systematic,
   trust-zone-grounded STRIDE threat modeling with a persistent, living
   threat register — complementing (not duplicating) the existing
   `engineering-guard-security` skill.
2. Integrate it into the software factory as a sequential, whole-repo gate
   that runs after the four parallel reviewers (security/ux/ui/code) and
   before the approver.
3. Add a severity floor to the factory's security-reviewer gate (and reuse
   it for the new STRIDE gate) so only CRITICAL/HIGH findings block a round.

### Acceptance criteria (proposed)

1. `engineering-guard-stride/SKILL.md` exists, follows this repo's skill
   format/voice (prose + numbered sections, not a slash-command template),
   includes the mandatory credential-safety block, and explicitly
   cross-references `security/SKILL.md` (scope boundary, not duplication).
2. `security/SKILL.md` gains a short cross-reference to STRIDE for
   systematic, whole-repo trust-boundary sweeps.
3. STRIDE persists its profile/report/tracker in a git-excluded local
   location (not committed `docs/`), following the `.factory/` precedent.
4. `factory_board.py`'s `check_verdict_file` enforces a severity floor for
   the `security` role (and the new `stride` role): `CHANGES` is accepted
   only when at least one finding declares `SEVERITY: CRITICAL` or
   `SEVERITY: HIGH`; MEDIUM/LOW/hardening-only findings must be `PASS` with
   notes.
5. A new factory stage `stride` runs once per job, after the review round
   that produces all-PASS/N/A from security/ux/ui/code, using the job's
   full accumulated diff (not per-round), before the approver. A `CHANGES`
   verdict (new/confirmed CRITICAL/HIGH on the changed component) sends the
   job back to the builder and consumes the existing 2-round review budget,
   identical to the other four reviewers.
6. `test/test_factory_board.py` covers: severity-floor parsing/rejection,
   the new `stride` stage's placement in the state machine, and its round
   accounting.
7. `npm test` stays green.

## Repository evidence

- `security/SKILL.md:161-169` already instructs the agent not to treat
  OWASP/CWE/ASVS as a complete or mandatory checklist and to consider
  application-specific threats beyond the named taxonomies. The skill's
  *instructions* are not Top-10-shallow; enforcement of "going deeper" is
  left entirely to agent discretion, with no structural mechanism forcing
  systematic coverage.
- `security/SKILL.md` and `roles/review-security.md` have no severity
  threshold for blocking: `roles/review-security.md:18-21` only requires
  "actionable findings" for `CHANGES`, and
  `factory_board.py:751-763` (`check_verdict_file`) only parses the verdict
  header (`PASS`/`CHANGES`), never the body's severity. Any actionable
  finding currently blocks a round regardless of severity.
- `factory_board.py:30,33-39,59-68,72-81` (`REVIEWERS`, `ALLOWED_VERDICTS`,
  `STAGE_TIERS`, `ROLE_STAGES`) hardcode the 4-reviewer set across multiple
  dictionaries; `test/test_factory_board.py` has ~15 call sites asserting
  the 4-reviewer `spawn` list. Adding a 5th *parallel* reviewer would touch
  all of these; a new *sequential* stage after the existing review round
  is architecturally cleaner and changes fewer invariants (no change to
  `REVIEWERS`/the wait-for-all list, only a new stage after `review`).
- `factory_board.py:395` refuses to start a build on a dirty worktree
  (decision D9); the only "uncommitted code" that exists during a job is
  the builder's own changes, already captured as `round-N/change.patch` /
  `files.txt`. A STRIDE pass scoped to "uncommitted code" would be
  functionally identical to the existing diff-scoped security reviewer and
  would forfeit STRIDE's distinguishing value (whole-repo trust-zone model,
  cross-diff boundary reasoning, e.g. a new endpoint added to an existing
  already-unauthenticated router, which a diff-only view cannot see).
- `docs/factory.md:180` and the dashboard's loopback-only binding show this
  repo already treats vulnerability-describing content as sensitive enough
  to keep out of casual/shared exposure; `.factory/` is excluded via
  `.git/info/exclude` specifically so nothing is committed
  (`decisions/engineering-guard-factory.md` D10). A living STRIDE register
  with open CRITICAL/HIGH findings and `file:line` evidence, committed to
  `docs/` as the source command specifies, conflicts with this established
  pattern.
- `check_verdict_file` (`factory_board.py:751-763`) is a single, small,
  role-keyed function already parameterized by `role` via
  `ALLOWED_VERDICTS`; extending it with a severity check is a localized
  change, not a redesign.

## Developer decisions

| # | Decision |
|---|----------|
| SD1 | Security-reviewer gate (and the new STRIDE gate) adds a severity floor: `CHANGES` requires at least one finding with a machine-checkable `SEVERITY: CRITICAL` or `SEVERITY: HIGH` line; MEDIUM/LOW/hardening-only findings are reported under `PASS`. Enforced by `factory_board.py`, not left to agent judgment alone. |
| SD2 | Confirmed: OWASP Top-10/CWE/ASVS remain discovery aids, not a mandatory checklist, in `security/SKILL.md` (no change) — STRIDE is the structural mechanism for systematic, forced-coverage depth beyond what Security's proportionate/discretionary model provides. |
| SD3 | The standalone STRIDE skill and the Security skill explicitly cross-reference each other's scope (Security: diff/feature-scoped, severity-prioritized; STRIDE: whole-repo, boundary-exhaustive, persistent register) to prevent silent duplication. |
| SD4 | STRIDE's profile/report/tracker persist in a git-excluded local location (pattern-matched to `.factory/`, e.g. a git-excluded `docs/stride/` or similar — exact path decided at implementation time, but must be added to `.git/info/exclude`, never committed). |
| SD5 | Factory integration: STRIDE is **not** diff-scoped to uncommitted code; it runs against the whole repo via its persisted/drift-checked profile. Diff-scoping was considered and rejected (see Alternatives) because it would collapse STRIDE into a redundant copy of the existing security reviewer. |
| SD6 | STRIDE runs as a new **sequential** factory stage (`stride`), once per job, after the four parallel reviewers all reach PASS/N/A and before the approver — not as a 5th parallel reviewer in the existing wait-for-all set. |
| SD7 | STRIDE's gate gives a `CHANGES`-equivalent verdict when it finds a new or newly-confirmed CRITICAL/HIGH threat touching the job's changed component. That verdict blocks like the other four reviewers and consumes the same 2-round review budget (not a non-blocking warning-only stage). |

## Architecture (proposed)

```
.agents/skills/stride/
  SKILL.md                      # standalone skill: profile, lifecycle, report phases
.agents/skills/factory/
  roles/review-stride.md        # new role: applies ../../stride/SKILL.md to the job's
                                 # full diff + whole-repo profile, writes stride.md
  scripts/factory_board.py      # add `stride` role/stage; severity-floor parsing
                                 # in check_verdict_file (shared by security + stride)
  SKILL.md                      # update loop diagram + stage table
docs/factory.md                 # update loop diagram
decisions/engineering-guard-factory.md  # revision note: new `stride` stage added
```

### Updated factory loop (proposed)

```
feature ─► spec-writer ─► [HUMAN approve-spec] ─► builder ◄──────────────────┐
                                                     │                        │
                                               test-auditor ── CHANGES ───────┤
                                                     │ PASS                   │
                       ┌─────────────┬───────────────┼─────────────┐          │
                       ▼             ▼               ▼             ▼          │
                   security         ux              ui           code        │
                       └─────────────┴──── WAIT FOR ALL ───────────┘          │
                                             │ all PASS/N/A (≤2 review rounds) ┘
                                             ▼
                                          stride (whole-repo, once per job) ──CHANGES──┘
                                             │ PASS (no new CRITICAL/HIGH)
                                             ▼
                                          approver ─► ESCALATE ─► needs-human
```

- `stride` reads the job's full accumulated diff since `base` (same
  `change.patch`/`files.txt` mechanism, computed fresh against the final
  round) plus the persisted whole-repo profile (refreshed for drift, not
  rebuilt from scratch every job).
- `stride`'s `CHANGES` sends the job back to `build`, consuming a review
  round from the same `attempt.review_rounds` budget used by the four
  parallel reviewers (SD7) — no new separate budget.
- At the 2-round limit with outstanding STRIDE `CHANGES`, behavior matches
  existing rounds-exhausted handling: the approver still runs and
  escalates with the open finding listed (consistent with how security/
  ux/ui/code already behave at the round limit).

### Severity-floor mechanism (SD1)

`check_verdict_file` is extended so that, for roles configured as
severity-gated (`security`, `stride`), a `CHANGES` verdict is only valid
when the body contains at least one line matching
`SEVERITY:\s*(CRITICAL|HIGH)`. A `CHANGES` body containing only
`SEVERITY: MEDIUM`/`LOW`/no severity line is rejected by the board script
(same mechanism as the existing "CHANGES needs at least one finding"
check), forcing the reviewer to either substantiate a CRITICAL/HIGH
finding or verdict `PASS` with the lower-severity items as notes.
`ux`/`ui`/`code`/`tests` keep their current, non-severity-gated validation.

## Testing and verification

- `test/test_factory_board.py`: new cases for severity-floor acceptance/
  rejection on `security` and `stride` roles; `stride` stage placement
  (runs once, after review close, before approver); round-budget
  consumption on `stride` `CHANGES`; round-limit-exhausted handling with
  an open `stride` finding.
- `npm test` must stay green.
- Manual live run per CLI for the new `stride` role spawn, logged with the
  README evaluation-record template (per existing project convention for
  skill changes).

## Alternatives

| Option | Status | Rationale / revisit condition |
|--------|--------|-------------------------------|
| STRIDE as a 5th parallel reviewer in the existing wait-for-all set | Rejected | Requires touching `REVIEWERS`, `ALLOWED_VERDICTS`, `STAGE_TIERS`, `ROLE_STAGES`, and ~15 existing test assertions; forces an architecture-wide, stateful tool into a diff-scoped, per-round, stateless reviewer slot it doesn't fit (loses the persistent-profile value, or pays its cost every round for no benefit). Revisit only if a future requirement needs STRIDE findings to appear in the *same* round as the other four for UI/workflow reasons. |
| STRIDE scoped to uncommitted/diff-only code in the factory | Rejected | The factory already forces a clean worktree at build start (D9); the only uncommitted content during a job is the round diff, already covered by the existing security reviewer. Diff-scoping STRIDE would make it redundant rather than complementary, and forfeits its only differentiator (whole-repo, cross-diff boundary reasoning). Revisit only if evidence shows the whole-repo sweep is too slow/costly in practice to run per job. |
| STRIDE report/tracker committed to `docs/` (as the source command specifies) | Rejected | Conflicts with this repo's established pattern of not persisting vulnerability-describing content in committed/casually-exposed locations (`.factory/` exclusion, loopback-only dashboard, D10). Revisit if the developer explicitly wants a durable, shareable, git-tracked vulnerability register instead. |
| Severity floor as agent judgment only (no board-script parsing) | Rejected (per SD1) | Relies on the reviewing agent correctly self-regulating severity under time/token pressure — the same discretion gap that motivated adding STRIDE's structural coverage in the first place; inconsistent with that reasoning if the security gate itself stays judgment-only. Revisit if the `SEVERITY:` line proves too rigid a format for real findings. |
| STRIDE `CHANGES` as non-blocking, warning-only in `decision.md` | Rejected (per SD7) | Would let a job reach the approver/human with an unaddressed CRITICAL/HIGH architectural threat, inconsistent with how the other four reviewers gate. Revisit if STRIDE's false-positive rate in practice proves too high to trust as a hard gate. |

## Open questions

- Exact git-excluded path for STRIDE's profile/report/tracker (SD4) —
  deferred to implementation; must be added to `.git/info/exclude`
  following the `.factory/` precedent, not committed.
- Exact wording/location of the Security↔STRIDE cross-reference text
  (SD3) — deferred to implementation, content only, no architectural
  decision needed.
- Whether other repos consuming Engineering Guard as a package (via the
  Codex plugin) need a migration note for the new `stride` stage appearing
  in their factory loop — non-blocking, address in `docs/factory.md`
  update during implementation.

## Risks

- Severity-floor parsing (`SEVERITY: CRITICAL|HIGH`) adds a format
  reviewers must follow; a reviewer forgetting the line on a genuine
  CRITICAL finding would cause an incorrect `PASS`. Mitigate by keeping
  the role file's instruction explicit and the regex visible in error
  messages the board script returns.
- Whole-repo STRIDE sweep per job adds latency/cost to the factory loop
  tier `expensive` (profile-aware sweep), even with drift-only refresh.
  Accepted trade-off per SD5/SD6 evidence above.
- A STRIDE false positive at the 2-round limit still reaches the human via
  the approver's escalation, same safety net as other reviewers — not a
  new risk class.

## Plan revision and approval status

**Status:** Approved 2026-10-28, Revision 1, in full.
All decisions above (SD1–SD7) were selected by the developer in the Align
session via direct confirmation of the recommended options, then the
developer explicitly approved the complete Revision 1 record (not merely
individual decisions) for implementation.
