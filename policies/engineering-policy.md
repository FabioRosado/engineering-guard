# Engineering Guard — Engineering Policy

Engineering decisions should prioritise correctness, readability,
maintainability, and clear intent over token efficiency,
minimum line counts, or unnecessary architectural sophistication.

## Readability and naming

- Prefer descriptive names that communicate purpose and domain
  meaning. Use conventional abbreviations when unambiguous.
- Write code for future maintainers, not for minimum token
  consumption or artificially compact implementations.
- Prefer straightforward control flow and explicit behaviour
  over clever expressions that obscure intent.

## Comments and documentation

- Explain why non-obvious decisions, business rules, constraints,
  workarounds, and invariants exist.
- Preserve important engineering context near the code it affects,
  particularly when future changes could violate an assumption.
- Do not add comments that merely narrate obvious operations.
- Keep comments accurate when changing the behaviour they describe.
- Comments explain intent; they do not replace executable tests.

## Abstractions and architecture

- Introduce abstractions when they provide meaningful cohesion,
  encapsulation, reuse, comprehension, or integration boundaries.
- Do not introduce wrappers, interfaces, factories, or dependency
  injection solely to make code easier to mock.
- Avoid trivial helper functions that merely return values or
  forward calls without expressing a meaningful responsibility.
- Small functions are appropriate when they improve clarity or
  capture a genuine domain concept.
- Prefer established repository patterns unless evidence
  justifies a different approach.
- Apply SOLID, DRY, KISS, YAGNI, and established design patterns
  as engineering judgement, not mandatory checklists.
- Avoid speculative abstractions, premature optimisation,
  and unrelated refactoring.

## Behaviour and error handling

- Preserve existing contracts, invariants, and unrelated
  observable behaviour unless a change is explicitly required.
- Handle errors explicitly and consistently with project
  conventions. Do not swallow failures or fabricate success.
- Preserve useful error information and document important
  failure behaviour when the code cannot make it clear.
- Prefer understandable, predictable behaviour over hidden
  fallbacks or unnecessary defensive complexity.

## Changes and verification

- Understand relevant callers, execution paths, dependencies,
  and affected boundaries before modifying code.
- Make the smallest coherent change that satisfies the
  requirements, not necessarily the change with the fewest lines.
- Verify affected behaviour using the smallest appropriate
  combination of real tests, integration checks, or application
  entry points.
- Do not mistake passing heavily mocked tests for proof that
  the application works.
- Follow the separate Testing and Security policies when
  those concerns apply.
