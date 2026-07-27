# GREENSMECAPT Data Boundaries

The project separates data by processing stage.

## `raw`

Original source data. Raw files must remain unchanged after ingestion.

## `interim`

Validated, cleaned, or partially transformed data that is not yet ready for assessment.

## `processed`

Final analysis-ready data consumed by ranking and decision-support workflows.

## `samples`

Small synthetic datasets used for demonstrations, tests, and development.

Real SME, expert, financial, or personally identifiable data must not be committed
to the Git repository. Only safe synthetic examples belong in `samples`.