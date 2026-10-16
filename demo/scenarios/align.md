# Architecture Alignment demo

1. Run the Research demo and ask Research to save its short report as `decisions/checkout-discount.md`. The recommendation is a proposal, not an approved decision.
2. In a later turn, invoke `$engineering-guard-align` and ask it to resume that report. Challenge the proposed pricing boundary or ask how rounding and invalid inputs should affect the design. The skill should inspect the real files, explain any plan changes, and persist a draft record without marking it approved.
3. Review the record and explicitly approve the complete plan only when ready. Invoke Align again in a later session; it should recover the record and its approval status from disk.

The skill should never edit the demo implementation or infer approval from its own recommendation.
