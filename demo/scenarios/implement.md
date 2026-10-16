# Implement mode demo

Use a disposable copy of `demo/implement/` outside the repository. In that copy,
replace `src/discount.cjs` with `before/discount.cjs` and run the shared
`test/behavior.test.cjs` with `node --test`. Confirm the invalid-input assertion
fails because the baseline returns zero. The repository's `src/` remains the
corrected reference; do not overwrite it to set up the exercise.

From the disposable copy, invoke `$engineering-guard-implement` with:

> Improve only `src/discount.cjs` and its behavior test in this disposable copy. Preserve the percentage-discount result, use names that explain the calculation, and let invalid input errors remain visible instead of returning a fabricated total. Avoid extra wrappers. Run `node --test test/behavior.test.cjs` and report the result.

The copied baseline is intentionally terse and swallows errors. The shared test checks both the discounted total and visible invalid-input failure. From the Engineering Guard root, `npm run demo:implement` or `python3 scripts/verification_runner.py --run demo:implement` checks the corrected reference, not the exercise starting state.
