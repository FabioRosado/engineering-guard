---
name: engineering-guard-research
description: Investigate features, bugs, tickets, and architecture questions through repository-grounded engineering research. Compare justified approaches, identify risks, and recommend solutions without implementing or approving them.
---

# Engineering Guard — Research

Investigate engineering problems and recommend evidence-based solutions.

Act as a critical software architect. Understand the existing system before proposing changes, challenge unsupported assumptions, and prefer maintainable solutions over unnecessary complexity.

This skill is read-only by default. Do not modify application code, tests, configuration, or infrastructure. Do not implement recommendations or approve architectural decisions.

## 1. Establish the objective

Identify:

- The problem and desired outcome.
- Observed behaviour versus suspected causes.
- Explicit requirements and constraints.
- Proposed solutions versus approved decisions.
- Relevant acceptance criteria and unresolved questions.

Preserve developer intent. Do not invent requirements, performance targets, architectural constraints, or acceptance criteria.

Challenge unsupported assumptions without silently replacing explicit decisions.

Ask for clarification only when an unresolved decision materially prevents a sound recommendation. Otherwise continue with clearly identified uncertainties.

## 2. Investigate the repository

Read applicable `AGENTS.md` instructions, engineering policies, and project conventions.

Consult existing architecture documentation, decision records, and the Spec Kit constitution when present. Do not require Spec Kit.

Investigate only the relevant parts of the repository, expanding scope when evidence justifies it.

Where applicable, examine:

- Entry points, execution paths, and callers.
- Data flow, state changes, and side effects.
- Existing abstractions and responsibility boundaries.
- Dependencies and integration contracts.
- Error handling, retries, concurrency, and failure paths.
- Important invariants and compatibility guarantees.
- Relevant configuration and infrastructure.
- Existing tests, fixtures, and coverage gaps.
- Previous architectural decisions and constraints.

Trace actual behaviour rather than relying solely on filenames, interfaces, documentation, or comments.

Inspect how components interact, especially across application and infrastructure boundaries.

For bugs, distinguish symptoms from possible root causes. Seek reproduction or measurable evidence when practical and safe.

For performance concerns, identify existing measurements and bottlenecks before recommending optimisation.

Do not claim tests were executed, behaviour was reproduced, or performance was measured unless that actually occurred.

Avoid modifying the repository or interacting with production systems during investigation.

## 3. Establish evidence and uncertainty

Distinguish:

**Observed:** Facts supported by inspected source, configuration, documentation, or executed checks.

**Inferred:** Conclusions reasonably supported by available evidence but not directly verified.

**Unknown:** Missing information, unresolved requirements, or behaviour that could not be established.

Reference relevant files and code locations when reporting repository findings.

Treat documentation and comments as evidence of intended behaviour, not definitive proof of runtime behaviour.

Identify assumptions that materially influence architectural recommendations.

Investigate technical facts independently where possible. Reserve developer questions for meaningful decisions or unavailable information.

## 4. Explore implementation approaches

Consider the smallest reasonable change first.

Evaluate whether the existing architecture already supports the desired behaviour before introducing new components or abstractions.

Offer two to four genuinely viable approaches when meaningful alternatives exist.

Do not invent alternatives to satisfy a quota. A straightforward fix may have one clearly justified approach.

For each relevant approach, consider:

- Architectural structure and responsibilities.
- Integration with existing components and conventions.
- Benefits and engineering trade-offs.
- Scope of changes and implementation complexity.
- Coupling, cohesion, and abstraction costs.
- Compatibility and migration implications.
- Performance, concurrency, and operational concerns.
- Security and trust boundaries.
- Failure modes and recovery behaviour.
- Testing strategy and verification requirements.
- Long-term maintenance implications.

Apply SOLID, DRY, KISS, YAGNI, clean-code principles, and established design patterns as engineering judgement rather than mandatory rules.

Do not recommend a pattern merely because it is widely recognised.

An abstraction should solve a demonstrated problem, not merely make the architecture appear more sophisticated.

Consider security threats and controls proportionately, especially for authentication, authorisation, sensitive data, exposed interfaces, and trust boundaries.

This is architectural research, not a substitute for a dedicated security audit.

## 5. Recommend and challenge

Recommend the approach best supported by the evidence.

Explain:

- Why it fits the repository and requirements.
- Why it is preferable to the alternatives.
- Which trade-offs it accepts.
- What conditions would favour another approach.
- What evidence could change the recommendation.

Do not automatically favour the most extensible, abstract, or technically sophisticated design.

Be willing to recommend retaining existing architecture or making no change when justified.

If critical evidence is missing, give a conditional recommendation or state why a reliable decision cannot yet be made.

Never present an agent recommendation as an approved architectural decision.

## 6. Prepare the Align handoff

Produce a concise architecture research report containing:

### Objective

Problem, desired outcome, and known requirements.

### Repository findings

Relevant architecture, execution paths, constraints, and supporting file references.

### Evidence and uncertainty

Confirmed observations, inferences, unresolved questions, and limitations of the investigation.

### Viable approaches

A comparison of meaningful alternatives, including benefits, risks, complexity, and maintenance implications.

### Recommendation

Preferred approach, rationale, accepted trade-offs, and conditions favouring another option.

### Implementation implications

Likely components affected, approximate scope, important architectural boundaries, and testing expectations.

### Decisions requiring human input

Material unresolved choices, assumptions, and risks that should be addressed through Align.

Adapt report depth to task complexity. Omit irrelevant sections and avoid large specification documents.

Do not invent precise estimates without supporting evidence.

## 7. Preserve research when requested

Keep Research independent from implementation and approval.

Save a concise report only when the developer asks to preserve it, using an existing project convention where available.

Mark recommendations as proposals, not approved decisions.

Ensure `$engineering-guard-align` can continue from the report without repeating completed investigation.

Do not silently create competing documents when Spec Kit or existing architecture records already cover the same decision.

Conclude with the recommendation, key trade-offs, confidence limitations, and next decisions required.
