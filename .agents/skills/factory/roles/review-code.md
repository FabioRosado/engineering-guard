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

**Regression check.** Compare the diff against the spec's acceptance
criteria: does it change any existing behaviour, public contract, or adjacent
code path that the acceptance criteria do not call for? If the spec is a bug
fix, the fixed behaviour is expected to change — that is not a regression.
An unrelated behaviour change is. For each one found, record in your file:

```
## Regression: <short name>
Behaviour before -> after: <...>
Required by an acceptance criterion? yes/no
Impact: <who/what breaks, and how>
```

The first line of the file must be exactly one of:

```
VERDICT: PASS
VERDICT: CHANGES
```

`CHANGES` requires at least one concrete, actionable finding (file:line,
problem, expected fix). Style preferences alone are not `CHANGES`. A
regression finding justifies `CHANGES` only when it is not required by an
acceptance criterion and has a concrete impact; note lower-impact or
intentional behaviour changes under `PASS` instead.
