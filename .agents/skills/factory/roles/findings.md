# Factory: findings and BLOCKED (shared by the test auditor and every reviewer)

Your role file names your **finding prefix** (for example `security`). Everything below uses it.

## Findings

For every problem you report, write one line in this exact form, then explain it in prose
below the line:

```
FINDING: <prefix>-<n> | SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW|INFO> | LOCATION: <path[:line]|none> | STATUS: <open|closed|disputed>
```

- **Reuse ids.** Before you write anything, read your own file from the previous round
  (`<job>/round-<N-1>/<your file>`, if it exists). A problem you are re-checking keeps its
  id. Mint a new `<prefix>-<n>` (next unused number) only for a problem you have not
  reported before. Never renumber. The board follows findings across rounds by id, so a
  reworded id looks like a new problem and hides whether the builder fixed the old one.
- **Close only your own.** Write `STATUS: closed` for one of your earlier findings only when
  you checked the fix in the current code. Ids starting with another role's prefix are
  rejected by the board: you cannot raise or close them.
- **Restate every open finding.** A finding that was open last round must appear again this
  round as `open`, `closed` or `disputed`. If you leave it out, the board warns that it was
  dropped, and it stays open.
- **`disputed`:** use it when `build.md` rebuts a finding and you have not yet decided
  whether the rebuttal holds. A disputed finding stays unresolved for the human.
- **`LOCATION: none`** only when the problem has no file, such as a missing test.
- Keep the narrative. The line is an index for the board; the reasoning, evidence and
  expected fix still go in your prose.
- A `VERDICT: CHANGES` needs at least one `FINDING` line with `STATUS: open` once any
  finding line appears in the job. Lower-severity open findings may follow `VERDICT: PASS`.

A malformed `FINDING:` line makes the whole file invalid and you will be re-spawned, so
check the spelling of the severity and status words.

## BLOCKED

If you cannot assess the change at all, write `VERDICT: BLOCKED` as the first line and, below
it, one line saying what you could not do and why (for example: a database the tests need is
not reachable, the patch is empty, a required file is unreadable).

- Use it only when no verdict would be honest. If you can assess part of the change, give
  `PASS` or `CHANGES` for that part and list what you could not check in your prose.
- `BLOCKED` stops the job and sends it to the human. It does not send it to the builder,
  because there is nothing for the builder to fix. Do not use it to avoid a hard judgement.
- A bare `BLOCKED` with no reason is rejected.
