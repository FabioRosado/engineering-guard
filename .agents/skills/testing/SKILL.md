---
name: engineering-guard-testing
description: Design, implement, and independently audit meaningful behavioural tests. Detect excessive mocking, weak assertions, missing integration coverage, and false confidence from passing test suites.
---

# Engineering Guard — Testing

Design, implement, and evaluate tests that provide trustworthy
evidence of software correctness.

The objective is not to maximise test counts or coverage
percentages. It is to detect meaningful defects and prevent
regressions.

Act as a critical test engineer. A passing test is useful only
when it verifies relevant behaviour and can detect its failure.

## 1. Establish the task

Determine whether the developer wants to:

- Design a testing strategy.
- Write or update tests.
- Investigate a failing test.
- Audit existing test quality.
- Diagnose a misleading passing test suite.

For planning and audit-only requests, remain read-only.
Do not modify tests or production code without authorisation.

Read applicable repository instructions, the Engineering Guard
testing policy, relevant decision records, and the project
constitution when present. Check the applicable revision and
approval status before treating a decision as a test contract;
Research proposals and drafts are not approved requirements.

Do not require Spec Kit.

## 2. Understand the expected behaviour

Establish the requirements and observable acceptance criteria.

Distinguish:

- Intended behaviour established by requirements.
- Existing implementation behaviour.
- Assumptions and unresolved expectations.
- Known regressions and failure scenarios.

Do not derive all test expectations from the implementation.
The implementation itself may be incorrect.

Inspect relevant production code, callers, interfaces,
integration boundaries, and existing tests.

Trace the actual execution path before deciding what to mock
or which components should be exercised.

Keep investigation proportional to the change.

## 3. Design meaningful test cases

Choose tests that would detect important incorrect behaviour.

Consider where relevant:

- Successful operations and expected outputs.
- Invalid inputs and boundary conditions.
- Error handling and failure propagation.
- State changes, persistence, and side effects.
- Authentication and authorisation boundaries.
- Retry, concurrency, and idempotency behaviour.
- Compatibility and regression requirements.
- Interactions between real application components.

For substantial changes, establish a concise behavioural
test matrix before implementation.

Prioritise realistic failure modes over exhaustive combinations
of trivial cases.

Do not invent requirements or expected behaviour.

## 4. Choose appropriate test boundaries

Select test levels according to the behaviour being verified.

**Unit tests**
Verify domain rules, calculations, transformations,
and isolated behaviour.

**Integration tests**
Verify real interactions between components, persistence,
routing, dependency wiring, or external interfaces.

**End-to-end tests**
Verify important user-facing or system workflows through
representative application entry points.

Use the smallest combination that provides meaningful
evidence for the requirement.

Do not claim unit tests establish integration correctness.

Prefer exercising real application components where practical.

Do not require expensive end-to-end tests for trivial changes,
but do not replace necessary integration coverage with mocks.

## 5. Use test doubles responsibly

Mock only when there is a justified boundary.

Suitable examples may include:

- Unavailable external services.
- Nondeterministic dependencies.
- Expensive or unsafe external operations.
- Controlled failure injection.

Keep the functionality being tested real.

Avoid:

- Mocking the primary behaviour under test.
- Mocking every dependency by default.
- Testing only interactions between mocks.
- Assertions that merely confirm configured mock returns.
- Creating production interfaces solely for mocking.
- Replacing integration tests with heavily mocked unit tests
  while claiming equivalent confidence.

Interaction assertions are appropriate when the interaction
itself is the observable contract.

Explain unusual or consequential mocking decisions.

Where test doubles are necessary, consider how their
contracts are validated against real implementations.

## 6. Implement tests that detect failures

Write descriptive tests expressing expected behaviour.

Prefer assertions about externally observable outcomes,
state changes, persisted data, and relevant side effects.

Do not rely exclusively on checking whether internal
functions were called.

For bug fixes, when practical:

1. Reproduce the reported failure.
2. Write a regression test expressing correct behaviour.
3. Demonstrate that it fails for the original defect.
4. Apply or coordinate the authorised fix.
5. Demonstrate that the regression test passes afterward.

For a tests-only task, report the demonstrated production failure
without changing production code unless that fix was also requested.
Do not claim the final passing step if it has not occurred.

Verify that an expected failure occurs for the intended
reason, not merely because a command exited unsuccessfully.

Never manufacture a failing test or claim red-green
verification without executing the relevant states.

Do not weaken assertions, change expected values, or add
mocks merely to obtain a passing result.

## 7. Challenge the tests themselves

Before accepting a passing test suite, ask:

- Would these tests fail if the relevant behaviour were wrong?
- Do assertions verify meaningful outcomes?
- Does the test exercise the production path it claims to?
- Are important boundaries mocked away?
- Are success and failure scenarios represented?
- Could fixtures or test setup conceal production defects?
- Could a broad exception or generic failure satisfy the test?
- Are integration assumptions actually verified?

For critical behaviour, consider a targeted negative control
or mutation check when safe and practical.

For example, temporarily changing an important condition in
a disposable environment should cause relevant tests to fail.

Do not introduce mutations into the developer's working tree
without appropriate isolation and restoration.

Mutation testing is useful evidence, not a mandatory ritual
for every change.

## 8. Investigate failures carefully

Run relevant tests and inspect their actual output.

When a test fails, determine whether the cause is:

- A genuine production defect.
- An incorrect test expectation.
- A test fixture or environment problem.
- A flaky or nondeterministic condition.
- An unrelated pre-existing failure.

Do not automatically assume the implementation is correct.

Do not automatically assume the test is correct either.

Resolve discrepancies using requirements, contracts,
and evidence from the real execution path.

Only change an expectation when there is evidence that
the expectation is incorrect.

Respect the requested scope. Do not modify production code
during an audit-only task or expand an implementation task
without authorisation.

Avoid repeatedly changing tests until they turn green
without establishing why they originally failed.

## 9. Audit existing test suites

When reviewing existing tests, investigate whether the suite
provides meaningful behavioural confidence.

Identify:

- Excessive or unjustified mocking.
- Tests that assert mock configuration rather than behaviour.
- Missing integration or application-boundary coverage.
- Weak, missing, or overly broad assertions.
- Duplicated tests that provide little additional confidence.
- Missing negative or regression scenarios.
- Test fixtures that differ materially from production.
- Important behaviour with no effective failure detection.

Prioritise findings by their potential to hide real defects.

Provide concrete examples with file references.

Distinguish confirmed testing weaknesses from possible gaps.

Do not rewrite the test suite unless requested.

## 10. Verify and report

Execute relevant tests and application checks when authorised.

When `scripts/verification_runner.py` is present, inspect its
available scripts and explicitly select relevant test commands
with `--run <name>`. Review captured failures, errors, and
coverage artifact paths. The runner records what executed; it
cannot judge whether tests exercise meaningful production
behavior, so inspect the test and production paths directly.

Report:

- Behaviour and requirements covered.
- Test levels and real boundaries exercised.
- Commands executed and actual results.
- Important mocks and their justification.
- Regression or mutation evidence, when available.
- Failures discovered and their causes.
- Unverified boundaries and environmental limitations.
- Remaining risks of false confidence.

Distinguish tests written from tests actually executed.

Do not claim functionality is verified solely because
a test suite passes.

Do not claim integration or end-to-end verification when
only unit tests were executed.

Keep the report proportional to the work.

## Hook integration

The Codex testing hook supplies the current testing policy
and gates recognised writes when policy delivery is missing
or stale.

This guarantees policy availability only for covered writes,
not test quality or compliance.

Follow the testing policy regardless of hook coverage.
