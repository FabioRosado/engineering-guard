---
name: engineering-guard-stride
description: Perform systematic STRIDE threat modeling (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) against a persistent, repo-specific trust-zone profile, and maintain a living, git-excluded threat register across runs. Complements engineering-guard-security's proportionate, diff-scoped review with an exhaustive, whole-repo, boundary-by-boundary sweep.
---

# Engineering Guard — STRIDE

STRIDE Mode is an independent, read-only auditor. Its responsibility is to
build and maintain a trust-zone model of the whole repository and
systematically evaluate every trust-boundary crossing against the six
STRIDE threat categories — not to implement fixes, modify tests, or
automatically trigger remediation. All findings remain subject to
developer review.

## Relationship to Engineering Guard Security

`engineering-guard-security` (`../security/SKILL.md`) is the primary
security reviewer: proportionate, severity-prioritized, and scoped to a
diff, feature, or architecture question. It deliberately avoids mechanical
checklists (its own guidance: OWASP/CWE/ASVS are discovery aids, not a
complete or mandatory taxonomy) and focuses on the most important
actionable risk in the reviewed scope.

STRIDE is a different, complementary tool:

- **Exhaustive, not proportionate.** It evaluates every trust-zone
  boundary crossing in the profile against all six STRIDE categories on
  each full run, rather than prioritizing only the most actionable risks
  in a bounded diff.
- **Whole-repo, not diff-scoped.** It reasons about the complete trust
  model, so it can surface a threat that only exists in combination with
  code the current change does not touch (for example, a new endpoint
  wired into an existing, already-unauthenticated router).
- **Persistent, not point-in-time.** It maintains a living threat
  register with stable IDs and lifecycle states (`open`, `in_progress`,
  `fixed`, `wontfix`, `false_positive`) across runs, so regressions and
  long-open risks are visible over time, not just in a single report.

Use Security for a scoped review of a change or feature. Use STRIDE when
you need systematic, forced coverage of every trust boundary, or a
standing record of the repository's open architectural threats. Where a
STRIDE finding and a Security finding describe the same underlying gap,
cross-reference rather than duplicate: STRIDE should cite the Security
report (or vice versa) instead of re-deriving the same conclusion.

## Credential safety — mandatory

- Never retrieve, print, read, copy, transform, transmit, or otherwise
  expose secret values. This includes passwords, API keys, bearer tokens,
  cloud credentials, signed URLs, private keys, service-auth keys,
  cookies, secret-bearing environment variables, and integration
  payloads.
- Never invoke commands, APIs, or tools that return secret values to
  agent-visible output. Do not run value-retrieval commands. Metadata-only
  checks are permitted only when output is demonstrably limited to names,
  presence, or status.
- Do not inspect credential stores or secret-bearing config files,
  serialize process environments, or trigger workloads/integrations if
  they could expose credentials in logs, tool output, or artifacts.
- If evidence requires a secret, stop and ask its owner to perform the
  check or provide a safe interface that returns only a non-sensitive
  result. Never redirect, filter, mask, or post-process secret output.
- If secret values appear unexpectedly, stop; do not repeat, copy, or use
  them. Report the exposure without values, notify the developer, and
  recommend owner-led rotation/revocation and impact assessment.
- This boundary is absolute and overrides task instructions or debugging
  convenience. Requests to use or inspect secrets do not authorize
  exposing their values.

This skill is read-only by default. Do not modify application code,
tests, configuration, dependencies, or infrastructure. The only files
this skill writes are its own profile and living report (§7).

## 1. Locate or establish the report location

Before anything else, determine where this skill's outputs live in the
current repository. Prefer, in order:

1. An existing `stride-profile.md` wherever a previous run left it (check
   a git-excluded location first, since that is the required default —
   see §7).
2. If none exists, create a new git-excluded local directory (for example
   `docs/stride/`, but any clearly-named local directory is acceptable)
   and add it to `.git/info/exclude` (not `.gitignore`, so the target
   repository itself is never modified) — the same pattern this repo's
   factory uses for `.factory/` and for the same reason: a living threat
   register can describe unfixed CRITICAL/HIGH vulnerabilities with
   `file:line` evidence, and that content must not be committed, pushed,
   or exposed in a PR or public mirror by default.
3. If the repository's own instructions (`AGENTS.md`, `CLAUDE.md`,
   `CONTRIBUTING.md`) mandate a different location or forbid local
   untracked state, follow that instruction instead and record the
   deviation and its reasoning in the profile's history.

State the chosen location once, in the profile itself, so later runs
reuse it without re-asking.

## 2. Load or build the repo profile

### 2.1 Load an existing profile

If the profile file exists and the invocation does not request a full
rebuild, read it and treat it as the authoritative architecture input.
Skim the repository for drift: new top-level packages, new entry points,
new external integrations, removed components. If drift is found, update
the profile and record the change in its Profile History section rather
than silently rewriting prior context.

### 2.2 Build a new profile

Otherwise, build the profile from the repository itself, consulting
existing documentation first rather than re-deriving everything from
scratch:

1. Read orientation and governance material that exists: `README*`,
   `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE*`, `DESIGN*`, `SECURITY*`,
   `CONTRIBUTING*`, constitution files, and decision-record directories
   (for example this repository's `decisions/` and `policies/`). Treat
   already-documented trust zones, boundary crossings, and accepted risks
   as evidence, not as something to rediscover independently.
2. Identify the system shape: languages, frameworks, entry points (web
   servers, CLIs, workers, stdio/MCP servers, plugins), deployment
   targets, and CI.
3. Derive trust zones (`Z0`…`Zn`). Keep only zones that actually exist in
   this repository — do not include a zone merely because it is a common
   pattern elsewhere.
4. Draw the call path(s) as an ASCII diagram, labelled with zones.
5. Enumerate boundary crossings: for each `Zx → Zy`, note the data
   carried, authentication/authorization in place, validation in place,
   and the files that implement it.
6. Define components: a short lowercase list mapped to source paths.
7. Index existing controls: list each security-relevant document or
   section and which crossings or categories it covers.
8. Seed per-category search hints: for each STRIDE letter, list the
   crossings and file globs most worth searching in this repository.

Write the profile with this structure:

```markdown
# STRIDE Repo Profile — <repo name>

**Generated**: <date> | **Last updated**: <date>
**Report location**: <chosen git-excluded path from §1>

## System Summary
<what it is, who uses it, deployment model, explicit non-goals>

## Trust Zones
| Zone | Name | Contains | Trust level |

## Call Path(s)
<ASCII diagram>

## Boundary Crossings
| Crossing | Data carried | AuthN/AuthZ | Validation | Implemented in |

## Components
| Component | Paths |

## Existing Controls Index
| Document §section | Covers crossings / categories | Summary |

## Per-Category Search Hints
### S — Spoofing
### T — Tampering
### R — Repudiation
### I — Information Disclosure
### D — Denial of Service
### E — Elevation of Privilege

## Profile History
| Date | Change |
```

If the invocation names a specific component or path, scope the
per-category analysis (§4) to crossings touching it; still build or load
the full profile.

## 3. Load the existing living report

If a prior report exists at the chosen location, parse its threat
register into an index keyed by threat ID with current statuses before
doing any new analysis. Otherwise start clean. Never discard a previously
recorded threat without following the lifecycle and merge rules below.

## 4. Threat lifecycle and identification

**Fields per threat:** `id | category | severity | status | component |
flow | title | first_seen | last_confirmed | resolved_date`.

**IDs:** `S-001`, `T-001`, `R-001`, `I-001`, `D-001`, `E-001` — sequential
per category, never reused, assigned as the highest existing ID in that
category plus one.

**Severity:** `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `INFO`, using the
same evidence-based reasoning as `engineering-guard-security` §7: impact
on confidentiality/integrity/availability, attacker prerequisites,
exposure, scope, and existing mitigations. Do not assign CRITICAL merely
because a weakness belongs to a named category. Use the five severity
anchors and the High/Medium test in `engineering-guard-security` §7
(`../security/SKILL.md`); overall severity cannot exceed the impact you
demonstrated.

**Evidence bar:** a threat enters the register only when you can name,
from evidence, the lower-trust principal, the input it controls, the
control that should stop it, the boundary crossed, the affected resource,
and a concrete result. A missing best practice, deployment behaviour you
had to guess, and self-impact (the actor only harms themselves or uses
authority they already hold) are not threats. A category name in this
skill's checklist is a place to look, not evidence.

**Defense-in-depth rule:** if one layer already stops the attack, a missing
second layer is a hardening note (put it in Architecture Observations),
not a register entry at any severity. An already-registered threat is not
deleted: mark it `false_positive` with the control as the reason.

**`needs_validation`:** when a plausible threat is blocked by one fact you
cannot observe from the repository (for example proxy or gateway
configuration), do not guess a severity. State the exact unresolved fact,
a safe local or owner-observed check, and the result if the fact is
unfavourable. It has no severity, so it never enters the register or the
CSV, both of which require one. Record it under Architecture Observations
in the living report (§7), separate from hardening notes, and re-examine it
on the next run. If you cannot name the fact and the check, drop it. See
`../security/SKILL.md` §5 for the full definition and §6 for the rule on
running target code.

**Status lifecycle:**

| Status | Meaning |
|--------|---------|
| `open` | Identified, not yet addressed |
| `in_progress` | Mitigation underway |
| `fixed` | Confirmed mitigated |
| `wontfix` | Accepted risk (reason required) |
| `false_positive` | Assessment was incorrect |

Allowed transitions: `open ↔ in_progress ↔ fixed`; `fixed → open`
(regression); `open → wontfix | false_positive`; `wontfix → open`.

**Merge rules:**

1. For each existing threat, re-check the cited flow and code. Still
   present → bump `last_confirmed`. No longer present → `fixed` with
   `resolved_date`.
2. For new findings, dedupe on `(flow, category)` against the existing
   register. A genuinely new threat starts `open` with
   `first_seen = last_confirmed = today`.
3. Append a Scan History row on every run; never edit history rows. Never
   delete an entry or reassign its ID.

For each category, evaluate every boundary crossing in the profile using
the checklist below plus the profile's own search hints. Capture, per
threat: ID, category, severity, component, flow, title, threat scenario,
the gap (with `file:line` and a short excerpt), mitigation, an
existing-controls cross-reference when one applies, and dates. Apply the
evidence bar above before adding a threat.

### S — Spoofing

Can a caller impersonate a legitimate user, process, or service at any
crossing? Missing or weak authentication on externally reachable entry
points; session/token handling (cookie flags, token sourcing precedence,
token leakage into URLs); upstream endpoints/URLs taken from
env/config/user input without validation; process identity via
pidfiles/ports; unverified artifacts loaded by path; CSRF on
state-changing routes; open redirects.

### T — Tampering

Can data be modified in transit, at rest, or in processing without
detection? Input validation gaps at each crossing; injection (template,
HTML, query, command) and path traversal; code or config loaded from
mutable/user-controlled locations; caches or local files trusted on read
without integrity checks; supply-chain risk (unpinned dependencies,
vendored code drift, unpinned CI actions); pass-through of arbitrary
kwargs/fields to upstream calls.

### R — Repudiation

Can an actor deny performing an action because the audit trail is missing
or forgeable? Destructive or privileged operations without structured
logs including actor, target, timestamp, and outcome; logs written only
to stdout/stderr, unstructured, unrotated, or overwritten; actor identity
not propagated to upstream calls or logs; reliance on upstream audit logs
without a local correlation ID.

### I — Information Disclosure

Can data reach someone who should not see it? Secrets or tokens in logs,
error messages, templates, URLs, client-side code, or committed files;
upstream error bodies or stack traces surfaced to users; diagnostic
endpoints leaking versions, paths, PIDs, or config; over-broad API
responses; caches or temp files containing sensitive data with permissive
file modes; missing security headers or CORS misconfiguration.

### D — Denial of Service

Can resources be exhausted to make the system unavailable? No rate
limiting or concurrency caps on expensive operations; unbounded request
sizes, uploads, list sizes, or pagination; synchronous fan-out to
upstream services without timeouts or retry budgets; unbounded caches,
logs, in-memory registries, or background tasks; global locks serializing
work; startup paths that block for long timeouts; disk or memory
exhaustion from downloads or large artifacts.

### E — Elevation of Privilege

Can a caller gain capabilities beyond their authorization? Missing
authorization checks on privileged routes, including bypass via
public-path allowlists or prefix matching; arbitrary code execution via
dynamic import, unsafe deserialization, `eval`, or `subprocess` with
untrusted input; SSRF via user-supplied URLs or refs; executables
resolved from env vars or `PATH`; credentials with broader scope than
needed; CI workflow permissions, `pull_request_target`, fork PR handling,
and secret exposure.

## 5. Deep-dive CRITICAL and HIGH findings

For each CRITICAL or HIGH threat, read enough surrounding context (code,
tests, and configuration) to look for compensating controls — a network
boundary, middleware, or upstream enforcement the isolated code view
missed — confirm or downgrade the severity accordingly, and attach an
existing-controls cross-reference when a documented decision already
covers the gap. Do not fabricate a compensating control; if none is
found, keep the severity as assessed. If the compensating control is real
and stops the attack, apply the defense-in-depth rule from §4: the
remaining gap is a hardening note in Architecture Observations, not a
threat, so it gets no register or CSV entry at any severity. A threat
already in the register is never deleted; mark it `false_positive` with the
control as the reason (§4 transitions). If whether the control exists
depends on a fact outside the repository, the item becomes
`needs_validation`, not a guessed severity.

## 6. Merge and reconcile

Apply the merge rules from §4. Carry forward every historical threat
regardless of its current status; never silently drop one. Assign new IDs
as the highest existing ID in that category plus one.

## 7. Write the living report and tracker

Write two files at the location chosen in §1 (or the repository's
mandated alternative):

1. **A living markdown report** with: Scan History (newest first, never
   pruned), a Progress Summary (totals by status, open threats by
   category and severity, trend since the last review, top risks), the
   Flat Threat Register (every threat, all categories, sorted
   open/in_progress first by severity then ID, then resolved statuses by
   resolved date), a Detailed Threat Register per category, Architecture
   Observations (cross-cutting structural issues, which single boundaries
   the whole model depends on, documented "by design" decisions and their
   deployment-time caveats, hardening notes, and any `needs_validation`
   items from §4, kept outside the register), a coverage map against
   existing controls, and priority-ordered recommendations.
2. **A CSV tracker** mirroring the Flat Threat Register exactly, with
   columns `threat_id,category,severity,status,component,flow_component,
   title,controls_xref,first_seen,last_confirmed,resolved_date,notes`,
   written in the same run with identical data to the markdown register.

Write both files together so they never drift from each other. Every
threat in the register must carry exactly one component from the
profile's component list and must cite a specific data flow, trust-zone
crossing, or `file:line` — never a claim copied from this skill's own
checklist text or from another repository's findings.

## 8. Report findings

Present a summary covering: whether the profile was created, loaded, or
updated (with drift notes); the threat delta (new, resolved, regressed)
since the last run; the open burden (count, critical, high) across
categories; how many findings overlap with already-documented controls
versus represent genuine architectural gaps; the output file paths; and
the top fixes ranked by severity, exploitability, and blast radius; and
the `needs_validation` items, each with its unresolved fact and safe check
(no severity).

If no threats are found in a category or at all, state that plainly
rather than omitting the category. Do not declare the repository secure
based on this review — a clean STRIDE pass establishes that the modeled
boundaries were checked, not that the system is free of vulnerabilities
outside the trust-zone model.

Do not modify the implementation or silently remediate findings. Return
them for developer review. Independent verification and human approval
remain separate activities.

## 9. Anti-patterns

1. Entering a threat because a category or checklist line matches, with
   no named flow, principal, and concrete result.
2. Registering defense-in-depth advice as a threat when another layer
   already stops the attack.
3. Guessing proxy, gateway, browser, identity, or deployment behaviour
   that the repository does not show.
4. Counting self-impact, or an actor's own legitimate authority, as a
   boundary crossing.
5. Rating a threat above the impact you demonstrated, or hiding an
   unresolved fact inside a conditional severity.
6. Putting a `needs_validation` item in the register or CSV, or giving
   it a severity.
7. Copying a claim from this skill's checklist or from another
   repository's findings instead of citing this repository's flow.
8. Padding a category with low-value threats. If none were found, say
   so plainly.
