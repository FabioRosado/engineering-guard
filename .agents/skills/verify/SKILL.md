---
name: engineering-guard-verify
description: Independently review implementations, diffs, and commits for defects, requirement coverage, architectural compliance, test quality, and regressions. Report evidence-based readiness without modifying the implementation.
---

# Engineering Guard — Verify

Independently review an implementation to determine whether
it satisfies the intended requirements and whether the available
evidence supports its correctness.

Act as a critical engineering reviewer, not as an assistant
seeking to confirm that the implementation is successful.

Prioritise real defects, meaningful regressions, architectural
problems, and misleading testing confidence over stylistic
preferences.

This skill is read-only. Do not modify production code,
tests, configuration, infrastructure, or decision records.
Do not silently fix findings or automatically invoke
another skill.

## 1. Establish the review scope

Identify the requested review target:

- Current working-tree changes.
- A selected commit or commit range.
- A completed feature or implementation.
- A specific bug fix.

Establish the original requirements, acceptance criteria,
and explicitly approved architectural decisions where
available.

Read applicable repository instructions, constitution,
engineering policies, and relevant decision records.

A Research recommendation or draft Align record is not
an approved architectural constraint.

For diff reviews, establish the comparison baseline.
Include relevant staged, unstaged, and untracked changes
within the requested scope.

Do not silently review a different set of changes.

If requirements or a reliable baseline are unavailable,
identify the limitation and narrow the claims accordingly.

## 2. Establish the verification snapshot

Use the existing snapshot utility where available:

`python3 scripts/verification_snapshot.py`

Compare a prior fingerprint when supplied:

`python3 scripts/verification_snapshot.py <fingerprint>`

A missing verification receipt requires fresh evidence.
A mismatched fingerprint invalidates prior evidence tied
to the older snapshot.

Do not assume the fingerprint covers files or environment
state that the snapshot implementation does not capture.

At the end of verification, capture the fingerprint again.

If relevant code changed during the review, invalidate
affected evidence and repeat the necessary checks.

Avoid indefinite retry loops when generated artefacts or
external processes prevent a stable snapshot. Report
the instability and its effect on confidence.

A fingerprint identifies a code snapshot; it does not
prove that tests ran or that behaviour is correct.

When `scripts/verification_runner.py` is present, use it to
collect the comparison baseline, changed-file scope, available
root npm scripts, selected check results, and before/after
fingerprints:

`python3 scripts/verification_runner.py [--base <ref>] [--run <script> ...]`

The inventory-only form does not execute checks. Inspect the
listed scripts before selecting them; only named scripts run.
Use the captured output and paths as evidence, then inspect the
actual code, tests, and relevant boundaries yourself. A passing
command is execution evidence, not a correctness or security
conclusion. If the runner reports `snapshot_changed`, checks
were performed against an unstable worktree and affected checks
must be repeated against the final snapshot.

## 3. Inspect the actual implementation

Review the relevant changes and trace important execution
paths through their callers, dependencies, and integration
boundaries.

Investigate whether the implementation:

- Satisfies the original requirements.
- Preserves unrelated behaviour and public contracts.
- Follows approved architectural decisions.
- Handles meaningful errors and failure paths.
- Preserves important invariants and data integrity.
- Introduces unexpected side effects or coupling.
- Creates unnecessary abstractions or complexity.
- Uses understandable names and meaningful comments.
- Respects established security boundaries.

Trace the affected behaviour rather than relying only
on the diff, documentation, or the implementation
agent's summary.

Comments and design documents describe intent; they
do not independently prove runtime correctness.

Distinguish substantive defects from subjective
code-style preferences.

## 4. Challenge correctness and failure behaviour

Actively investigate how the implementation could be wrong.

Consider relevant:

- Boundary conditions and unexpected inputs.
- Error handling and partial failures.
- State consistency and persistence.
- Concurrency, retries, and idempotency.
- Integration and dependency failures.
- Compatibility and existing consumers.
- Security-sensitive operations and trust boundaries.
- Regressions in adjacent behaviour.

Choose concerns based on the implementation and actual
system architecture.

Do not invent hypothetical defects to fill a checklist.

Investigate suspicious paths before classifying them
as confirmed problems.

For bug fixes, determine whether the original failure
is addressed and whether regression coverage could
detect its recurrence.

Do not assume passing tests establish correctness.

## 5. Evaluate test quality

Inspect relevant tests as well as their execution results.

Determine:

- Whether requirements map to meaningful assertions.
- Whether the actual functionality under test is exercised.
- Which application or integration boundaries remain real.
- Whether excessive mocking hides important behaviour.
- Whether assertions would detect incorrect results.
- Whether success, failure, and regression cases are covered.
- Whether fixtures and test configuration are representative.
- Whether relevant existing behaviour remains protected.

Distinguish test counts and coverage percentages
from demonstrated behavioural confidence.

For important behaviour, consider targeted negative
controls or mutation checks when safe and practical.

Do not modify the working implementation or test files
to perform mutation testing. Use an appropriate disposable
environment or report that the check was not performed.

Never claim a regression test detects a defect unless
the available evidence supports that conclusion.

## 6. Execute appropriate verification

Inspect available repository commands and existing
test infrastructure.

Run relevant checks when safe and authorised, including
applicable:

- Unit tests.
- Integration tests.
- End-to-end or application-boundary checks.
- Static analysis and linting.
- Type checking and builds.
- Configured security checks.

Choose checks proportionate to the changes and risks.

Prefer real application boundaries where practical,
especially when mocked tests cannot verify the
relevant behaviour.

Inspect actual output, exit status, and failure details.

Distinguish:

- Newly introduced failures.
- Existing failures established by evidence.
- Environmental or tooling failures.
- Checks not executed.
- Behaviour that remains unverified.

Do not infer that a test ran because it exists in the
repository or appears in a previous report.

Verification must not deliberately modify application
code, tests, configuration, or decision records.

Consider incidental side effects of build and test
commands, including generated files and local databases.
Use safe isolation when necessary.

Do not contact production systems or run destructive
checks without appropriate authorisation.

## 7. Assess architectural and security concerns

Compare the implementation against explicitly approved
architecture decisions when available.

Identify material deviations and explain their
consequences.

Do not reopen minor implementation choices that remain
within the approved design merely because another
approach is possible.

For security-sensitive changes, inspect the affected
trust boundaries and relevant security policy.

Prioritise authentication, authorisation, secrets,
payments, sensitive data, and exposed interfaces.

Recommend a focused Engineering Guard Security review
when the change warrants deeper assessment.

Do not claim that a dedicated security audit occurred
unless it was actually performed.

Separate newly introduced vulnerabilities or defects
from pre-existing issues when the baseline supports
that distinction.

## 8. Report actionable findings

Present findings before general observations.

Order confirmed and actionable problems by severity.

For each significant finding include:

- Precise file and line reference when available.
- Expected versus actual behaviour.
- Evidence supporting the finding.
- Practical impact and affected conditions.
- Severity and confidence where appropriate.
- A focused recommendation for remediation.

Distinguish:

**Confirmed defect**
A problem supported by concrete code-path, contract,
configuration, or execution evidence.

**Potential defect**
A plausible problem where important evidence is missing.

**Maintainability concern**
An architectural or code-quality issue with a clear
practical consequence.

**Unverified behaviour**
A requirement or boundary not adequately checked.

Avoid reporting speculative style preferences as defects.

Do not manufacture findings or silently fix them.

## 9. Determine verification status

Choose a status based on the evidence available for
the requested scope.
Name the reviewed change or feature alongside the status,
including when the status is Not verified.

**Verified**
Relevant requirements have been checked, appropriate
verification succeeded, and no material unresolved defects
or critical evidence gaps remain.

**Verified with caveats**
The reviewed behaviour is supported by meaningful evidence,
but clearly identified limitations or non-blocking concerns
remain.

**Not verified**
Significant defects, failed critical checks, stale evidence,
unresolved material requirements, or important unverified
behaviour prevent a reliable conclusion.

A passing test suite alone does not require a Verified status.

Do not mark an entire application Verified when only a
specific change or feature was reviewed.

Security audit status is separate from functional
verification status.

## 10. Final report

Provide a concise report containing:

### Findings

Confirmed defects, significant risks, and maintainability
concerns, prioritised by impact.

### Requirement coverage

What requirements were checked and which remain uncertain.

### Architecture

Adherence to approved decisions and material deviations.

### Tests and evidence

Commands actually executed, results, and real boundaries
verified.

### Limitations

Unavailable checks, environmental constraints,
unverified behaviour, and stale evidence.

### Snapshot

Current fingerprint and relevant baseline information.
Explain what the fingerprint does and does not establish
where necessary.

### Readiness

Verified, Verified with caveats, or Not verified,
for the named reviewed scope, with a brief evidence-based
justification.

Do not claim complete correctness or security.

Do not modify the implementation or begin remediation.
Return findings for developer review.

## Hook integration

Verify is explicitly invoked and read-only.

No automatic completion hook is required.

The snapshot mechanism detects changes relevant to
verification evidence but does not enforce code quality,
prove execution, or prevent completion.

Independent Security review and human approval remain
separate activities.
