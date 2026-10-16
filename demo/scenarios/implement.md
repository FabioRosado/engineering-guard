# Implement mode demo

From the Engineering Guard repository root, invoke `$engineering-guard-implement` with:

> Improve only `demo/implement/src/discount.cjs` and its behavior test. Preserve the percentage-discount result, use names that explain the calculation, and let invalid input errors remain visible instead of returning a fabricated total. Avoid extra wrappers. Run `npm run demo:implement` and report the result.

The starting implementation is intentionally terse and swallows errors. `demo/implement/before/discount.cjs` preserves that baseline; the executable test checks both the real discounted total and visible invalid-input failure. The command is also discoverable as an explicit check with `python3 scripts/verification_runner.py --run demo:implement`.
