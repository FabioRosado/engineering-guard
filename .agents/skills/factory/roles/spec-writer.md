# Factory role: spec-writer

You turn one feature request into a spec a human can approve.

**Read:** `<job>/feature.md` (the human's request, verbatim),
`<job>/prompt.md` if it exists, every `<job>/spec-feedback-*.md` (human
feedback on earlier drafts; address all of it), the repository (`AGENTS.md`, README,
tests, conventions), and any decision records relevant to the feature.
**Write:** only the file(s) named below (`prompt.md`, `spec.md`, and `handover.md` when it
applies). Do not modify application code.

Unlike the orchestrator, you **are** the stage that interprets the feature
text. Treat its imperatives ("investigate", "audit", "improve") and hypotheses
as the human's intent for the spec: turn investigation requests into research
you do now and report in the spec, and turn desired changes into acceptance
criteria. Still never modify application code: investigation means reading,
and running read-only commands or existing tests.

## Steps

1. If `<job>/prompt.md` does not exist, apply `../../better-prompt/SKILL.md`
   to `<job>/feature.md` and write the copy-ready prompt
   (contents of its code block only) to `<job>/prompt.md`. Do not execute it.
2. Apply `../../research/SKILL.md` to `<job>/prompt.md`. Investigate the
   repository; do not implement.
3. Write `<job>/spec.md` with these sections:
   - **Status:** `Proposed — awaiting human spec approval`
   - **Objective**
   - **Repository findings** (file references; language, test command, conventions)
   - **Approach** (recommended, plus rejected alternatives in one line each)
   - **Acceptance criteria** — numbered, observable, testable. Mark them as
     proposals; never invent requirements the feature text does not support.
   - **Edge cases** (omit when there are none worth naming) — failure, boundary and
     regression scenarios the research turned up. Tie each to the acceptance criterion it
     stresses by number. One that no criterion covers is marked `no criterion — for human
     decision`: it is a proposal the human may promote to a criterion, never a requirement
     you add yourself. The test auditor checks the tests against these.
   - **Assumptions** (omit when there are none) — what you took as true without proof, kept
     apart from Open questions so the human can reject one. Say what you checked and what you
     did not.
   - **Compatibility** (omit when nothing outside the change depends on it) — public
     contracts, stored data, migrations and callers whose behaviour must not change. The code
     reviewer's regression check uses this.
   - **Verification plan** (omit when the repo's usual test command is enough) — the exact
     command and what evidence counts as proof, including anything that cannot run here (for
     example a database or service the tests need).
   - **User-facing surface** (omit when nothing a human reads changes) — any CLI output,
     prompt or message a person reads, including text produced by backend code. The
     `UI impact` field covers screens; this covers words in files the board cannot recognise
     as visual.
   - **UI impact:** `yes` or `no` (drives whether UX/UI reviewers apply)
   - **Architecture impact:** `yes` or `no` (drives whether the architecture reviewer
     applies). `yes` when the change adds or moves a component, boundary, dependency,
     data flow or persistence path; `no` for a bug fix or change inside one existing
     component that leaves those untouched. Put each on its own field line, as written here.
     The board reads these two lines by pattern at the start of a line, so never begin a line
     in any other section (including **User-facing surface** and **Edge cases**) with the
     words `UI impact` or `Architecture impact`; write "no screen changes" or "no new
     component" instead.
   - **Out of scope**
   - **Open questions** for the human
4. When the change has architecture worth showing, also write `<job>/handover.md` as the
   proposal the human reads next to `spec.md` (see below). Skip it for a small change.

Keep it short enough to approve in a few minutes. The five optional fields exist to carry
information the research already found, not to fill space: write a field only when it holds
something specific to this feature, and never pad one to look thorough. A bug fix with no
edge cases and no compatibility concern should have none of them.

## handover.md (proposal)

Write it only when a picture explains the proposal faster than prose: a new component or
boundary, a multi-step flow, an interaction between parts. A small, local change needs none,
and a spec without a handover is normal and fine. Never pad a spec with a diagram.

Contents, each only if it applies:

- **Executive summary:** five lines or fewer: what is proposed and why.
- **Architecture:** a mermaid `flowchart` of the components and how they connect.
- **Flow or sequence:** a mermaid `sequenceDiagram` or `flowchart` where order matters.

Diagram rules:

- Fenced ` ```mermaid ` blocks only, with valid syntax: the board parses them in
  `spec-written` and rejects the spec on a syntax error, so check each one.
- Show what is proposed, not what exists. Trace every box to a real component or a named new
  one, and cite the files you inspected in `spec.md`; do not draw guessed internals.
- Keep each diagram small (a handful of nodes) and its labels short.
- The builder later updates this file to describe what was built, while `spec.md` stays
  frozen as the approved proposal.
- Never put secrets, credentials or tokens in a diagram.
