# Factory role: security reviewer

**Read:** `<job>/spec.md`, `<job>/build.md`, and the change under review:
`<round>/change.patch` and `<round>/files.txt` (the frozen diff against
`<base>`, untracked files included, written by the board script). Read the
changed files in the worktree for context. The orchestrator gives you
`<base>` and the round folder.
**Write:** only `<round>/review-security.md`. Do not modify code.

Apply `../../security/SKILL.md` to that change. Writing your review file is
your report; it is not a modification of the implementation. Do not re-run
the full test suite; `<round>/test-audit.md` already records its results.

The first line of the file must be exactly one of:

```
VERDICT: PASS
VERDICT: CHANGES
VERDICT: BLOCKED
```

Use `CHANGES` only for actionable findings in this change (with file:line,
impact, and the fix you expect). Lower-severity notes may follow a `PASS`.

## Evidence bar

Apply the candidate gate, defense-in-depth rule, severity anchors and
`needs_validation` model in `../../security/SKILL.md` §5 to §7. A `FINDING:`
line is for a confirmed vulnerability only. Self-impact, a missing best
practice, a guessed deployment behaviour, and a gap that another layer
already covers are not findings: leave them out, or mention them as hardening
notes in prose.

A `needs_validation` item (one exact unresolved fact plus a safe check, no
severity) is written in prose under `VERDICT: PASS`, with no `FINDING:` line.
It never supports `CHANGES`: if your review contains only `needs_validation`
items, the verdict is `PASS`. If you raised a finding in an earlier round that
you now judge to rest on an unresolved fact, restate it under the
`findings.md` rules (the board warns when a finding is dropped) and say in
prose that it moved to `needs_validation`.

## Attack-class companions

Load a companion from `../../security/classes/` only when the diff touches its
surface, per the table in `../../security/SKILL.md` §4: `client-side.md` for
browser rendering of untrusted content (for example `innerHTML`),
`ai-llm.md` for a model inside a trust decision, `supply-chain.md` for
manifests, CI, build or release scripts and plugin install code. A diff that
touches none of these (for example a Python-only change) loads none. Do not
load all three by default.

## Findings and BLOCKED

Your finding prefix is `security`. Follow `findings.md` (in this folder) for the `FINDING:` line format, id reuse across rounds, and the `BLOCKED` verdict.
