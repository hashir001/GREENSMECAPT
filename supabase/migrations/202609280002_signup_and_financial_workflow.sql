-- Public SME/investor onboarding and governed financial submissions.

create table if not exists public.financial_submissions (
    submission_id text primary key,
    sme_id text not null unique references public.smes (sme_id),
    status text not null default 'draft',
    revision integer not null default 1 check (revision >= 1),
    observations_json text not null default '[]',
    submitted_by text,
    reviewed_by text,
    review_note text,
    created_at timestamp with time zone not null default now(),
    updated_at timestamp with time zone not null default now(),
    submitted_at timestamp with time zone,
    reviewed_at timestamp with time zone,
    check (status in ('draft', 'submitted', 'under_review', 'changes_requested', 'approved'))
);

create index if not exists ix_financial_submissions_status
on public.financial_submissions (status);

alter table public.financial_submissions enable row level security;
revoke all on table public.financial_submissions from anon, authenticated;

create or replace function public.handle_greensmecapt_signup()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    requested_role text;
    assigned_sme_id text;
    company_name text;
    company_sector text;
    company_jurisdiction text;
begin
    requested_role := new.raw_user_meta_data ->> 'greensmecapt_requested_role';

    -- Controlled admin/reviewer/expert creation does not use public onboarding.
    if requested_role is null then
        return new;
    end if;

    if requested_role not in ('sme_user', 'investor') then
        raise exception 'Public signup supports only SME and investor accounts';
    end if;

    if requested_role = 'sme_user' then
        company_name := btrim(coalesce(new.raw_user_meta_data ->> 'company_name', ''));
        company_sector := btrim(coalesce(new.raw_user_meta_data ->> 'company_sector', ''));
        company_jurisdiction := btrim(coalesce(new.raw_user_meta_data ->> 'company_jurisdiction', ''));
        if company_name = '' or company_sector = '' or company_jurisdiction = '' then
            raise exception 'SME signup requires company name, sector and jurisdiction';
        end if;

        assigned_sme_id := 'sme_' || replace(new.id::text, '-', '');
        insert into public.smes (
            sme_id, legal_name, sector, jurisdiction, created_at, updated_at
        ) values (
            assigned_sme_id, left(company_name, 255), left(company_sector, 255),
            left(company_jurisdiction, 255), now(), now()
        );
        insert into public.sme_applications (
            application_id, sme_id, status, revision, created_by, updated_by
        ) values (
            'application_' || replace(gen_random_uuid()::text, '-', ''),
            assigned_sme_id, 'draft', 1, new.id::text, new.id::text
        );
        new.raw_app_meta_data := coalesce(new.raw_app_meta_data, '{}'::jsonb)
            || jsonb_build_object(
                'greensmecapt_role', 'sme_user',
                'sme_ids', jsonb_build_array(assigned_sme_id)
            );
    else
        new.raw_app_meta_data := coalesce(new.raw_app_meta_data, '{}'::jsonb)
            || jsonb_build_object(
                'greensmecapt_role', 'investor',
                'sme_ids', '[]'::jsonb
            );
    end if;

    return new;
end;
$$;

revoke all on function public.handle_greensmecapt_signup() from public;
drop trigger if exists on_greensmecapt_user_signup on auth.users;
create trigger on_greensmecapt_user_signup
before insert on auth.users
for each row execute function public.handle_greensmecapt_signup();
