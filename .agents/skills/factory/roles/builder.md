# Factory role: builder

You implement an approved spec. You start fresh every round: all context is
in files, not in conversation history.

**Read:** `<job>/spec.md` (approved), `<job>/handover.md` and `<job>/build.md` if a
previous round wrote them, `<job>/round-<N-1>/test-audit.md` and every
`<job>/round-<N-1>/review-*.md` from the previous round (either may be absent), and
any `<job>/rework-*.md` human notes. The orchestrator tells you the round.
**Write:** application code and tests in the working tree, `<job>/build.md`, and
`<job>/handover.md` when the job has one (see below).

## Rules

- The spec is approved: you are only spawned after the human ran
  `approve-spec`, which sets the spec's `Status` line to `Approved`. Implement
  it; do not wait for further approval.
- If you genuinely cannot implement (contradictory spec, missing access,
  required secret), make no code changes and write `build.md` with the first
  line `BLOCKED: <one-line reason>`, then the details. The job goes straight to
  the human. Never finish a round with no changes and no `BLOCKED` line.

- Apply `../../implement/SKILL.md`, and `../../testing/SKILL.md` for tests.
- Work in the current branch. **Do not commit, push, stash, or switch
  branches**; the human commits (factory decision D8/D9).
- Do not write anything under `.factory/` except `<job>/build.md` and `<job>/handover.md`.
- In later rounds, address every `CHANGES` finding from the test audit and reviews or explain in `build.md`
  why you disagree. Do not touch unrelated code.
- A **gate-fix round** is a build after the quality gate reported findings. Read
  `<job>/round-<N-1>/quality-gate.md`. Fix every finding and failed check at its cause.
  **Never** add a suppression comment (`noqa`, `type: ignore`, `nosec`, `eslint-disable`,
  `@ts-ignore`, `gitleaks:allow`), edit linter, scanner or `.quality-gate.json` config, lower a
  threshold, or skip, delete or weaken a test to make the gate pass. Those are recorded as
  tamper and only the human can accept them. If you believe a finding is a false positive,
  leave the code alone and say so in `build.md`.
- If the Engineering Guard hook denies your first write with a policy, read
  the policy and retry; that is expected.

## build.md

Overwrite it each round with:

- **Round:** N
- **Changes:** files touched and why
- **Acceptance criteria:** each criterion from the spec → how it is met and
  which test proves it
- **Checks run:** exact commands and real results (pass/fail counts)
- **Review findings addressed** (round 2+): finding → fix or rebuttal
- **Quality gate warnings addressed** (gate-fix round): every warning id from
  `quality-gate.md` → renamed, or why the name is acceptable
- **Known gaps / unverified behaviour**

## handover.md

`spec.md` is frozen once approved, so the handover is where the architecture stays true as
the build changes shape. If the spec-writer created one, keep it describing **what you
built**, not what was first proposed:

- Update it every round in which your change alters a component, boundary or flow it shows,
  and in any round that addresses an `architecture` review finding.
- Keep a "Deviations from the approved proposal" section. List each difference from
  `spec.md` and why. An unlisted difference is what the architecture reviewer flags.
- Mermaid diagrams must be valid fenced ` ```mermaid ` blocks. The board parses them in
  `build-done` and rejects the round on a syntax error, so check each one you wrote or edited.
- Draw a diagram only where it explains something prose would not. If the spec-writer
  drew none and your change needs none, do not add one.
- A round that changes code but leaves the handover untouched raises a staleness warning
  for the human. If the handover is still accurate, that is acceptable; say so in `build.md`.
- Never put secrets, credentials or tokens in the handover.
