---
name: engineering-guard-implement
description: Implement features and fixes using readable, maintainable code, established repository conventions, meaningful tests, and approved architectural decisions when available.
---

# Engineering Guard — Implement

Implement the requested change with an emphasis on correctness,
readability, maintainability, and meaningful verification.

Act as a thoughtful software engineer, not merely a code generator.

Prefer code that future maintainers can understand and modify
over code optimised for fewer tokens, fewer lines, or easier mocking.

## 1. Understand before editing

Read applicable `AGENTS.md` instructions, project conventions,
the Engineering Guard engineering policy, and the relevant
project constitution when present.

Read the security policy for security-sensitive changes and
the testing policy before modifying tests.

Inspect the relevant:

- Execution paths, callers, and existing behaviour.
- Dependencies, interfaces, and responsibility boundaries.
- Existing implementation patterns and conventions.
- Tests, fixtures, and available verification commands.
- Error handling and important behavioural constraints.

Keep investigation proportional to the task.

Do not demand a separate Research or Align phase for
straightforward changes.

Look for applicable decision records proportionately to the change.
When an explicitly approved record exists, check that the approved
revision is current and relevant, then follow its architecture,
constraints, and acceptance criteria. Flag stale or conflicting
decisions rather than silently adopting them.

A Research recommendation or draft decision is not approval.

## 2. Plan the implementation

Determine the smallest coherent change that satisfies the
requirements and preserves unrelated behaviour.

For substantial changes, identify the relevant implementation
steps and verification strategy before editing.

Do not produce lengthy planning documents unless requested.

Respect approved architectural decisions while retaining
autonomy over local implementation details.

If new evidence reveals a material problem with an approved
plan, explain the conflict and request a decision before
departing from it.

Do not silently change:

- Architectural or integration boundaries.
- Persistence or communication strategies.
- Authorisation or security guarantees.
- Public contracts or compatibility expectations.
- Agreed scope or acceptance criteria.

Do not seek approval for ordinary implementation details
that remain within the agreed architecture.

## 3. Write code for maintainability

### Expressive naming

Choose descriptive names that communicate intent.

Avoid vague abbreviations, generic identifiers, and compressed
expressions when clearer alternatives improve understanding.

Conventional short names remain appropriate where unambiguous.

Do not optimise source code for token consumption.

### Meaningful comments

Explain important reasoning that is not obvious from the code.

Document relevant:

- Architectural decisions and constraints.
- Business rules and invariants.
- Non-obvious ordering or dependency requirements.
- Error-handling and recovery assumptions.
- Compatibility requirements and deliberate workarounds.

Prefer comments explaining WHY behaviour exists rather than
narrating WHAT individual statements do.

Keep comments accurate, close to the relevant implementation,
and consistent with the behaviour they describe.

Do not add decorative comments or unnecessary documentation.

### Justified abstractions

Introduce abstractions only when they improve cohesion,
encapsulation, reuse, readability, or responsibility boundaries.

Avoid:

- Functions created solely to return a trivial value.
- Wrappers that introduce indirection without meaningful benefit.
- Interfaces and factories without demonstrated variation.
- Dependency injection introduced solely to enable mocking.
- Speculative flexibility for requirements that do not exist.
- Splitting straightforward logic into excessive helper functions.

Small functions are appropriate when they express a meaningful
concept or improve comprehension.

Prefer the existing architecture unless there is a justified
reason to change it.

When a recognized design pattern or refactoring technique materially
shapes the change, name it in the implementation summary and explain
the responsibility, coupling, or change-cost problem it addresses.
Use a pattern only when its structure fits the real requirement; do
not add pattern-name comments merely to label familiar constructs.
When the pattern choice is consequential or non-obvious, add a brief
nearby code comment naming it and explaining why it fits, rather than
stating only the pattern name. For example:

```js
// Strategy: keep format-specific rendering out of the shared export flow.
const formatter = formatters[requestedFormat];
```

For refactoring, identify the concrete code smell or change pressure
and the behavior that must remain unchanged; name the transformation
in the code comment when that rationale would not be clear from the
resulting code. Add no comment when the code already makes the reason
obvious.

### Clear behaviour

Make error handling explicit and consistent with project conventions.
Distinguish invalid input from dependency or internal failures;
do not present an outage as a client error.

Do not silently swallow failures, fabricate successful fallbacks,
or hide unexpected states.

Preserve data integrity, relevant invariants, and established
security boundaries.

Avoid unrelated refactoring or unnecessary dependencies.

### Resource and integration boundaries

When adding a long-lived resource, identify who owns it and
where it is closed. Check both normal shutdown and failure
during startup after some resources have already opened.

For example, if initialization fails after a connection opens,
close it before propagating the failure:

```js
async function startIndex(openConnection, loadIndex) {
  const connection = await openConnection();
  try {
    const index = await loadIndex(connection);
    return { index, close: () => connection.close() };
  } catch (error) {
    try {
      await connection.close();
    } catch (cleanupError) {
      throw new AggregateError([error, cleanupError], 'Index startup and cleanup failed');
    }
    throw error;
  }
}
```

The aggregate preserves both failures when cleanup also fails;
adapt its reporting to the application's established error contract.

For work spanning a database, queue, remote API, or other
independent systems, inspect the order of effects and what
happens when each step fails. Define whether partial work is
retriable, compensatable, or must be reported as incomplete;
check idempotency before recommending a retry. For example:

```js
async function saveAndNotify(record, save, notify) {
  await save(record);
  try {
    await notify(record);
  } catch (error) {
    throw new Error('Record saved; notification failed', { cause: error });
  }
}
```

This example reports partial work rather than claiming full
success; it does not establish a retry or transaction strategy.
Choose recovery according to the actual contract, not a
mandatory outbox or compensating-action pattern.

## 4. Implement in coherent increments

Make focused changes that can be understood and verified.

For larger tasks, implement in logical increments and perform
relevant checks as work progresses.

Do not rewrite unrelated components merely because they could
be improved.

If an unexpected issue is discovered:

- Establish whether it is caused by the current change.
- Investigate the evidence before modifying more code.
- Correct issues within the approved scope.
- Report unrelated defects without silently expanding scope.

Avoid repeated speculative fixes without understanding why
previous attempts failed.

## 5. Test meaningful behaviour

Read and follow the Engineering Guard testing policy.

Add or update tests using the existing project framework.

Derive tests from requirements, observable behaviour, and
known failure modes rather than merely mirroring the implementation.

Prefer real application logic and realistic boundaries.

Mock only justified external or nondeterministic dependencies.
Do not mock the behaviour being tested.

For bug fixes, demonstrate that an appropriate regression test
detects the original failure when practical.

Cover relevant success, failure, boundary, and regression cases.

Where effects span systems, test the failure window after the
first effect and assert both the reported outcome and the
remaining state or side effects. For resource startup, test
cleanup when a later initialization step fails.

Never weaken assertions, replace real behaviour with mocks,
or alter production contracts merely to make tests pass.

For security-sensitive changes, verify the affected trust
boundary with appropriate positive and negative cases.

Do not equate a large number of passing tests with correctness.

## 6. Verify the implementation

Run the relevant tests, linters, type checks, builds, or
application entry points supported by the repository.

Choose checks proportionate to the change and its risks.

When `scripts/verification_runner.py` is present, inspect its
inventory and explicitly select relevant root npm scripts with
`--run <name>`. Use `--base <ref>` when a comparison baseline
other than `HEAD` is relevant. The runner captures execution
evidence; it does not decide whether the checks are sufficient.
Do not run every listed script automatically.

Inspect actual command results rather than assuming success.

Distinguish:

- Newly introduced failures.
- Existing failures established by evidence.
- Checks that could not be executed.

Where practical, verify important behaviour through a real
application boundary rather than relying exclusively on mocks.

Do not claim end-to-end or integration verification unless
those checks were actually executed.

Do not perform destructive operations or interact with
production systems without appropriate authorisation.

## 7. Review and report

Before finishing, review the diff against:

- The original requirements and acceptance criteria.
- Approved architectural decisions, when present.
- Applicable engineering and security policies.
- Readability, naming, comments, and abstraction quality.
- Relevant tests and observed behaviour.
- Unintended changes or regressions.

Correct identified problems within scope.

Report concisely:

- What changed and why.
- Important implementation decisions.
- Tests and checks executed, with actual results.
- Deviations from the plan, if any.
- Remaining risks or unverified behaviour.

Do not declare the implementation fully verified when
meaningful checks remain incomplete.

Independent Verify and Security reviews remain separate
activities and must not be represented as completed unless run.

## Hook integration

The production-code hook delivers the engineering policy
before recognised production-code writes.

Testing Guard similarly delivers its testing policy.

These hooks enforce policy availability, not code quality
or compliance.

Follow the applicable policies even when a write bypasses
hook detection.
