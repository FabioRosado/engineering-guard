# Architecture Alignment demo

1. Run the Research demo and ask Research to save its short report as `decisions/checkout-discount.md`, explicitly labelled `Research proposal — unapproved`. Its location does not imply approval.
2. In a later turn, invoke `$engineering-guard-align` and ask it to resume that report in the same record. Challenge the proposed pricing boundary or ask how rounding and invalid inputs should affect the design. The skill should inspect the real files, explain plan changes, re-check the revised approach against applicable project instructions and engineering policy, and save a draft with a plan revision and `Draft — awaiting explicit developer approval` status. It should report any applicable conflicts, not perform a mechanical checklist against unrelated rules.
3. Review the record and explicitly approve the complete plan. Invoke Align in a fresh session and verify it recovers the approval for that exact revision.
4. Request a material plan change, such as changing the agreed rounding behavior. Align should explain why the approved revision no longer applies, update the record as a new draft, and ask for approval of the revised plan. It must not implement either plan.

The skill may maintain the decision record, but must never edit the demo implementation or infer approval from its own recommendation.
