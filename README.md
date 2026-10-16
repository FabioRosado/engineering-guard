# Engineering Guard v0.3

Engineering Guard is a repository-local Codex PoC with seven independently invocable skills, reusable engineering policies, a pre-write policy-delivery hook, and a small verification evidence runner.

## Use with Codex

Start Codex at the repository root, then invoke the skill that matches the work:

- `$engineering-guard-research` investigates a request and recommends an evidence-based approach without implementing it.
- `$engineering-guard-implement` makes a focused change and runs proportionate checks.
- `$engineering-guard-testing` designs or audits meaningful behavioral tests.
- `$engineering-guard-verify` independently reviews an implementation without modifying it.
- `$engineering-guard-better-prompt` turns a rough request into a grounded, copy-ready coding-agent prompt. It never executes the prompt.
- `$engineering-guard-align` discusses architecture and maintains a human-approved plan.
- `$engineering-guard-security` performs an independent, read-only security review.

Skills live in `.agents/skills/`; hook definitions are in `.codex/hooks.json`. Codex discovers skills from the repository-local directory. Trust the project through Codex's normal project flow, then review and trust its hooks with `/hooks`. The project does not change global Codex configuration. A changed hook definition needs review again.

Python 3.9 or newer runs the hook and verification tools. Node.js 18 or newer and npm run the JavaScript demonstrations. No third-party Python or npm packages are required.

## Policy delivery

- `SessionStart` supplies the testing policy and records its content digest for the session.
- Before a recognized test-file write, `PreToolUse` supplies a missing or stale testing policy and denies that attempt once; the retry uses normal Codex permissions.
- Before a recognized production-code write, the hook similarly supplies the engineering policy. A mixed production/test edit receives both policies in one denial.
- `SessionStart` after compaction or resume restores policies already delivered to that session. Content digests invalidate stale acknowledgements.
- The hook never approves a write. It enforces policy availability, not policy compliance or code quality.

`PreToolUse` classifies Codex `tool_name` and `tool_input.command` for Bash and `apply_patch`, recognizing common Python and JavaScript/TypeScript test names and code extensions. Bash path parsing is heuristic: computed paths and interactive commands continued through `write_stdin` are not re-intercepted. MCP or specialized write tools and edits outside the covered paths can bypass the hook. Skills and policies remain advisory.

The hook uses `SessionStart` for restoration because Codex emits it with source `compact` after compaction. There is no Stop hook: Codex does not support a Stop matcher, and a blocking Stop can create an automatic continuation prompt. Verify remains explicit and read-only.

## Verification evidence

`python3 scripts/verification_snapshot.py` prints the current worktree fingerprint and reports that prior evidence is missing. Pass a saved fingerprint to classify it as `current` or `stale`. The fingerprint includes `HEAD`, tracked files, and non-ignored untracked files. It does not prove that tests ran or that a human approved a result.

`scripts/verification_runner.py` reuses that snapshot utility to report the Git baseline, changed-file scope, available root npm scripts, command results, common coverage artifact paths, and before/after fingerprints:

```sh
python3 scripts/verification_runner.py
python3 scripts/verification_runner.py --run test --run demo:security
```

The first command inventories without running checks. By default, scope compares the current worktree with `HEAD`; pass `--base <existing-ref>` for a broader branch comparison. Only explicitly selected root npm scripts execute; the runner disables automatic npm pre/post lifecycle scripts, but a selected script may invoke other commands and the runner is not a sandbox. Inspect scripts before running them. The JSON report goes to stdout and is not saved in the source tree. A nonzero check or a worktree change during execution returns a nonzero exit and marks the evidence failed or stale. Coverage artifacts are listed, not interpreted. Captured output may contain sensitive data; command output is capped, commands time out after 120 seconds, and the actual patch is not included in the report.

The runner records execution evidence only. It does not judge test quality, implementation correctness, architecture, security, or whether selected checks are sufficient. Inspect the actual source paths and captured output. Do not treat a passing command as proof that the system works or is secure.

## Deterministic demonstrations

```sh
python3 -m unittest discover -s test -p 'test_*.py'
npm test
npm run demo:shallow
npm run demo:behavior
npm run demo:implement
npm run demo:security
npm run demo:quality
```

The Python test suite covers simulated Codex hook events, snapshots, and the verification runner in disposable Git repositories. `npm test` remains a convenience alias for that suite. These simulations do not prove Codex loaded or trusted the hook.

The checkout demo is intentionally defective: `demo:shallow` passes because it stubs the pricing function, while `demo:behavior` is expected to fail because the implementation charges 9,990 cents instead of the expected 9,000. `demo:implement` checks a focused correction and visible invalid-input failure. `demo:security` exercises cross-user access against vulnerable and corrected fixtures. `demo:quality` runs the same behavior cases against a straightforward function and an unnecessarily layered alternative; it checks behavior equivalence, not readability.

## Evaluating Engineering Guard

Engineering Guard separates three kinds of evidence:

- **Deterministic:** `npm test` and the executable demos establish specified behavior and real command outcomes.
- **Live Codex:** Follow the invocation instructions in `demo/scenarios/` to see whether a skill uses that evidence. These runs are manual integration checks, not part of `npm test`.
- **Qualitative:** Review Better Prompt examples and the engineering-quality scenario for intent preservation, useful steps, appropriate scope, and readable responsibilities. Model judgment is not reported as a deterministic pass/fail guarantee.

The verification runner can collect repeatable command evidence for manual or model-assisted review without adding a separate evaluation framework.

## Scope

This PoC uses repository-local `.codex/`, `.agents/skills/`, policies, scripts, and demos. It adds no dependency, server, MCP integration, or full plugin package, and does not modify global Codex configuration. Full plugin packaging is deferred until distribution beyond this repository is needed.
