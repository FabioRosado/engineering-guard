# Engineering Guard v0.2

Engineering Guard is a repository-local Codex PoC with seven independently invocable skills, reusable policies, and a small pre-write policy-delivery hook.

## Use with Codex

Start Codex at the repository root, then invoke the skill that matches the work:

- `$engineering-guard-research` investigates a request and recommends an evidence-based approach without editing application code by default.
- `$engineering-guard-implement` makes a focused change and verifies it using repository tests or entry points.
- `$engineering-guard-testing` plans or reviews meaningful tests.
- `$engineering-guard-verify` independently reviews a diff or implementation without modifying it.
- `$engineering-guard-better-prompt` turns a rough engineering request or existing prompt into a grounded, copy-ready coding-agent prompt. It never executes the prompt or modifies project files. Quick and Thorough examples are in `demo/scenarios/better-prompt-examples.md`.
- `$engineering-guard-align` turns Research proposals into an interactive architecture plan, persists a draft decision record, and waits for explicit human approval.
- `$engineering-guard-security` performs an independent read-only security review.

Skills live in `.agents/skills/`; Codex discovers repository skills from that directory. Hook definitions live in `.codex/hooks.json`. Trust the project through Codex's normal project flow, then use `/hooks` to review and trust the current local hook definition. Codex will skip project hooks until the project and hook definition are trusted. Engineering Guard does not change global Codex configuration. A changed hook definition needs review again.

Node.js 18 or newer is required for the hook and test suite.

## Policy delivery and enforcement

- On `SessionStart`, the existing Testing Guard behavior adds `policies/testing-policy.md` to context and records its content digest for that session.
- Before a recognized test-file write, `PreToolUse` checks the testing-policy digest. If missing or stale, it denies that attempt once, supplies the current policy, records the digest, and lets a retry use normal Codex permission handling.
- Engineering policy is progressive: it is not loaded at session start unless already relevant to that session. Before a recognized production-code write, `PreToolUse` supplies `policies/engineering-policy.md` and denies that attempt once. A mixed production-and-test edit gets all missing policies in one denial.
- When the same session starts again after resume or compaction, the hook restores the testing policy and any engineering policy already delivered to that session. Content digests invalidate stale acknowledgements.
- The hook never approves a write. On retry, normal Codex permissions still apply.

The hook uses Codex `tool_name` and `tool_input.command` for Bash and `apply_patch`. It recognizes the existing Python and JavaScript/TypeScript test naming patterns and common code-file extensions. It is a policy-delivery guardrail, not a complete enforcement boundary: heuristic Bash path parsing can miss computed paths, interactive commands continued through `write_stdin` are not re-intercepted, and MCP writes, specialized tools that opt out, or changes outside the covered Codex paths can bypass it. It does not judge subjective architecture or code quality. Skills and policy prose remain advisory.

The hook uses `SessionStart` for policy restoration rather than a `PostCompact` hook: Codex emits `SessionStart` with source `compact` after compaction. No `Stop` completion hook is configured: Codex does not support a Stop matcher, so the event cannot be limited to code-changing tasks; blocking Stop creates an automatic continuation prompt. Although Codex exposes `stop_hook_active` for loop protection, that does not solve the scoping problem. The Verify skill remains explicit and read-only. Its worktree fingerprint detects missing or stale evidence without claiming that a hook can reason about code quality or security. `PostToolUse` is not used for policy delivery because the write has already run.

`node scripts/verification-snapshot.mjs` reports a missing prior receipt and the current fingerprint; pass a previous fingerprint to classify it as `current` or `stale`. The fingerprint includes `HEAD`, tracked files, and non-ignored untracked files, so edits, additions, deletions, and commits invalidate it. Git-ignored files are outside the snapshot, and a fingerprint does not prove that reported tests ran or that a human approved the result.

## Checks and demonstrations

```sh
npm test
npm run demo:shallow
npm run demo:behavior
npm run demo:implement
npm run demo:security
```

The automated hook tests simulate Codex's `SessionStart`, `SessionEnd`, and `PreToolUse` payloads, including `apply_patch` and Bash `tool_input.command`, unrelated operations, session isolation, policy changes, compaction restoration, and mixed source/test edits. These are simulated events, not proof that Codex loaded or trusted the hook.

The seeded checkout demo remains intentionally flawed: `demo:shallow` passes because it stubs the pricing function, while `demo:behavior` is expected to fail because pricing subtracts 10 cents instead of applying a 10% discount. `demo:implement` checks the separate before/after exercise for readable calculation and visible invalid-input failure. `demo:security` confirms a cross-user record-access regression fails on a vulnerable fixture and passes on its corrected counterpart. Align and Security walkthroughs are in `demo/scenarios/`.

## Scope

This PoC uses only repository-local `.codex/hooks.json`, `.codex/hooks/`, `.agents/skills/`, and `policies/`. It does not package a plugin, add a server or dependency, publish, or modify global Codex configuration. Use the full plugin packaging flow later if distribution beyond this repository becomes a requirement.
