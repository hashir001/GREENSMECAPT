# GREENSMECAPT

GREENSMECAPT is an evidence-first decision-support platform for assessing green SMEs and funding applications. It extracts structured evidence from submitted documents, routes it through human review, assesses environmental and financial performance, and supports investor comparison with TOPSIS, Fuzzy TOPSIS, ELECTRE III and robustness analysis.

## Decision boundaries

The platform keeps three concepts separate:

- **Readiness drivers and subdrivers:** four official drivers and seven operational subdrivers analysed through expert Fuzzy DEMATEL judgments.
- **Assessment criteria:** the SME's environmental performance, financial health and transaction characteristics. These feed performance assessment and MCDM comparison.
- **Measures and evidence:** electricity, water, waste, emissions, financial values and source documents. Measures support criteria only when their scope and comparison context are established.

DEMATEL is a causal readiness-intelligence layer. It does not automatically generate Green Score weights. Development runs use the explicitly labelled, replaceable scenario in `config/dematel_scenario.development.json`; production remains without causal results until an approved expert-calibrated result is configured.

## DEMATEL structure

The official drivers are Internal Factors, Government & Institutional Support, Market Conditions and Access to Finance. Seven condensed subdrivers retain the survey concepts in an operational matrix.

- Driver-level DEMATEL: 4 factors and 12 directional judgments per expert.
- Subdriver-level DEMATEL: 7 factors and 42 directional judgments per expert.
- Maximum when both are collected: 54 judgments per expert.

The same Fuzzy DEMATEL mathematics is used at both levels. Results remain separate and are not multiplied into performance weights. The current application interprets applicant evidence at the seven-subdriver level; the four domains remain the official grouping and reporting layer.

## Current workflow

1. Documents are ingested and processed through native extraction, OCR and configured analysis.
2. Extracted evidence is reviewed and validated by a human.
3. Applicability, environmental, financial and readiness observations are established.
4. Environmental performance observations are normalized under the versioned development policy.
5. TOPSIS, Fuzzy TOPSIS and ELECTRE III generate comparison views.
6. Robustness analysis tests ranking sensitivity.

Applicant readiness records enabling, constraining, mixed, unknown, not-applicable and review-needed states. It can be joined to calibrated DEMATEL influence results without becoming an environmental performance score.

## Configuration status

Files under `config/` are versioned development contracts. Provisional weights, benchmarks and outranking thresholds are not presented as research findings. The deprecated DEMATEL-to-criterion mapping remains only for historical reproducibility and cannot be executed.

See `docs/architecture.md` and `docs/readiness_and_performance.md` for system boundaries and unresolved calibration inputs.

