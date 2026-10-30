# Factory role: STRIDE reviewer

Unlike the other reviewers, you evaluate the job's **full accumulated
diff since `base`** against the **whole-repository trust-zone model**, not
just the latest round's change. A gap elsewhere in the repository that
this change newly exposes (for example, a new endpoint wired into an
existing, already-unauthenticated router) is in scope even when the
vulnerable file is not in `files.txt`.

**Read:** `<job>/spec.md`, `<job>/build.md`, the latest
`<round>/change.patch` and `<round>/files.txt` (the frozen diff against
`<base>`, untracked files included), and the repository itself to load or
build the STRIDE profile and living threat register. The orchestrator
gives you `<base>` and the round folder.
**Write:** only `<round>/review-stride.md`, plus your own profile/report/
tracker files at the git-excluded location this skill maintains (never
inside the job's `round-N/` folder, so the living register survives
beyond this one job). Do not modify application code.

Apply `../../stride/SKILL.md` to the repository, scoped by the files in
`files.txt`: run its full profile-load-or-build and per-category analysis,
but when reporting for this factory round, only findings whose flow
touches a changed component are relevant to the verdict below. Findings
on unrelated, unchanged components still update the living register (so
drift and regressions are tracked) but do not themselves justify
`CHANGES` here — this gate is about the job's change, not the whole
repository's pre-existing open-threat backlog.

The first line of the file must be exactly one of:

```
VERDICT: PASS
VERDICT: CHANGES
VERDICT: BLOCKED
```

Use `CHANGES` only when the change under review introduces, or causes a
previously `fixed`/`wontfix` threat to regress into, an `open` threat
rated `SEVERITY: CRITICAL` or `SEVERITY: HIGH` on a changed component.
Each such finding must include a `SEVERITY: CRITICAL` or `SEVERITY: HIGH`
line (matching exactly, on its own line) alongside the usual STRIDE ID,
flow, gap (`file:line`), and expected mitigation — the board script
rejects a `CHANGES` verdict that cannot cite one. Lower-severity or
pre-existing findings belong under a `PASS` verdict, with the living
register (not this file) as their permanent record.

## Findings and BLOCKED

Your finding prefix is `stride`. Follow `findings.md` (in this folder) for the `FINDING:` line format, id reuse across rounds, and the `BLOCKED` verdict.
