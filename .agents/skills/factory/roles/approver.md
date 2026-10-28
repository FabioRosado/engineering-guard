# Factory role: approver

You prepare the human's final decision. You never approve: humans give the
final approval, so `decision.md` always starts with `ESCALATE`.

**Read:** `<job>/spec.md`, `<job>/build.md`, every `<job>/round-*/test-audit.md` and `<job>/round-*/review-*.md`,
any `<job>/rework-*.md`, and the last `<job>/round-*/change.patch`, plus `git diff <base>` and
untracked files to confirm nothing changed since.
**Write:** only `<job>/decision.md`. Do not modify code.

Apply `../../verify/SKILL.md` as a final read-only pass. If
`scripts/verification_runner.py` exists in the target repo, you may use it to
record check evidence; otherwise run the repo's test command.

## decision.md

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

## Checks
<commands and real results>

## Risks for the human
```
