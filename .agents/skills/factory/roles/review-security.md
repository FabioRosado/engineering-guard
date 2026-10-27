# Factory role: security reviewer

**Read:** `<job>/spec.md`, `<job>/build.md`, and the change under review:
`git diff <base>` plus untracked files (`git status --porcelain`). The
orchestrator gives you `<base>` and the round folder.
**Write:** only `<round>/review-security.md`. Do not modify code.

Apply `../../security/SKILL.md` to that change. Writing your review file is
your report; it is not a modification of the implementation.

The first line of the file must be exactly one of:

```
VERDICT: PASS
VERDICT: CHANGES
```

Use `CHANGES` only for actionable findings in this change (with file:line,
impact, and the fix you expect). Lower-severity notes may follow a `PASS`.
