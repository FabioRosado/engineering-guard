# Verify mode demo

From the Engineering Guard repository root, invoke `$engineering-guard-verify` with:

> Independently review the current demo implementation and tests. Run `npm run demo:shallow` and `npm run demo:behavior`. Report concrete findings with file references, including any implementation defect and any test-quality problem, and distinguish executed behavior from conclusions based only on inspection. Do not modify files.

The target is the existing seeded demo: the shallow test passes while the real checkout behavior test exposes the incorrect charge. Verification should derive both findings from the code and test behavior, not from a required phrase.
