-- Persist one centrally approved assessment profile per SME.
-- Investors compare these governed profiles and cannot supply scoring inputs.

create table if not exists public.sme_assessment_profiles (
    sme_id text primary key
        references public.smes (sme_id)
        on delete cascade,
    profile_version integer not null default 1
        check (profile_version >= 1),
    context_json text not null,
    responses_json text not null,
    approved_by text not null,
    created_at timestamp with time zone not null default now(),
    updated_at timestamp with time zone not null default now()
);

create index if not exists
    ix_sme_assessment_profiles_approved_by
on public.sme_assessment_profiles (approved_by);

alter table public.sme_assessment_profiles
enable row level security;

revoke all on table public.sme_assessment_profiles
from anon, authenticated;
