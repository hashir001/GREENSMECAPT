```markdown
# GREENSMECAPT

GREENSMECAPT is an evidence-aware decision-support platform for assessing and
ranking green small and medium-sized enterprises.

The platform is intended to help investors and other authorized decision-makers
combine sustainability, operational, financial, and contextual evidence into
structured and explainable SME assessments.

## MVP scope

The initial MVP will provide:

- validated SME, criterion, evidence, and assessment models;
- fuzzy DEMATEL structures for expert-informed causal weighting;
- TOPSIS-based SME ranking;
- ELECTRE III outranking analysis;
- transparent intermediate calculations and explanations;
- synthetic demonstration data;
- tested application services;
- an API boundary for future interfaces and integrations.

## Current status

The project is in its initial architecture and development-environment stage.

## Repository structure

- `src/greensmecapt/domain`: core concepts and business rules;
- `src/greensmecapt/mcdm`: decision-support algorithms;
- `src/greensmecapt/data`: ingestion and persistence adapters;
- `src/greensmecapt/services`: application workflows;
- `src/greensmecapt/api`: future HTTP interface;
- `tests`: unit and integration tests;
- `configs`: non-secret configuration;
- `data`: separated data-processing stages;
- `docs`: architecture and design decisions.

## Development setup

```bash
cd ~/projects/GREENSMECAPT
source .venv/bin/activate
python -m pip install -e ".[dev]"