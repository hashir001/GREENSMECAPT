# ADR 0003: Keep the Green Score distinct from ranking and context

## Status

Accepted for the development implementation. Criterion definitions, benchmark
ranges and weights remain replaceable calibration artifacts.

## Decision

For SME `i`, the platform calculates a distinct environmental result:

`GS_i = sum(w_j * s_ij)`

where every `s_ij` is a normalized 0-100 score for an applicable environmental
performance criterion and the effective `w_j` values sum to one. Development
linguistic inputs are converted from triangular fuzzy numbers by centroid
defuzzification: `(lower + modal + upper) / 3 * 100`.

Base weights are relative calibration values. They are renormalized across the
criteria that are genuinely applicable to the SME. A non-applicable criterion
therefore does not penalize the company.

Missing applicable performance is never converted to zero:

- full applicable coverage produces a final Green Score;
- coverage at or above the governed minimum may produce an explicitly
  provisional score over resolved criteria, with coverage shown separately;
- unresolved applicability or coverage below the minimum withholds the score.

Only a numeric indicator and unit explicitly authorized by a criterion's
normalization rule can directly determine that criterion score. Absolute
electricity, water, waste, fuel and emissions totals otherwise remain in the
performance-context layer until a denominator, baseline, trend or benchmark
makes them comparable. Context measurements must not suppress an admissible
evidence-informed criterion rating.

Every criterion result retains its normalized score, base weight, applicable
weight, scoring weight, contribution, responses, evidence and indicator IDs.

## Separation from other outputs

- Green Score summarizes environmental performance.
- Financial and Investment Assessment remains separate and uncompressed.
- Readiness evidence receives contextual DEMATEL interpretation, not Green
  Score weight.
- Evidence Strength reports documentary support and never changes performance.
- TOPSIS and fuzzy TOPSIS compare applicant profiles; their closeness values are
  not the Green Score.
- ELECTRE III exposes outranking, veto and incomparability relationships.

## Calibration boundary

The calculation contract is implemented now. Final weights, sector benchmark
ranges, target profiles and thresholds require the approved empirical and
expert-calibration process. Development outputs must retain their policy version
and calibration label.
