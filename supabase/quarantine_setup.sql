-- Patch C: quarantine. Rows the pipeline flags SUPERVISOR_REVIEW (impossible / out-of-domain
-- values) are held here instead of being published; an administrator approves, corrects or
-- rejects each one. Run once in the Supabase SQL editor (idempotent, additive).
create table if not exists public.table_quarantine (
  id              bigint generated always as identity primary key,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  secteur         text not null,
  source_api      text not null,
  date_reference  date not null,
  indicateur      text not null,
  valeur          double precision not null,
  unite           text,
  region          text not null,
  pays            text not null default 'TCD',
  licence         text,
  source_url      text,
  notes           text,
  flags           jsonb not null default '[]'::jsonb,
  id_raw          integer,
  status          text not null default 'pending'
                  check (status in ('pending', 'approved', 'corrected', 'rejected')),
  corrected_value double precision,
  reviewed_by     text,
  reviewed_at     timestamptz,
  review_note     text
);
-- one waiting row per observation: a new harvest updates it instead of piling up copies
create unique index if not exists table_quarantine_pending_key
  on public.table_quarantine (secteur, source_api, date_reference, indicateur, region)
  where status = 'pending';
create index if not exists table_quarantine_status_idx on public.table_quarantine (status, created_at desc);

-- Server-side only (service-role key); no browser access.
alter table public.table_quarantine enable row level security;
