# Readiness, performance and measures

## 1. Readiness structure

The official top-level drivers are Internal Factors, Government & Institutional Support, Market Conditions and Access to Finance.

The operational subdrivers are:

1. Leadership & organizational commitment
2. Workforce / technical capability & training
3. Digital, data & AI readiness
4. Regulation, compliance & standards/certifications
5. Institutional support & implementation guidance
6. Customer/buyer demand, competitiveness & reputation
7. Green finance availability, grants & incentives

The four-driver DEMATEL needs 12 directional judgments. The seven-subdriver DEMATEL needs 42. If both are elicited, the total is 54 judgments per expert. The core Fuzzy DEMATEL mathematics is unchanged.

## 2. SME readiness observations

For a real applicant, the readiness model records one state per operational subdriver:

- `enabling_evidence`
- `constraining_evidence`
- `mixed_evidence`
- `unknown`
- `not_applicable`
- `needs_review`

Evidence-based states require source identifiers. Missing evidence remains `unknown`; it is not converted to zero. The profile has no scalar readiness score. After expert calibration, DEMATEL influence results can explain why an observed constraint matters.

## 3. Environmental comparison context

A raw total describes quantity, not performance. Before comparing electricity, water, emissions or waste, the system needs a reporting period, operational boundary, suitable denominator, and a baseline, trend, target or sector benchmark.

The metric catalogue enforces these comparison-context requirements. Even direct ratios still require a period and operational scope.

The assessment workflow now reports each accepted metric as `ready`,
`incomplete`, `needs_review` or `no_measurement`. When a supported denominator
is supplied, it calculates an intensity while retaining the original total and
its sources. It does not infer a missing denominator, baseline or benchmark.

## 4. Financial separation

Green-finance availability, grants and incentives belong to readiness/context. ROA, revenue growth, liquidity, cash flow, leverage, project cost, requested amount and expected savings describe the SME and transaction. They must not be collapsed.

The financial layer reports core-data coverage and retains supporting
transaction values. It may calculate requested-project-cost coverage and a
simple undiscounted payback period when compatible source values exist. It has
no aggregate financial score or pass/fail decision until an approved financial
calibration is supplied.

## 5. Roles and publication

- SME users maintain their own company and source documents.
- Reviewers validate evidence and supply governed assessment observations.
- Experts provide DEMATEL influence judgments; they do not assess applicants.
- Investors read frozen published profiles and cannot change assessment inputs.
- Administrators may access all workspaces and govern users/configuration.

Activity yes/no/unclear inputs are reviewer-side applicability routing, not an
expert survey and not a readiness score. Readiness uses the six evidence states
listed above.

## 6. Calibration still required

The following remain unresolved until supplied and approved:

- expert directional pairwise judgments at either selected level;
- the final fuzzy linguistic scale;
- performance criterion weights;
- sector benchmarks and target/reference profiles;
- ELECTRE indifference, preference and veto thresholds;
- evidence-strength thresholds; and
- any decision thresholds applied to readiness observations.
