# ADR 0002: Governed assessment foundation

- Status: accepted for development
- Metric catalogue: `config/metric_catalog.development.json` version `2.0.0`
- Financial policy: `config/financial_assessment.development.json` version `2.0.0`
- Evidence policy: `config/evidence_strength.development.json` version `1.0.0`

## Decision

GREENSMECAPT separates five outputs that answer different questions:

1. **environmental performance** — what the SME has actually achieved;
2. **financial health** — the SME's historical financial condition;
3. **investment case** — the proposed transaction, forecasts and assumptions;
4. **readiness context** — organizational and external conditions that may
   enable or block transition; and
5. **evidence strength** — how well each conclusion is supported.

Environmental performance is the only layer eligible for environmental MCDM
normalization. Financial health remains a separate assessment. Investment and
readiness information provide decision context. Evidence strength qualifies
all four layers but is never added to or substituted for performance.

## Metric contract

Every governed metric declares its assessment dimension, value nature,
direction, units and comparison requirements. The value nature distinguishes:

- actual flows measured over a reporting period;
- point-in-time balances;
- ratios;
- values that may be reported or transparently derived;
- forecasts; and
- activity denominators.

Forecast environmental benefits remain evidence-only and cannot be presented
as achieved results. Activity values such as production, floor area and FTE
provide comparison context and have no performance direction. Absolute energy,
water, waste and emissions totals require period, scope and a denominator,
trend, baseline or benchmark before cross-SME performance interpretation.

## Financial contract

The financial policy distinguishes raw statement inputs, derived indicators
and investment inputs. Each derived indicator names both its calculation method
and its source metrics. This preserves the difference between reported facts
and calculations such as ROA, revenue growth, current ratio, debt-to-assets,
requested financing share and simple payback.

The calculation engine retains the formula, input metric identifiers, input
values and source identifiers for every derived result. If a directly reported
indicator disagrees with the value calculated from its supplied inputs, the
indicator becomes `needs_review`; the system does not silently choose one.

Final weights, decision thresholds and benchmark interpretations remain
unresolved until approved calibration is supplied. The system must not convert
an uncalibrated financial ratio into a fabricated aggregate score.

## Missing and conflicting evidence

Missing information is **unknown, not zero**. Evidence is classified by source
type and must retain its locator, validation state, unit or currency, period,
scope and actual-versus-forecast status where applicable. Conflicting evidence
is an explicit outcome, not an average. Model-inferred evidence requires human
acceptance before it can support a governed assessment.

Development evidence-strength bands use qualitative, versioned rules rather
than a numeric score: unresolved conflicts are `conflicting`; no confirmed
support is `insufficient`; missing context or weak-only support is `limited`;
complete internal support is `adequate`; and complete audited, regulatory or
third-party support is `strong`. Each output retains its source classification,
classification basis, missing attributes, issues and rule rationale. These
bands remain an evidence overlay and never modify environmental performance.

## Configuration integrity

Application startup rejects incompatible policy sets. In particular:

- every criterion indicator must exist in the metric catalogue;
- every financial-policy metric must exist in a financial or investment
  catalogue dimension;
- normalization may reference only known environmental performance criteria;
  and
- evidence policy must cover environmental performance, financial health,
  investment case and readiness context.

Approved assessment revisions persist the exact evidence policy with the other
policy snapshots. This makes a historical result reproducible when later
catalogue or policy versions change.

Automated contract tests enforce these separation and cross-policy rules on
every repository build.

## Implementation-paper traceability

The implementation study can report coverage and accuracy separately for each
dimension, actual-versus-forecast classification, extraction versus derived
values, evidence-source class, missing-context rate, conflict rate and reviewer
acceptance. It can also reproduce comparisons from the persisted policy
versions without claiming that development weights, thresholds or benchmarks
were empirically calibrated.
