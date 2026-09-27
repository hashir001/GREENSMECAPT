# GREENSMECAPT

GREENSMECAPT is an evidence-first decision-support platform for assessing green SMEs and funding applications. It extracts structured evidence from submitted documents, routes it through human review, assesses environmental and financial performance, and supports investor comparison with TOPSIS, Fuzzy TOPSIS, ELECTRE III and robustness analysis.

## Decision boundaries

The platform keeps three concepts separate:

- **Readiness drivers and subdrivers:** external and internal conditions such as finance access, regulation, organisational capability and market pressure. Expert directional judgments are analysed with Fuzzy DEMATEL.
- **Assessment criteria:** the SME's environmental performance, financial health and transaction characteristics. These feed performance assessment and MCDM comparison.
- **Measures and evidence:** electricity, water, waste, emissions, financial values and source documents. Measures support criteria only when their scope and comparison context are established.

DEMATEL is a causal readiness-intelligence layer. It does not automatically generate Green Score weights. The research-grounded taxonomy is present, while pairwise relationships and the linguistic scale remain explicitly marked for expert calibration.

## Current workflow

1. Documents are ingested and processed through native extraction, OCR and configured analysis.
2. Extracted evidence is reviewed and validated by a human.
3. Applicability and assessment observations are established.
4. Environmental performance observations are normalized under the versioned development policy.
5. TOPSIS, Fuzzy TOPSIS and ELECTRE III generate comparison views.
6. Robustness analysis tests ranking sensitivity.

Applicant readiness now has a separate evidence model that records enabling, constraining, mixed, unknown, not-applicable and review-needed states. It can be joined to DEMATEL influence results after expert calibration without turning readiness into an environmental performance score.

## Configuration status

Files under `config/` are versioned development contracts. Provisional weights, benchmarks and outranking thresholds are not presented as research findings. The deprecated DEMATEL-to-criterion mapping remains in the repository only for historical reproducibility and cannot be executed.

See `docs/architecture.md` and `docs/readiness_and_performance.md` for the system boundaries and unresolved calibration inputs.
