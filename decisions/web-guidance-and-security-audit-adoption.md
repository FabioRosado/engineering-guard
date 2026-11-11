# Adopt Modern Web Guidance and Cloudflare security-audit ideas

**Status:** UNAPPROVED Research proposal (2026-11-11). Its path does not imply approval; Align may revise this record.
**Revision:** 1 (2026-11-11)

Approval does not itself authorise implementation.

## Objective

Improve Engineering Guard with two external skills:

1. **Modern Web Guidance (MWG)**, `GoogleChrome/modern-web-guidance`: steers agents toward
   modern web-platform features.
2. **`cloudflare/security-audit-skill`**: a multi-phase security audit with an evidence bar and
   independent verification.

Developer questions behind this: should MWG feed the security and UI checks, and can the Cloudflare
skill improve the security one?

## Evidence and uncertainty

**Observed**

- MWG is a generator-side skill, not an auditor. Its CLI (`modern-web-guidance`) has `search`,
  `retrieve <id>` and `legacy-scan <dir>`. The npm package is `1.0.0`, Apache-2.0, published with
  SLSA provenance, and **requires Node >= 22**. `README.md` says Node.js 18 or newer for this repo's JavaScript tools, so MWG must stay optional.
- MWG without a configured Baseline target defaults to "Widely available".
- MWG has a Security category (validate-origins, Trusted Types, Sanitizer, SRI/CORS/Referrer Policy,
  Connection Allowlists, Local Network Access, passkeys). These are browser-side hardening guides,
  not application-security review.
- The Cloudflare skill (MIT) is a whole-repo audit: recon, coverage ledger, hunters, fresh
  verifiers that try to disprove each candidate, schema-validated `findings.json`, report. It
  overlaps `engineering-guard-stride` (whole-repo, persistent), not the per-diff
  `engineering-guard-security`.
- Our factory reviewers are read-only and work from `round-N/change.patch`
  (`roles/review-*.md`). `factory_board.py` enforces the `FINDING:` line format and a
  CRITICAL/HIGH floor only for roles in `SEVERITY_GATED_ROLES = {"security", "stride"}`
  (`factory_board.py:54`). UX and UI have no severity floor, so a `CHANGES` there blocks a round
  at any severity.
- `policies/security-policy.md` is not auto-delivered by the hook (README says so), so the skill text
  is the real carrier of security rules.

**Not read / not run (verify before implementing)**

- I did not run any MWG command, including `legacy-scan`, so its output format and usefulness
  on `ui/` (Svelte) are unknown.
- I read upstream `SKILL.md`, `CLIENT-SIDE.md` and `VALIDATION-AND-REPORTING.md` only. I did not read
  `AI-AND-LLM.md`, `SUPPLY-CHAIN-AND-RELEASE.md`, `ATTACK-CLASSES.md` or the validators.
- Whether the plugin packaging picks up a new `security/classes/` folder (`.codex-plugin/plugin.json`
  points at `./.agents/skills/`) is inferred, not tested.

## Approaches and judgement

| # | Approach | Verdict | Reason |
|---|---|---|---|
| A | Install both upstream skills as-is next to ours | **Rejected** | Two competing whole-repo auditors (Cloudflare skill vs STRIDE). Cloudflare skill needs an OS sandbox and writes to `~/security-audit-skill/`, which conflicts with `.factory/` and credential-safety rules. MWG would be loaded unpinned and unscoped. |
| B | Port ideas into our own skills and roles; keep MWG as an optional, pinned builder aid | **Recommended** | Matches the existing structure (skills as prose, board as the only enforcer). Smallest change. Keeps our credential-safety block as the overriding rule. |
| C | Port the full audit pipeline (ledger, hunters, schema, validators) | **Deferred** | Many agents per run and a budget model. STRIDE's register already gives cross-run persistence. Revisit only if STRIDE runs prove too shallow. |
| D | Add adversarial verifier stage to the factory | **Deferred to its own record** | Valuable but changes the board state machine. See Phase S3. |
| E | Use MWG `legacy-scan` as an optional quality-gate scanner | **Deferred** | Fits the optional-scanner pattern in `decisions/quality-gate.md` (warn when absent, record `skipped`), but output format is unknown. Decide after the Phase W0 dogfood. |

## Plan

Two independent tracks. Each phase ships on its own.

### Track W: Modern Web Guidance

**W0. Dogfood (no repo change).** Run `npx modern-web-guidance@1.0.0 legacy-scan ui/` and two
`search`/`retrieve` queries against the Svelte dashboard. Human reads the output.
*Go* when the scan finds real, actionable legacy patterns without large noise. *No-go* ends Track W,
and only the Security pointers in W3 are kept. Needs Node >= 22 and network, and executes
unpinned-by-default code, so pin the version.

**W1. Spec-writer.** `roles/spec-writer.md`: when `UI impact: yes`, record a
`Baseline target:` line. Take it from the target repo's `AGENTS.md`/`CLAUDE.md`; otherwise write
`Widely available (default)`. No `factory_board.py` change; the field is prose like the others.

**W2. Builder.** `roles/builder.md`: when the spec has `UI impact: yes` and Node >= 22 is available,
run `npx modern-web-guidance@<pinned> search "<task>"`, retrieve at most the 1-3 most relevant
guides, and follow them within the Baseline target. Add a `Modern web guidance consulted:` line to
`build.md` (guide ids, or `skipped: <reason>`). Never block on a missing CLI, Node or network. The
builder is not read-only, so running the CLI there does not break reviewer constraints.

**W3. Reviewers (advisory only).**

- `roles/review-ui.md`, `roles/review-ux.md`: add one bullet "Platform primitives: native
  `<dialog>`, Popover, `:user-invalid`, container queries etc. used where the Baseline target
  allows, rather than hand-rolled JS". Instruct: report these as `SEVERITY: INFO` under
  `VERDICT: PASS`; never use `CHANGES` for modernisation alone. Reason: UX/UI have no severity
  floor, so otherwise a style suggestion burns one of the 2 review rounds.
- Reviewers do not run the CLI (read-only, cheap models, network). They compare the diff with the
  guide ids listed in `build.md`.
- Security side: add MWG's browser-hardening guides as *pointers* inside the client-side companion
  (S2), as hardening recommendations, never as findings on their own.

**Out of scope for W:** vendoring guides into the repo, installing MWG globally, using it in
verify/stride/approver, making modernity blocking.

### Track S: security-audit ideas

**S1. Evidence bar, prompt-only (highest value, no board change).**

Edit `security/SKILL.md`, `stride/SKILL.md`, `roles/review-security.md`, `roles/review-stride.md`,
and add a short matching paragraph to `policies/security-policy.md`.

- **Candidate gate** (security §5, stride): a confirmed finding names the lower-trust principal, the
  input, the intended control, the boundary crossed, the affected resource and a concrete result.
  Missing best practice, guessed deployment behaviour and self-impact are not findings.
- **Defense-in-depth rule:** if layer A stops the attack, a missing layer B is a hardening note.
- **Severity anchors** (security §7): add the five calibration anchors and the high/medium test
  ("does the result fully defeat an explicit control with real consequences, or only weaken it?").
  Overall severity cannot exceed demonstrated impact. This lines up with the existing
  CRITICAL/HIGH blocking floor in the board.
- **`needs_validation`:** an exact unresolved fact (for example "depends on proxy config not in the
  repo") plus a safe local or owner-observed check. Reported in prose under `PASS`, no `FINDING:`
  line, because the board's format requires a severity.
- **Anti-patterns list** at the end of both skills (adapted, not copied).
- **Execution safety** (security §6): run target code only in a no-network, allowlisted-env,
  resource-limited sandbox; otherwise report `needs_validation`.
- Keep our credential-safety block verbatim and above all added text.

**S2. Attack-class companions.** New folder `security/classes/`, each file 400-700 words in our
voice with an attribution line to the MIT upstream, loaded by the reviewer only when the diff
touches that surface:

1. `client-side.md` (also hosts the MWG hardening pointers from W3),
2. `ai-llm.md` (this repo ships skills, prompts and hooks),
3. `supply-chain.md` (npm and Python manifests, CI, hooks, plugin install).

Later, only if needed: web-protocol-auth, cloud-deployment, data-isolation. Add a "when to load" table
to `security/SKILL.md` §4 replacing the generic list for those surfaces. Each companion keeps the
upstream's "core discipline" block (source + sink + victim impact) and its validation rules.
Read the three upstream files in full first (two are unread).

**S3. Adversarial verification (separate decision record, needs approval).** Before a
`CHANGES` from `security` or `stride` blocks the builder, a fresh agent that did not write the
finding tries to disprove each CRITICAL/HIGH finding and returns `UPHELD` or `REFUTED`. Needs:
a role file, a board state/transition, tests in `test/test_factory_findings.py` and
`test/test_factory_board.py`, dashboard display. Cost: one extra agent per blocking finding.
Cheaper existing mechanism to measure first: the `disputed` status and builder rebuttal in
`roles/findings.md`. Start S3 only if S1/S2 do not reduce false-positive `CHANGES`.

**Not adopting:** coverage ledger, `findings.json` schema and Node validators, `~/security-audit-skill/`
output directory, hunter-wave orchestration, run profiles and cost budget.

## Files affected

| Phase | Files |
|---|---|
| W1-W3 | `roles/spec-writer.md`, `roles/builder.md`, `roles/review-ui.md`, `roles/review-ux.md`, `docs/factory.md` (one short paragraph) |
| S1 | `security/SKILL.md`, `stride/SKILL.md`, `roles/review-security.md`, `roles/review-stride.md`, `policies/security-policy.md` |
| S2 | new `security/classes/*.md`, `security/SKILL.md` §4 |
| S3 | `factory_board.py`, new role, tests, UI (only if approved) |

All under `.agents/skills/factory/` or `.agents/skills/` unless noted. W and S1/S2 are text-only, so no
`factory_board.py` change.

## Verification

- Text-only phases: run `python3 -m unittest discover -s test -p 'test_*.py'` to confirm the
  board is unaffected, then run one factory job on a small web diff and read the reviewer files.
- W: a job with `UI impact: yes` shows the `Baseline target:` line in `spec.md` and the
  `Modern web guidance consulted:` line in `build.md`. A job with Node < 22 shows `skipped`, not a
  blocked build.
- S1: replay one past `review-security.md` from `.factory/` against the new rules and confirm that
  self-impact or defence-in-depth findings are now downgraded.
- S2: a diff that touches `innerHTML` makes the reviewer cite the client-side companion; a
  diff that touches only Python does not load it.

## Risks and trade-offs

- **Advisory text is skipped by agents** (the reason `decisions/quality-gate.md` exists). S1 and W
  rules are not machine-enforced; accepted for now, W3's `INFO` convention is the soft guard.
- **Token cost** of more role text on cheap-model reviewers; mitigated by loading companions only on
  matching diffs.
- **Licence:** MIT needs the copyright notice if substantial text is copied. Plan rewrites in our own
  voice and adds an attribution line.
- **Supply chain:** MWG runs via `npx`. Pin the version, builder only.
- **Upstream drift:** MWG guides change weekly; we vendor nothing, so no drift on our side, but
  build results vary by day.

## Decisions requiring human input

1. Approve Track W as scoped (builder aid + advisory reviewer bullet), or limit to the Security
   pointers only?
2. Should "potential vulnerability" in `security/SKILL.md` §5/§7 lose conditional severity, in
   favour of the `needs_validation` model? This changes existing wording and calibration.
3. Companion order for S2 (proposed: client-side, ai-llm, supply-chain).
4. Run W0 first and gate Track W on it (recommended)?
5. Start S3 now, or only after measuring S1/S2?
