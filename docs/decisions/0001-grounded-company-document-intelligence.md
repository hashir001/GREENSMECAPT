# ADR 0001: Grounded company and document intelligence

- Status: accepted for development
- Policy: `config/company_intelligence.development.json`
- Initial policy version: `1.0.0`

## Decision

GREENSMECAPT uses an **open-world evidence, closed-world assessment** design.
Uploaded documents may contain unanticipated information, but comparative
assessment uses only versioned indicators, criteria, units, applicability
rules and calibration parameters.

Google Document AI supplies page text, layout and table structure. Gemini maps
that source material into a strict response contract. The backend verifies
quotes, controlled identifiers, written values, units, periods and scopes
before retaining a proposal. TOPSIS and ELECTRE never consume Gemini prose or
an unmapped discovery directly.

## Governed outputs

One semantic request may produce:

1. configured numeric metric claims;
2. configured qualitative assessment/activity claims;
3. controlled document-profile claims;
4. controlled company-profile claims;
5. reviewable sector/activity proposals; and
6. capped unmapped-material discoveries.

Every retained claim includes a stable identifier, exact source quotation and
page/region locator. Unmapped discoveries are explicitly non-scoring and are
limited by policy to prevent an open-ended summary from becoming an implicit
assessment model.

## Company authority model

Company master data has three states:

- **declared**: supplied directly by the SME;
- **inferred**: proposed from source-grounded document evidence; and
- **confirmed**: accepted by an authorized SME or reviewer.

An inferred sector or activity never silently overwrites declared or confirmed
data. Disagreement creates a review task. Confirmed activities determine which
assessment modules are applicable; a single broad sector label is insufficient
for companies with facilities, fleets, cloud services or multiple business
lines.

## Unknown information

Novel information is retained only when it may materially affect environmental
performance, financial/investment interpretation, readiness, compliance or
risk. It is stored as a proposed label, controlled category, exact quote,
source locator and clearly labelled model rationale. It remains outside scoring
until governance promotes it into a later catalogue/policy version.

## Cost and reliability controls

- Company and document context share the existing Gemini extraction request.
- Requests are bounded by source-segment and character limits.
- Results are idempotent and versioned by model, catalogue and policy.
- The backend deduplicates claims across request/page batches.
- Unmapped discoveries are capped per document.
- Born-digital structure is retained while Document AI remains the primary OCR
  path for scanned content.
- Additional Document AI processors are introduced only after measured gains on
  representative documents.

## Implementation-paper traceability

The implementation study can report and evaluate the following independently:

- OCR/layout recovery;
- metric extraction precision and recall;
- provenance/grounding rejection rate;
- document-type accuracy;
- company-field extraction accuracy;
- sector/activity proposal accuracy and reviewer agreement;
- unmapped-discovery usefulness and false-positive rate;
- evidence-to-assessment coverage;
- latency and cost per page/document; and
- ranking stability under missing or corrected evidence.

The configuration version and model name are persisted with each document
report, allowing results to be reproduced without treating provisional
calibration values as research-derived findings.
