-- Batch 1: explicit roles, SME lifecycle, immutable approvals and publications.

create or replace function public.set_greensmecapt_access(
    target_user_id uuid,
    application_role text,
    assigned_sme_ids text[] default array[]::text[]
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if application_role not in (
        'admin',
        'reviewer',
        'expert',
        'investor',
        'sme_user'
    ) then
        raise exception 'Unsupported GREENSMECAPT role: %', application_role;
    end if;

    if application_role = 'sme_user'
       and cardinality(assigned_sme_ids) = 0 then
        raise exception 'SME users require at least one SME assignment';
    end if;

    if application_role <> 'sme_user'
       and cardinality(assigned_sme_ids) > 0 then
        raise exception 'Only SME users may receive SME assignments';
    end if;

    update auth.users
    set raw_app_meta_data =
        coalesce(raw_app_meta_data, '{}'::jsonb)
        || jsonb_build_object(
            'greensmecapt_role', application_role,
            'sme_ids', to_jsonb(coalesce(assigned_sme_ids, array[]::text[]))
        )
    where id = target_user_id;

    if not found then
        raise exception 'Supabase user % was not found', target_user_id;
    end if;
end;
$$;

revoke all on function public.set_greensmecapt_access(
    uuid,
    text,
    text[]
) from public, anon, authenticated;

grant execute on function public.set_greensmecapt_access(
    uuid,
    text,
    text[]
) to service_role;

create table if not exists public.sme_applications (
    application_id text primary key,
    sme_id text not null unique references public.smes (sme_id),
    status text not null,
    revision integer not null check (revision >= 1),
    created_by text not null,
    updated_by text not null,
    created_at timestamp with time zone not null default now(),
    updated_at timestamp with time zone not null default now(),
    check (status in (
        'draft',
        'submitted',
        'under_review',
        'changes_requested',
        'approved',
        'published',
        'withdrawn',
        'archived'
    ))
);

-- Existing SMEs predate the lifecycle table. Preserve them and require an
-- explicit submit/review cycle instead of silently treating them as approved.
insert into public.sme_applications (
    application_id,
    sme_id,
    status,
    revision,
    created_by,
    updated_by
)
select
    'application_migrated_' || md5(sme_id),
    sme_id,
    'draft',
    1,
    'system:migration',
    'system:migration'
from public.smes
on conflict (sme_id) do nothing;

create table if not exists public.sme_assessment_profile_revisions (
    revision_id text primary key,
    sme_id text not null references public.smes (sme_id),
    profile_version integer not null check (profile_version >= 1),
    context_json text not null,
    responses_json text not null,
    record_snapshot_json text not null,
    approval_fingerprint text not null,
    assessment_policy_json text not null,
    normalization_policy_json text not null,
    approved_by text not null,
    approved_at timestamp with time zone not null default now(),
    unique (sme_id, profile_version)
);

create index if not exists ix_profile_revisions_sme
on public.sme_assessment_profile_revisions (sme_id);

create table if not exists public.sme_assessment_profile_publications (
    publication_id text primary key,
    sme_id text not null references public.smes (sme_id),
    revision_id text not null
        references public.sme_assessment_profile_revisions (revision_id),
    active boolean not null default true,
    published_by text not null,
    published_at timestamp with time zone not null default now(),
    withdrawn_by text,
    withdrawn_at timestamp with time zone
);

create index if not exists ix_profile_publications_active
on public.sme_assessment_profile_publications (sme_id, active);

create unique index if not exists uq_active_profile_publication
on public.sme_assessment_profile_publications (sme_id)
where active = true;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'sme_applications',
        'sme_assessment_profile_revisions',
        'sme_assessment_profile_publications'
    ]
    loop
        execute format(
            'alter table public.%I enable row level security',
            table_name
        );
        execute format(
            'revoke all on table public.%I from anon, authenticated',
            table_name
        );
    end loop;
end
$$;
