-- Run once in Supabase SQL Editor to store LLM-generated studies separately
-- from raw, validated and published observations.
create table if not exists public.table_etudes (
  id bigint generated always as identity primary key,
  date_creation timestamptz not null default now(),
  secteur varchar(50),
  modele varchar(100) not null,
  nb_observations integer not null,
  rapport text not null,
  statut varchar(20) not null default 'generated'
);

create index if not exists table_etudes_sector_date_idx
  on public.table_etudes (secteur, date_creation desc);
alter table public.table_etudes enable row level security;
