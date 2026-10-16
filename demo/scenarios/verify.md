# Verify mode demo

From the repository root, first collect evidence:

```sh
python3 scripts/verification_runner.py --run demo:shallow --run demo:behavior
python3 -m unittest discover -s test -p 'test_verification_runner.py'
```

The first command exits nonzero because the behavior regression is intentionally failing. Its structured report should show the shallow mock-based check passing, the real checkout behavior check failing with 9,990 instead of 9,000, the unchanged snapshot, and `assessment: execution_evidence_only`. The second command demonstrates in a disposable Git repo that a passing check which changes tracked source produces `snapshot_changed`.

Then invoke `$engineering-guard-verify`:

> Independently review the checkout implementation, both tests, and the verification-runner report. Inspect actual source and test paths; explain why the shallow test passes despite the incorrect charge. State the readiness conclusion, distinguish the runner's execution evidence from your code review, and identify the payment gateway boundary as unverified by these fixtures. Do not modify files.

Expected result: report the pricing defect and ineffective test as separate evidence-backed concerns, and do not conclude Verified while the real behavior check fails. Do not call the payment integration verified; the fixture's gateway is a test double.
