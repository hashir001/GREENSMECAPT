# GREENSMECAPT: configurable profiles and follow-up planning

This batch adds a running company-context -> applicability -> follow-up workflow.
It adds files only. It does not require the discarded seven-metric catalogue,
change EvidenceItem, replace the existing input builder, or alter TOPSIS/OCR.
No new dependencies are required beyond the existing Pydantic 2 installation.

## Apply

Save `greensmecapt_profiles_batch.patch` in the project root. From that directory:

```bash
source .venv/bin/activate
git apply --stat greensmecapt_profiles_batch.patch
git apply --check greensmecapt_profiles_batch.patch
git apply greensmecapt_profiles_batch.patch
```

Git creates the directories and files. If the check reports a collision, stop:
do not force application or overwrite existing files. The patch is atomic by
default and intentionally contains only new file paths.

## Run

```bash
python -m greensmecapt.assessment.profiles config/assessment_profiles.development.json examples/assessment_profiles/green_software.json
python -m greensmecapt.assessment.profiles config/assessment_profiles.development.json examples/assessment_profiles/small_manufacturer.json
python -m greensmecapt.assessment.profiles config/assessment_profiles.development.json examples/assessment_profiles/activity_incomplete.json
```

Add `--json` to print a complete serializable profile, including snapshots and
fingerprints. These commands print results; they send no notifications and do
not save assessments to a database.

Expected examples:

| Example | Behaviour |
| --- | --- |
| Green software | Energy/cloud and customer-impact routes apply; direct factory/fuel emissions route does not. |
| Small manufacturer | Direct-emissions route applies; fuel records, approximate activity data and not-measured responses are offered. No carbon inventory is required to create the profile. |
| Incomplete activity description | Fuel/fleet applicability remains uncertain; two targeted activity questions are generated. The company still receives a profile. |

## Verify and commit

```bash
ruff check src/greensmecapt/assessment/profiles tests/unit/test_activity_profiles.py --select I --fix
ruff check .
python -m pytest
git add src/greensmecapt/assessment/profiles
git add config/assessment_profiles.development.json examples/assessment_profiles
git add tests/unit/test_activity_profiles.py docs/assessment_profiles_batch.md
git diff --cached --check
git diff --cached --stat
git commit -m "feat: add configurable activity profiles and follow-up planning"
git push
```

There are 18 new unittest cases, also discoverable by pytest. If the existing
OCR checkpoint is 70 passing tests, the expected total is 88. Local verification
of this batch used Python 3.12 and Pydantic 2.13.5; the user's full repository
and Ruff installation were not available in the verification environment.

The downloaded patch itself remains untracked; keep it outside the repository
after application, or leave it untracked. Commit the actual source/config files.

## What is configurable

The policy is JSON, using Python's standard JSON loader. This avoids adding a
YAML dependency; format does not affect the versioning or policy architecture.
Edit the version, modules, activity rules, questions, response routes and
assessment notes without changing the evaluator. Run the tests after edits.

`when` rules support `all_true`, `any_true` and `all_false`; all configured groups
must be satisfied. An empty rule is always applicable. Explicit false differs
from null or an omitted answer. Unknown answers stay uncertain until enough
facts resolve the rule. A satisfied `any_true` group does not require every
remaining alternative to be answered. Repeated requests for the same fact are
deduplicated.

Boolean context facts must be actual JSON true/false/null. Unknown keys are
rejected to catch misspellings. Sector and stage descriptions are retained;
they do not automatically determine applicability. Future NLP may propose
facts, but confirming them and recording their basis is still necessary.

Modules describe business activities, not the paper's policy/social/technology/
internal driver dimensions. Module tags can overlap. Each assessment topic has
an explicit rule, so module membership does not silently create duplicate scores.
The included policy is a development routing demonstration, not an approved
research catalogue or a complete map of all sectors.

CORE/CONDITIONAL/OPTIONAL/INFORMATIONAL set question priority; they do not
automatically reject a company or grant permission to rank it. Informational
topics are retained without evidence requests. All responses still need future
validation and scoring adapters appropriate to their meaning.

## Evidence, applicability and scoring are distinct

This batch creates candidate questions for applicable topics. It does not yet
inspect uploaded evidence to suppress questions already answered by documents.
That is the next response/evidence integration step. It does not classify absence
as not-measured or not-provided unless an appropriate later response establishes
that fact.

Alternative response routes are invitations to provide evidence. They are not
interchangeable measurements. A management description cannot become tonnes of
emissions. An unknown answer is not a neutral fuzzy number. Unknown material
data does not justify a definitive scalar rank merely because a profile exists.

This module does not compute performance, Evidence Strength, fuzzy scores,
readiness, or ranks. Existing TOPSIS still needs complete comparable inputs.
Next, criterion responses and accepted evidence will be mapped into criterion
scores, with explicit handling of ranges, qualitative rubrics and missing data.
Benchmark scoring and provisional uncertainty analysis require their own
defined reference profiles and tested algorithms; they are not activated here.

## Review and future access control

An ApplicabilityOverride records the original rule result, the effective
decision, reviewer identity, reason and supporting record references. This is
an internal function parameter. No applicant endpoint exists and this batch
does not authenticate reviewers. A future API must check authorization before
accepting an override; a supplied reviewer string alone is not permission.
Historical reviewer decisions will be stored as events when persistence lands.

Profiles contain policy/context snapshots plus canonical-content hashes. This
supports reconstruction even if a policy version label is accidentally reused.
Hashes are not signatures or proof that an applicant statement is true.

Before database/API implementation, define organisation membership, SME
ownership, reviewer assignment and investor visibility. Supabase/Postgres can
implement that model with authentication and database access policies. Docker
can then package the application and OCR dependencies for reproducible deployment.
