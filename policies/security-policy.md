# Engineering Guard — Security Policy

Security assessments must be independent, evidence-based,
proportionate to the reviewed system, and read-only.

The objective is to identify realistic vulnerabilities and
security risks, not to maximise the number of findings.

## Review boundaries

- Do not modify application code, tests, configuration,
  dependencies, or infrastructure during an audit.
- Do not automatically remediate findings or invoke
  implementation workflows.
- Establish the review scope, relevant threat model,
  exposure, and trust boundaries before assessing risks.
- Distinguish newly introduced vulnerabilities from existing
  issues when reliable baseline evidence is available.

## Security investigation

- Trace untrusted inputs, identities, and sensitive operations
  through the actual execution and trust boundaries.
- For design and pre-implementation reviews, recommend a small
  set of threat-relevant preventive controls and secure defaults
  before unsafe assumptions become embedded in implementation.
- Distinguish preventive design recommendations from confirmed
  vulnerabilities in existing behavior.
- Verify that security controls protect the relevant operation;
  do not infer safety from the presence of middleware,
  validation functions, or frontend restrictions alone.
- Require server-side authorization for protected resources.
  Client-supplied identifiers do not establish access rights.
- Consider applicable authentication, authorization, injection,
  data exposure, dependency, configuration, and infrastructure
  risks according to the actual architecture.
- Do not manufacture vulnerabilities or apply security
  checklists mechanically.

## Evidence and classification

- Investigate suspicious patterns before reporting them
  as confirmed vulnerabilities.
- Separate confirmed weaknesses, potential vulnerabilities,
  static-analysis warnings, and optional hardening advice.
- Assess severity using realistic impact, exploitability,
  exposure, attacker prerequisites, and existing controls.
- Report confidence separately from severity.
- Do not claim exploitability or successful reproduction
  without supporting evidence.
- A clean security scan does not establish that a system
  is secure.

## Safe verification

- Use existing project tooling and local security checks
  when relevant and safe.
- Do not install dependencies or modify project configuration
  as part of an audit.
- Do not actively test production or other remote systems
  without explicit authorization.
- Keep exploit demonstrations and potentially destructive
  security tests inside authorized, disposable environments.
- Do not expose credentials, tokens, secrets, or sensitive
  user data in reports or tool output.
- Redact sensitive values and identify affected locations
  instead.

## Findings and reporting

- Report actionable findings with supporting evidence,
  relevant code locations, preconditions, practical impact,
  severity, confidence, and focused remediation.
- Recommend regression tests that exercise the actual
  security boundary rather than merely mocked controls.
- Map findings to OWASP, CWE, or other security references
  only when the classification is justified.
- Report checks actually executed, tools unavailable,
  assumptions, and important areas left unverified.
- If no vulnerabilities are confirmed, state that none
  were identified within the reviewed scope.
- Never claim an application is completely secure based
  on a limited assessment.

Security findings must be returned for developer review.
Remediation, implementation, and final approval remain
separate responsibilities.
