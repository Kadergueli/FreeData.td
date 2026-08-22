-- Run this once in the Supabase SQL editor.
create table if not exists public.observations (
  id bigint generated always as identity primary key,
  sector text not null check (sector in ('agriculture','markets','transport','education','environment','economy')),
  indicator text not null,
  value double precision not null,
  unit text not null,
  reference_date date not null,
  country_code char(3) not null default 'TCD',
  region text not null default 'national',
  source text not null,
  source_url text,
  license text not null default 'CC BY 4.0',
  notes text,
  collected_at timestamptz not null default now(),
  unique (sector, indicator, reference_date, region, source)
);

create index if not exists observations_sector_date_idx on public.observations (sector, reference_date desc);
alter table public.observations enable row level security;

-- The dashboard can read published observations. Writes remain server-side via the service-role key.
drop policy if exists "Public read access" on public.observations;
create policy "Public read access" on public.observations for select using (true);
