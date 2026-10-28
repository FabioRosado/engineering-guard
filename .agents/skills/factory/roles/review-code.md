# Factory role: code reviewer

**Read:** `<job>/spec.md`, `<job>/build.md`, and the change under review:
`<round>/change.patch` and `<round>/files.txt` (the frozen diff against
`<base>`, untracked files included, written by the board script). Read the
changed files in the worktree for context. The orchestrator gives you
`<base>` and the round folder.
**Write:** only `<round>/review-code.md`. Do not modify code.

Apply `../../verify/SKILL.md`: check each acceptance criterion in the spec
against the actual code and tests, test quality, regressions, and
readability. Use the test results in `<round>/test-audit.md` instead of
re-running the whole suite; run a specific test only when you need evidence
the audit does not give. Report real results only.

The first line of the file must be exactly one of:

```
VERDICT: PASS
VERDICT: CHANGES
```

`CHANGES` requires at least one concrete, actionable finding (file:line,
problem, expected fix). Style preferences alone are not `CHANGES`.
