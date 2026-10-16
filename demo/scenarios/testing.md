# Testing quality demo

From the repository root, run:

```sh
python3 scripts/verification_runner.py --run demo:shallow --run demo:behavior
```

Then invoke `$engineering-guard-testing` with:

> Audit `demo/test/shallow.test.cjs` against `demo/src/pricing.cjs` and `demo/src/checkout.cjs`, using the runner output as execution evidence. Explain whether the passing test would detect the incorrect percentage calculation, whether the behavior test reaches the real pricing function, and what each result establishes. Do not modify files.

Expected result: identify that the shallow test replaces `calculateTotal`, so it only proves the checkout passes a returned value to the gateway. The behavior test uses real pricing and fails because the code subtracts 10 cents rather than applying 10 percent. Recommend focused behavior coverage at the real pricing/checkout boundary.

Avoid claiming the shallow test is useless for every purpose, inferring coverage from a passing status, or treating the expected behavior failure as a test-runner defect.
