# Contributing

Thanks for taking an interest in Engineering Guard. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first. To report a security concern, follow [SECURITY.md](SECURITY.md) rather than the steps below.

## License

Contributions are accepted under the repository's [MIT license](LICENSE). By opening a pull request you agree that your contribution is licensed the same way.

## Setup

- Python 3.9 or newer runs the hook, the factory scripts and the test suite. No third-party Python packages are required.
- Node.js 18 or newer and npm run the JavaScript demonstrations.
- The factory dashboard in `ui/` (Svelte and Vite) needs Node.js 20.19+ or 22.12+. Install its packages with `npm install --prefix ui`; they stay out of Git.
- The factory's optional mermaid diagram validator needs Node.js 20.19+, 22.13+ or 24+. Install it with `npm install --prefix .agents/skills/factory/validator`. Without it the factory still works and only warns that diagrams were not syntax-checked.

## Tests and checks

Run these from the repository root:

```sh
npm test            # Python suite: python3 -m unittest discover -s test -p 'test_*.py'
npm run ui:test     # dashboard tests (vitest); needs Node.js 20.19+ or 22.12+ and the ui/ packages
npm run test:all    # npm test and npm run ui:test
npm run quality     # deterministic quality gate over your uncommitted change (see below if you have committed)
```

`npm test` takes a few minutes. `npm run quality` reads `.quality-gate.json`; optional scanners that are not installed are skipped with a warning rather than failing the gate. The gate measures changes against `HEAD`, so once you have committed, run `npm run quality -- --base main` to measure your branch against `main`. See the README for the demonstration scripts (`npm run demo:*`).

## Repository conventions

- **Skills, policies and the hook** live in `.agents/skills/`, `policies/`, `.codex/` and `hooks/`. They are advisory guidance, so keep wording precise and do not claim they enforce more than they do.
- **Architecture decisions** are recorded in `decisions/`. A change that alters the architecture of a component, such as the factory or the dashboard, should add or update a record there.
- **`.factory/` is local.** The factory keeps its jobs, specs and reviews in `.factory/`, which is excluded through `.git/info/exclude`. Never commit it, and never force-add it. The factory itself never commits, pushes or merges; a human does.
- **`demo/` fixtures are intentionally defective** (for example `demo/security/vulnerable` and `demo/src`). Do not fix them: the demonstrations depend on them being defective. See [demo/README.md](demo/README.md).
- Keep changes focused. Do not mix unrelated refactoring into a feature or fix.

## Submitting a pull request

1. Fork the repository and create a branch for one change.
2. Make the change and add or update tests that check the behaviour, not just the implementation.
3. Run `npm test`, plus `npm run ui:test` if you touched `ui/`, and `npm run quality`.
4. Open a pull request and fill in the template. Include the commands you ran and their results. If a check could not run, say so.
