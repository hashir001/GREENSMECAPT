-- Batch 3: persist financial, readiness and environmental-context inputs
-- inside each immutable approved profile revision.

alter table public.sme_assessment_profile_revisions
add column if not exists supplemental_inputs_json text not null default '{}';

comment on column public.sme_assessment_profile_revisions.supplemental_inputs_json
is 'Versioned financial observations, readiness observations, metric comparison contexts and their governing policy snapshots.';
