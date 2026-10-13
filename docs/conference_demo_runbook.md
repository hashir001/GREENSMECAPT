# GREENSMECAPT conference demonstration

## Demo assets

Use `output/pdf/greensmecapt_conference_demo_pack/`. The guide explains the
document routes; `ground_truth.json` is the private evaluator answer key and
must not be uploaded as SME evidence.

Create two SME workspaces:

| SME | Sector | Jurisdiction |
| --- | --- | --- |
| TerraPack Circular Industries LLC | Moulded recycled-fibre food packaging manufacturing | United Arab Emirates |
| BlueMesa Sustainable Packaging LLC | Moulded paper-fibre packaging manufacturing | United Arab Emirates |

## Live demonstration sequence

1. Sign in as admin and confirm **Profile and access** reports Supabase,
   Document AI and Gemini as configured.
2. Create both SMEs. For each SME, upload its `01`, `02` and `03` files as
   separate documents.
3. Process each document. Show that the `01` files use OCR while the native
   files preserve searchable text and tables.
4. Open the evidence workspace. Show evidence grouped by source document,
   source page/excerpt, normalized values, company context and the seven
   readiness factors.
5. Use **Accept all review-ready** per document. Do not bulk-accept the
   conflicting electricity claims. Resolve those deliberately and explain
   that both claims remain source-linked in the ledger.
6. Show the incomplete recycled-input claim remaining contextual and the
   additional biodiversity/employee-improvement facts retained outside the
   scored catalog.
7. Confirm or correct company context, complete any assessment criterion that
   genuinely lacks accepted evidence, and enter the financial submission.
8. Prepare each assessment profile, review Green Score, financial assessment,
   Evidence Strength and readiness interpretation, then approve and publish.
9. Open the investor workspace, filter the published opportunity set and run
   the two-SME comparison. Explain that TOPSIS is cohort-relative, ELECTRE adds
   outranking, and DEMATEL explains readiness causes without changing Green
   Score or MCDM weights.

## Pre-demo acceptance check

- Both accounts can sign in and role routing is correct.
- All six evidence PDFs upload and process.
- The scanned files yield text only after Google Document AI OCR.
- Evidence is separated by document.
- The deliberate conflicts are visible and not silently resolved.
- Both profiles can be prepared, approved, published and compared.
- Delete/reset controls use application dialogs and work only for admin.
- No browser console error and no backend 401/500 response appears.

Keep the two published comparison profiles in place after the rehearsal. Use
the admin reset only when deliberately rebuilding the full demo dataset.
