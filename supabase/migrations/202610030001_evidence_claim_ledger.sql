-- Evidence claim identity and SME verification without overwriting sources.

alter table public.evidence_items
    add column if not exists claim_nature text not null default 'unspecified',
    add column if not exists entity_name text,
    add column if not exists facility_or_site text,
    add column if not exists project_name text,
    add column if not exists sme_verification_json text;

alter table public.evidence_items
    drop constraint if exists evidence_items_claim_nature_check;

alter table public.evidence_items
    add constraint evidence_items_claim_nature_check
    check (claim_nature in (
        'actual',
        'estimate',
        'target',
        'projected',
        'unspecified'
    ));

create index if not exists ix_evidence_items_claim_nature
on public.evidence_items (claim_nature);
