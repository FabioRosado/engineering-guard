# Engineering Guard — Testing Policy

Tests must establish confidence in observable behaviour and detect meaningful regressions, not merely mirror the implementation.

Optimise for defect detection and trustworthy evidence, not test counts, coverage percentages, or ease of mocking.

## Required practices

- **Start from requirements.** Derive test expectations from established requirements, contracts, examples, or independently verified behaviour. Do not assume the current implementation is correct or duplicate its logic to calculate expected results.
- **Understand the real execution path.** Trace relevant production code, callers, dependencies, and integration boundaries before choosing what to test or isolate.
- **Test at meaningful boundaries.** Use real components wherever practical. Choose unit, integration, and end-to-end tests according to the behaviour and risks being verified. Do not claim integration correctness from isolated unit tests.
- **Justify test doubles.** Mock external services, clocks, networks, or other dependencies when isolation is appropriate. Keep the functionality under test real. Where a mock replaces an important external contract, consider how that contract is verified independently.
- **Avoid mock theatre.** Never mock the behaviour being tested or create tests that pass solely because configured mocks return expected values. Interaction assertions are appropriate when the interaction itself is the required behaviour.
- **Cover meaningful failures.** Include relevant negative cases, boundary conditions, error handling, and regression scenarios. Prioritise realistic failure modes over exhaustive trivial combinations.
- **Preserve production architecture.** Do not introduce unnecessary wrappers, interfaces, or dependency injection solely for mocking. Design changes that improve genuine separation of concerns or testability may be justified by broader engineering needs.
- **Prefer quality over quantity.** A few tests exercising important behaviour are more valuable than hundreds of superficial tests. Avoid duplicated tests that contribute little additional confidence.
- **Do not manufacture green results.** Never silently weaken assertions, delete failing coverage, replace real behaviour with mocks, or change expectations merely to make tests pass. Update expectations when independently established requirements have changed, and explain why.
- **Investigate failures.** Determine whether failures arise from production defects, incorrect expectations, fixtures, infrastructure, or nondeterminism. Do not repeatedly modify tests until they pass without understanding the cause.
- **Verify and report.** Run relevant checks, inspect actual outcomes, and report the commands executed, tests passed or failed, real boundaries exercised, and important unverified behaviour.

## Review the tests themselves

For each important test, ask:

1. Would this test fail if the specific behaviour it claims to verify were incorrect?
2. Are the expected values independent of the implementation being tested?
3. Does the test exercise real production logic, or are mocks supplying the asserted result?
4. Are important application and integration boundaries adequately covered elsewhere?
5. Could a broad exception, incomplete fixture, or unrelated failure produce a misleading result?

For critical behaviour, consider a targeted mutation or negative control in a safe, isolated environment to demonstrate that the test detects a relevant defect.

Do not treat passing tests as proof of correctness. Distinguish what the suite establishes from what remains unverified.

When reviewing tests without permission to modify them, report weaknesses and recommended improvements rather than changing the suite.
