# Engineering Guard v0.3

Engineering Guard packages eight reusable agent skills (including a software factory orchestrator) and a policy-delivery hook as a local Codex plugin. The repository also keeps its project-local setup, reusable policies, verification evidence runner, and demos. MIT licensed; see [Contributing](CONTRIBUTING.md).

## Use with Codex

Start Codex at the repository root, then invoke the skill that matches the work:

- `$engineering-guard-research` investigates a request and recommends an evidence-based approach without implementing it.
- `$engineering-guard-implement` makes a focused change and runs proportionate checks.
- `$engineering-guard-testing` designs or audits meaningful behavioral tests.
- `$engineering-guard-verify` independently reviews an implementation without modifying it.
- `$engineering-guard-better-prompt` turns a rough request into a grounded, copy-ready coding-agent prompt. It never executes the prompt.
- `$engineering-guard-align` discusses architecture and maintains a human-approved plan.
- `$engineering-guard-security` performs an independent, read-only security review.
- `$engineering-guard-factory` runs a feature through a spec → human spec approval → build → parallel review → escalate loop. See [Software factory](#software-factory).

Skills live in `.agents/skills/`; project hook definitions are in `.codex/hooks.json`. Codex discovers skills from the repository-local directory. Trust the project through Codex's normal project flow, then review and trust its hooks with `/hooks`. A changed hook definition needs review again.

### Install in Codex desktop

The local marketplace at `.agents/plugins/marketplace.json` exposes the repository root as the Engineering Guard plugin. From this repository root, register that marketplace once:

```sh
codex plugin marketplace add .
```

Restart Codex, open the Plugins Directory, select the Engineering Guard marketplace, and install the plugin. Review and trust its bundled hooks with `/hooks`; installing a plugin does not automatically trust its hooks. The plugin loads the skills and hook implementation from this repository package, so keep this checkout in place. After updating the checkout, refresh the marketplace and restart Codex:

```sh
codex plugin marketplace upgrade engineering-guard
```

The plugin's skills are available through supported local-marketplace clients. Its lifecycle hooks are supported for plugins installed manually in Codex desktop; this repository does not claim CLI hook support. The source repository disables the user-installed plugin in `.codex/config.toml` so its existing local skills and hook run without duplicates. Other repositories need no project-local plugin registration. To remove the plugin, uninstall or disable it in the Plugins Directory, then remove the marketplace with `codex plugin marketplace remove engineering-guard`.

Python 3.9 or newer runs the hook and verification tools. Node.js 18 or newer and npm run the JavaScript demonstrations. No third-party Python or npm packages are required, with two optional exceptions: the factory dashboard (`ui/`, Svelte and Vite) and the factory's mermaid diagram validator, which uses `jsdom` and `mermaid` (about 180 MB installed, Node.js 20.19+, 22.13+ or 24+). Install it with `npm install --prefix .agents/skills/factory/validator`; without it the factory still works and only warns that diagrams were not syntax-checked.

## Software factory

`/engineering-guard-factory` (or `$engineering-guard-factory` in Codex) turns the session into an orchestrator that reuses the other skills as stages:

```
feature ─► spec-writer ─► [human approve-spec] ─► builder ◄────────────┐
             (better-prompt + research)           (implement + testing)  │
                                         test-auditor (testing) ─ CHANGES ┤
                                                      ▼ PASS             │
            security · ux · ui · code · architecture ── wait for all ────┤ CHANGES, ≤2 rounds
            (security)  (checklists)  (verify)  (proposal vs built)       │
                                   ▼ all PASS / N/A
                    approver (verify) ─► ESCALATE ─► needs-human
```

Commands: `models <preset>|<expensive> <cheap>`, `<feature>`, `next`, `approve-spec <id>`, `approve <id>` (read-only branch/commit/PR suggestion), `rework <id> <note>`.

- The definition lives once in `.agents/skills/factory/` (orchestrator, `roles/`, `presets.json`, dashboard). Codex and Kilo load it from `.agents/skills/`; Claude Code does not read `.agents/skills/`: from the target repo run `python3 <this checkout>/.agents/skills/factory/scripts/factory_board.py models <preset> --cli claude` and then `... install-claude`, which writes an absolute-path skill pointer to `~/.claude/skills/engineering-guard-factory/` and model-pinned `eg-*` subagents to `~/.claude/agents/`. Re-run both after changing models; the install is user-wide, so the last configured models apply in every repo.
- `scripts/factory_board.py` inside the skill is the only writer of `board.json` and enforces the rules: verdict headers, a test audit before reviews, wait-for-all, the round limit, the human spec gate, a clean worktree at build start, mermaid syntax in the job's `handover.md`, and an approver that can only `ESCALATE`.
- Model presets (`opus-sonnet`, `sonnet-haiku`, `sol-luna`, `luna`) map an expensive and a cheap model per CLI. Preset model IDs are unverified defaults; pass explicit IDs with `models <expensive> <cheap>` if they do not resolve. A CLI that cannot pin a model per subagent runs that stage on the session model and the board records the fallback.
- `handover.md` is an optional per-job summary with an executive summary and, only where useful, mermaid architecture, flow or sequence diagrams. The spec-writer writes it as the proposal, the builder keeps it describing what was built (`spec.md` stays frozen), and the approver finalises it; `decision.md` then only points to it. A fifth reviewer, `architecture`, compares the proposal and the diagrams with the diff, and is skipped when the spec says `Architecture impact: no` and the handover has no diagram. The board checks diagram syntax and warns when code changed but the handover did not; it cannot check that a diagram is correct, which is the reviewer's judgement. The dashboard opens a job with a handover on an Overview tab that renders it, diagrams included; a diagram that cannot be drawn shows its error and source.
- Builder changes stay uncommitted on the current branch. The factory never commits, pushes or merges.
- All state lives in the target repo's `.factory/`, excluded through `.git/info/exclude` so no factory files are added to that repository. View it with `npm run dashboard` from this checkout (it builds the Svelte UI on first run, then serves it with the central server at <http://localhost:5173/>). The UI needs Node.js 20.19+ or 22.12+; its packages install under `ui/` and stay out of Git.

Full usage guide: [`docs/factory.md`](docs/factory.md). The design and its approval are recorded in `decisions/engineering-guard-factory.md`.

## Policy delivery

- `SessionStart` supplies the testing policy and records its content digest for the session.
- Before a recognized test-file write, `PreToolUse` supplies a missing or stale testing policy and denies that attempt once; the retry uses normal Codex permissions.
- Before a recognized production-code write, the hook similarly supplies the engineering policy. A mixed production/test edit receives both policies in one denial.
- `SessionStart` after compaction or resume restores policies already delivered to that session. Content digests invalidate stale acknowledgements.
- The hook never approves a write. It enforces policy availability, not policy compliance or code quality.

`PreToolUse` classifies Codex `tool_name` and `tool_input.command` for Bash and `apply_patch`, recognizing common Python and JavaScript/TypeScript test names, pytest support files, and code extensions. Bash path parsing is heuristic: computed paths and interactive commands continued through `write_stdin` are not re-intercepted. MCP or specialized write tools and edits outside the covered paths can bypass the hook. The separate security policy is not automatically delivered for security-sensitive changes. Skills and policies remain advisory.

The hook uses `SessionStart` for restoration because Codex emits it with source `compact` after compaction. There is no Stop hook: Codex does not support a Stop matcher, and a blocking Stop can create an automatic continuation prompt. Verify remains explicit and read-only.

## Verification evidence

`python3 scripts/verification_snapshot.py` prints the current worktree fingerprint and reports that prior evidence is missing. Pass a saved fingerprint to classify it as `current` or `stale`. The fingerprint includes `HEAD`, staged index entries, tracked files, and non-ignored untracked files. It does not prove that tests ran or that a human approved a result.

`scripts/verification_runner.py` reuses that snapshot utility to report the Git baseline, changed-file scope, available root npm scripts, command results, common coverage artifact paths, and fingerprints before and after each selected check:

```sh
python3 scripts/verification_runner.py
python3 scripts/verification_runner.py --run test --run demo:security
```

The first command inventories without running checks. By default, scope compares the current worktree with `HEAD`; pass `--base <existing-ref>` for a broader branch comparison. Only explicitly selected root npm scripts execute; the runner disables automatic npm pre/post lifecycle scripts, but a selected script may invoke other commands and the runner is not a sandbox. Inspect scripts before running them. The JSON report goes to stdout and is not saved in the source tree. A nonzero check or a worktree change during execution returns a nonzero exit and marks the evidence failed or stale. Coverage artifacts are listed, not interpreted. Captured output may contain sensitive data; command output is capped, commands time out after 120 seconds, and the actual patch is not included in the report.

Each executed check reports `commandOutcome` separately from `cleanup.status`; aggregate `outcome` is successful only when the command passed and cleanup is `not_needed` or `complete`. `not_needed` means cleanup was not triggered; it does not assert that every descendant is gone. `incomplete` means the direct process, a tracked POSIX process group, or an output reader remained active at the cleanup deadline. `uncertain` means the runner could not verify descendant cleanup, including after an attempted cleanup on Windows. On POSIX, `complete` means the direct process was reaped, output readers stopped, and the tracked process group was observed absent. It does not prove that descendants which escaped that group and closed their pipes have terminated. Signals sent are recorded as actions, not proof that processes exited. If any cleanup is incomplete or uncertain, the report omits the after-snapshot and sets `unchangedDuringChecks` to `null`.

After timeout, output overflow, a runner `SIGINT`/`SIGTERM`, or a direct-process exit that leaves tracked processes or output readers active, termination, escalation, process reaping, and reader shutdown share one five-second monotonic cleanup deadline. A selected script can therefore take up to its 120-second command timeout plus this cleanup budget. An interrupt marks the command failed with `EINTR` and the runner reports the cleanup result. On POSIX the runner starts a new session and observes and terminates its process group, including members that remain after `npm` exits. This does not detect descendants that escape the group and close their pipes. On Windows the runner bounds direct-process termination and reader waiting, but descendant termination remains best effort and unverified; full Windows process-tree containment is not claimed.

The runner records execution evidence only. It does not judge test quality, implementation correctness, architecture, security, or whether selected checks are sufficient. Inspect the actual source paths and captured output. Do not treat a passing command or a complete tracked-group cleanup observation as proof that the system works, is secure, or that every escaped descendant has terminated.

## Deterministic demonstrations

```sh
python3 -m unittest discover -s test -p 'test_*.py'
npm test
npm run demo:shallow
npm run demo:behavior
npm run demo:implement
npm run demo:security
npm run demo:quality
npm run demo:python-startup
```

The Python test suite covers simulated Codex hook events, snapshots, and the verification runner in disposable Git repositories. `npm test` remains a convenience alias for that suite. These simulations do not prove Codex loaded or trusted the hook.

The checkout demo is intentionally defective: `demo:shallow` passes because it stubs the pricing function, while `demo:behavior` is expected to fail because the implementation charges 9,990 cents instead of the expected 9,000. `demo:implement` checks a focused correction and visible invalid-input failure; its scenario explains how to set up the failing starting state in a disposable copy. `demo:security` exercises cross-user access against vulnerable and corrected fixtures. `demo:quality` runs the same behavior cases against a straightforward function and an unnecessarily layered alternative; it checks behavior equivalence, not readability. `demo:python-startup` demonstrates resource ownership and startup failure cleanup in original, standard-library-only Python code; see `demo/scenarios/python-startup.md` for the exercise.

## Evaluating Engineering Guard

Engineering Guard separates three kinds of evidence:

- **Deterministic:** `npm test` and the executable demos establish specified behavior and real command outcomes.
- **Live Codex:** Follow the invocation instructions in `demo/scenarios/` to see whether a skill uses that evidence. These runs are manual integration checks, not part of `npm test`.
- **Qualitative:** Review Better Prompt examples and the engineering-quality scenario for intent preservation, useful steps, appropriate scope, and readable responsibilities. Model judgment is not reported as a deterministic pass/fail guarantee.

The verification runner can collect repeatable command evidence for manual or model-assisted review without adding a separate evaluation framework.

### Developing a skill incrementally

For a material skill change, identify one agent behaviour to improve and an existing scenario that could expose the failure. Record a baseline live run when practical, make the smallest change to the owning skill, then repeat the scenario and relevant deterministic checks. Add a new scenario only when existing ones cannot expose the behaviour. Record a human promotion decision; passing fixture tests alone does not establish that the agent followed the skill.

Keep a short evaluation record for each material revision, in the change or its review notes rather than a mandatory new repository file:

```text
Skill and revision: <path and commit or worktree fingerprint>
Target behaviour and scenario: <expected action and unacceptable outcome>
Run context: <client, model, date, relevant settings>
Observed: <baseline and revised outputs or links; expected criteria met/not met and why>
Checks: <commands, results, expected failures, and unverified boundaries>
Human decision: <promote, revise, or defer; reviewer and reason>
```

For work involving several dependent steps, use the client's transient task list to track the next coherent, verifiable increment and its check. Update it from observed results, not intended progress. A checked task is not evidence that a requirement works; small changes need no tracker, and no separate persistent tasks file is required. Preserve the distinction between a skill's promotion decision and a developer's approval of an application architecture plan.

## Scope

Engineering Guard is a local package of agent skills usable from Codex, Kilo and Claude Code, with repository-local skills, policies, hooks, scripts, and demos. Its only dependencies are the optional factory diagram validator described above; it adds no MCP integration. Registering the marketplace with `codex plugin marketplace add .` stores a user-level Codex source that points to this checkout; installing and trusting the plugin remain explicit desktop actions. The verification runner and demos remain repository-local.

## License and community

Engineering Guard is released under the [MIT License](LICENSE).

- [Contributing](CONTRIBUTING.md): setup, tests and how to open a pull request. Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).
- [Security policy](SECURITY.md): how to raise a security concern and what is in scope.

Acknowledgement: the security skill's AI/LLM, client-side and supply-chain companions adapt ideas, in our own words, from [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) (MIT, Copyright (c) 2025-2026 Cloudflare, Inc.).
