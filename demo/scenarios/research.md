# Research mode demo

From the Engineering Guard repository root, invoke `$engineering-guard-research` with:

> In the demo checkout flow, recommend how to implement the 10% discount correctly. Inspect the real pricing and checkout modules and both tests first. Give repository-grounded alternatives and trade-offs, recommend the smallest change, and do not edit files.

Evidence to inspect: `demo/src/pricing.cjs`, `demo/src/checkout.cjs`, `demo/test/behavior.test.cjs`, and `demo/test/shallow.test.cjs`. A useful report should distinguish the observed flat-cent subtraction defect from the shallow test that stubs the calculator, and compare fixing the existing pricing boundary with any genuinely viable alternative.
