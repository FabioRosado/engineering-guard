# Engineering quality comparison

Run the shared behavioral contract against both implementations:

```sh
npm run demo:quality
```

Then invoke `$engineering-guard-verify` with:

> Compare `demo/quality/simple/discount.mjs` and `demo/quality/overengineered/discount.mjs`. Read both implementations and the shared contract tests, then explain how their responsibilities, indirection, and likely change cost differ for the current single percentage-discount requirement. State what future requirement would justify the strategy registry. Do not use line count as a quality score and do not edit files.

Expected result: confirm both variants pass the same behavior contract, then explain that the simple function expresses the current calculation directly while the registry, strategy, and calculator add indirection without current variation. Treat an additional real discount policy or independently managed rule as possible evidence that could justify the abstraction.

Avoid deciding from file length alone, claiming the variants have untested behavior equivalence, or saying abstractions are inherently bad.
