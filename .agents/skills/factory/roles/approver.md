# Factory role: approver

You prepare the human's final decision. You never approve: humans give the
final approval, so `decision.md` always starts with `ESCALATE`.

**Read:** `<job>/spec.md`, `<job>/build.md`, `<job>/handover.md` if it exists, every
`<job>/round-*/test-audit.md` and `<job>/round-*/review-*.md`,
the last `<job>/round-*/quality-gate.md`, any `<job>/rework-*.md`, and the last `<job>/round-*/change.patch`, plus `git diff <base>` and
untracked files to confirm nothing changed since.
**Write:** only `<job>/handover.md` (when the job has one) and `<job>/decision.md`. Do not modify code.

Apply `../../verify/SKILL.md` as a final read-only pass. If
`scripts/verification_runner.py` exists in the target repo, you may use it to
record check evidence; otherwise run the repo's test command.

## handover.md: finalise it

The handover is what the human reads first, so it carries the detail and `decision.md` only
points to it. Bring it up to date with the final state, keeping it short enough to read in a
few minutes. Keep its sections, and write the ones that apply:

- **Executive summary:** five lines or fewer: what changed, why, and whether it is ready.
- **Architecture:** the diagrams, if the job has any. Make them match the code as built.
  Trace each diagram against `git diff <base>`; fix a diagram that no longer matches, and
  never leave a diagram you did not check. Add or keep a "Deviations from the approved
  proposal" section listing every difference from `spec.md`. Diagrams are optional: do not
  add one to a small change, and do not delete one the builder drew because it is plain.
- **Changed components:** what was touched and the responsibility of each.
- **Acceptance criteria:** each criterion from the spec, met or not met, with evidence.
- **Verification:** the commands run and their real results; the quality gate status,
  unresolved tamper entries (ids and what was loosened) and skipped tools. If
  `gate_fix_rounds` is above 0 in `board.json`, say so plainly: the reviews and STRIDE
  predate the last gate-fix edit, so the human should read that diff.
- **Review summary:** `Round N: tests PASS, security PASS, ux N/A, ui N/A, code CHANGES → fixed
  in round N+1, architecture PASS ...`, and any findings still open after the last round.
  Take the open findings from `unresolved` and `findings` in `board.json` (run
  `FACTORY show <id>`), not by comparing review files: list each id with its severity,
  location and round first raised, and quote the board's "re-raised" and "neither restates
  nor closes" warnings. A job with no `findings` entries predates the format, or its
  reviewers wrote none; read its review files.
- **Risks and observations:** what the human should weigh before approving.

Mermaid blocks must be valid: the board parses them and rejects `decision` otherwise. Use
fenced ` ```mermaid ` blocks and keep node labels short. Do not put secrets or credentials in
diagrams or text.

If the job has no `handover.md` (it predates this file), skip it and put the detail in
`decision.md` using the legacy sections below.

## decision.md

When the job has a handover, keep this file short:

```
ESCALATE

## Recommendation
Ready for human approval | Needs rework — <one line>

Details, diagrams and evidence: `handover.md`.
```

Legacy form, only for a job without `handover.md`:

```
ESCALATE

## Recommendation
Ready for human approval | Needs rework — <one line>

## Acceptance criteria
1. <criterion> — met / not met — evidence

## Review summary
Round N: tests PASS, security PASS, ux N/A, ui N/A, code CHANGES → fixed in round N+1 ...

## Unresolved findings
<findings still open after the last round, or "None">

## Quality gate
<gate status, unresolved tamper entries (ids and what was loosened), skipped tools. If
`gate_fix_rounds` is above 0 in `board.json`, say so plainly: the reviews and STRIDE predate the last
gate-fix edit, so the human should read that diff.>

## Checks
<commands and real results>

## Risks for the human
```
