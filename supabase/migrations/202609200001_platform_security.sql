-- GREENSMECAPT Supabase bootstrap and browser-access boundary.
-- Run this after the backend has created the application tables once.

insert into storage.buckets (id, name, public)
values ('source-documents', 'source-documents', false)
on conflict (id) do update
set public = false;

-- The browser talks to FastAPI, never directly to application tables or
-- original documents. The backend performs authorization, validation,
-- evidence auditing and content-integrity checks before data is returned.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'smes',
        'documents',
        'document_processing',
        'document_processing_jobs',
        'document_batch_checkpoints',
        'evidence_items',
        'audit_events',
        'assessment_runs'
    ]
    loop
        if to_regclass('public.' || table_name) is not null then
            execute format(
                'alter table public.%I enable row level security',
                table_name
            );
            execute format(
                'revoke all on table public.%I from anon, authenticated',
                table_name
            );
        end if;
    end loop;
end
$$;

-- Assign the claims consumed by the backend JWT verifier. This function is
-- callable only with the server-side service role (or from the SQL editor).
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
        'investor',
        'sme_user'
    ) then
        raise exception 'Unsupported GREENSMECAPT role: %', application_role;
    end if;

    if application_role = 'sme_user'
       and cardinality(assigned_sme_ids) = 0 then
        raise exception 'SME users require at least one SME assignment';
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
