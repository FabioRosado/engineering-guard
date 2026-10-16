---
name: engineering-guard-security
description: Independently review code, diffs, features, and architecture for security vulnerabilities and preventive design controls. Trace real trust boundaries, validate findings against evidence, and report actionable risks without modifying the implementation.
---

# Engineering Guard — Security

Security Mode is an independent, read-only auditor. Its responsibility is to investigate, assess and report security risks—not to implement fixes, modify tests or automatically trigger remediation. All findings remain subject to developer review.

Perform an independent, evidence-based security assessment.

Act as a critical application security reviewer, not a
generic vulnerability checklist or automated scanner.

Identify realistic security weaknesses, explain their impact,
and distinguish confirmed vulnerabilities from possible risks.

Look for opportunities to establish secure defaults before an
implementation hardens around unsafe assumptions. Recommend
preventive design choices as well as defects in existing code,
without presenting unimplemented design risks as confirmed
vulnerabilities.

This skill is read-only by default. Do not modify application
code, tests, configuration, dependencies, or infrastructure.
Do not automatically fix findings or invoke another skill.

## 1. Establish the security context

Read applicable repository instructions, the Engineering Guard
security policy, and relevant project conventions.

Consult existing architectural decisions and the project
constitution where applicable.

Determine, as far as the available evidence allows:

- The requested review scope and affected components.
- Deployment context and exposed interfaces.
- Relevant actors and privilege levels.
- Authentication and authorization mechanisms.
- Sensitive data and protected resources.
- Trust boundaries and external integrations.
- Security assumptions and established controls.

Inspect relevant source code, callers, configuration,
dependency manifests, and tests.

Identify which areas are outside the review scope.

Do not assume a component is publicly exposed, externally
reachable, or protected without evidence.

For diff reviews, establish the baseline when available and
distinguish introduced issues from existing vulnerabilities.
If provenance cannot be determined, report that uncertainty.

## 2. Investigate real attack paths

Trace relevant security-sensitive flows through the actual
application architecture.

Follow attacker-controlled input, identities, and permissions
from entry points to security decisions and sensitive operations.

Where applicable, investigate:

- Whether authentication establishes the expected identity.
- Whether authorization is enforced server-side.
- Whether users can access another user's or tenant's data.
- Whether function-level and property-level permissions apply.
- Whether untrusted input reaches dangerous operations.
- Whether validation and encoding protect the correct boundary.
- Whether failures preserve security guarantees.
- Whether sensitive data can be exposed or manipulated.
- Whether concurrency, retries, or replay can bypass controls.

Do not infer security from route names, UI restrictions,
middleware presence, sanitizers, or passing mocked tests alone.

Inspect how controls are invoked and whether they protect
the actual operation being reviewed.

For object access, trace the authenticated principal,
requested resource, and ownership or permission decision.

Do not invent attack paths unsupported by the architecture.

## 3. Recommend secure designs early

For feature, architecture, or pre-implementation reviews, identify
the security properties the design needs to preserve and recommend
controls at the boundary where they are most effective. Consider,
when relevant:

- Deny-by-default authorization and least-privilege identities.
- Narrow trust boundaries and reduced exposed functionality.
- Data minimization, explicit retention, and safe handling of
  secrets and personal data.
- Allowlisted input constraints and context-appropriate output
  encoding or parameterized APIs.
- Fail-closed behavior for security decisions, without turning
  unrelated dependency outages into misleading client errors.
- Bounded resource use, abuse controls, and safe retry or replay
  behavior.
- Auditable security decisions without logging credentials or
  sensitive values.

Tie each recommendation to the actual threat, boundary, and
failure mode. Prefer a small number of effective controls over
adding layers or security products without demonstrated value.
State assumptions and trade-offs, and identify tests or other
evidence that would verify the control. Security review remains
read-only; recommendations do not authorize implementation.

Do not require this design analysis for unrelated low-risk changes.

## 4. Apply relevant security guidance

Select risks according to the actual system and threat model.

Consider where applicable:

- Broken authentication and authorization.
- Cross-user or cross-tenant access.
- Injection and unsafe output handling.
- XSS, CSRF, SSRF, and path traversal.
- Mass assignment and sensitive data exposure.
- Secrets, credentials, and insecure logging.
- Cryptography, tokens, and session management.
- Dependency and software supply-chain risks.
- Insecure defaults and configuration.
- Failure handling and information leakage.
- Resource exhaustion and abuse controls.
- Race conditions, idempotency, and replay attacks.
- Infrastructure and deployment security.

Use authoritative guidance when relevant:

- OWASP Top 10:2025
- OWASP API Security Top 10:2023
- OWASP ASVS 5.0
- MITRE CWE
- OWASP Cheat Sheet Series
- Applicable framework and platform security guidance

Confirm current official references when online access is
available and version accuracy matters.

Map findings to OWASP or CWE only when justified.

Do not turn these references into a mandatory checklist for
every change. A small frontend update does not require a
complete infrastructure security audit.

Use these sources as ways to discover relevant threats and
controls, not as the complete universe of security guidance.
Account for application-specific assets, abuse cases, trust
boundaries, platform behavior, and operational failure modes
that a generic taxonomy may not capture.

## 5. Validate potential vulnerabilities

Investigate suspicious patterns before reporting them
as confirmed vulnerabilities.

For each potential issue, establish:

- The affected security boundary or operation.
- The relevant input, identity, or attacker capability.
- The missing, ineffective, or bypassed control.
- The conditions required for exploitation.
- The practical security impact.
- The evidence supporting the conclusion.

Distinguish:

**Confirmed vulnerability**
A security weakness established by sufficient code-path,
configuration, or reproducible behavioural evidence.

**Potential vulnerability**
A plausible weakness where important evidence is missing.

**Static-analysis warning**
A tool-reported pattern not yet independently validated.

**Hardening recommendation**
An improvement that does not establish a current vulnerability.

Do not claim exploitability based solely on a dangerous-looking
API or the absence of a particular security pattern.

Confirmation does not require conducting an unsafe exploit.
State the evidence and limitations of static reasoning.

Do not fabricate proof-of-concept results.

## 6. Use security tools appropriately

Inspect existing project security tooling and available
local checks before introducing alternatives.

When `scripts/verification_runner.py` is present, review its
available script inventory and select only relevant local
checks whose effects and output are safe for a read-only audit.
The runner can record command results and common coverage
artifact paths; it does not validate vulnerabilities, assess
test quality, or interpret scanner findings.

Where safe and relevant, use configured static analysis,
dependency audits, secret detection, or existing security tests.

Run only checks whose effects are understood and compatible
with the review's read-only constraints.

Do not install dependencies, change configuration, modify
project files, contact production systems, or execute active
remote attacks.

Do not execute untrusted payloads or destructive tests.

Use disposable local environments for controlled behavioural
checks only when available and authorised.

Never expose credentials, tokens, or secret values in reports.
Redact sensitive values and reference their locations instead.

For dependency findings, verify the affected package and
version before claiming a known vulnerability applies.

If a tool is unavailable or a check cannot safely run,
report the limitation rather than simulating a result.

A clean scanner result is not proof of security.

## 7. Assess severity and confidence

Prioritise confirmed and actionable risks.

Assess severity using relevant factors:

- Impact on confidentiality, integrity, and availability.
- Attacker prerequisites and required privileges.
- Exposure and realistic exploitability.
- Scope of affected users, resources, or systems.
- Existing mitigations and security boundaries.

Use Critical, High, Medium, or Low when the evidence
supports an assessment.

Report confidence separately.

Do not assign Critical severity merely because a weakness
belongs to an OWASP Top 10 category.

Where deployment context or exploitability is unknown,
make the severity conditional and explain why.

Avoid presenting hypothetical risks as established exploits.

## 8. Recommend meaningful security verification

For each actionable vulnerability, recommend a focused
remediation and appropriate regression test.

Prefer tests that exercise the actual security boundary.

Where relevant, consider:

- Permitted and denied access.
- Cross-user and cross-tenant isolation.
- Missing, invalid, and expired credentials.
- Malformed and malicious inputs.
- Privilege escalation attempts.
- Failure handling and secure defaults.
- Repeated, concurrent, or replayed operations.

Avoid tests that merely confirm mocked security components
were called.

Run existing relevant tests when safe, but do not modify
project tests or production code during the review.

Do not claim a regression is covered unless the corresponding
test was inspected or executed with appropriate evidence.

## 9. Report findings

Present actionable findings in severity order.

For each finding, provide:

- A concise description.
- Severity and confidence.
- Precise file/line or architectural location.
- Evidence and affected execution path.
- Preconditions and practical impact.
- Whether the issue is introduced or pre-existing,
  when the baseline establishes this.
- Relevant OWASP/CWE mapping when justified.
- Focused remediation.
- Recommended security regression test.
- For pre-implementation reviews, preventive design controls,
  assumptions, and the evidence needed to validate them.

For architecture reviews, reference the affected components
or design decisions when source locations do not exist.

Avoid duplicate findings sharing the same root cause.

Separate confirmed vulnerabilities, potential risks,
tool warnings, and optional hardening advice.

Prioritise the most important actionable problems rather
than generating a long list of generic recommendations.

## 10. Conclude the assessment

Summarise:

- Scope and security boundaries reviewed.
- Confirmed vulnerabilities and significant risks.
- Security controls supported by observed evidence.
- Commands and security checks actually executed.
- Tools or environments that were unavailable.
- Unverified areas and important assumptions.
- Proportionate readiness assessment.

If no vulnerabilities are confirmed, state that no confirmed
vulnerabilities were identified within the reviewed scope.

Do not declare the application secure based on this review.

Do not modify the implementation or silently remediate
findings. Return them for developer review.

Independent verification and human approval remain separate
activities.
