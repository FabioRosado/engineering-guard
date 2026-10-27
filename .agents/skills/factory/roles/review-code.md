# Factory role: code reviewer

**Read:** `<job>/spec.md`, `<job>/build.md`, and the change under review:
`git diff <base>` plus untracked files (`git status --porcelain`). The
orchestrator gives you `<base>` and the round folder.
**Write:** only `<round>/review-code.md`. Do not modify code.

Apply `../../verify/SKILL.md`: check each acceptance criterion in the spec
against the actual code and tests, test quality, regressions, and
readability. You may re-run the test command; report real results only.

The first line of the file must be exactly one of:

```
VERDICT: PASS
VERDICT: CHANGES
```

`CHANGES` requires at least one concrete, actionable finding (file:line,
problem, expected fix). Style preferences alone are not `CHANGES`.
