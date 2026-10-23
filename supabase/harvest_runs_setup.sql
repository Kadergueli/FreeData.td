-- Patch B: durable history of every harvest (scheduler, GitHub workflow, admin button).
-- Run once in the Supabase SQL editor (idempotent, additive: touches no existing table).
create table if not exists public.table_harvest_runs (
  id           bigint generated always as identity primary key,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  trigger      text not null default 'scheduler' check (trigger in ('scheduler', 'api', 'admin')),
  triggered_by text,
  sectors      jsonb not null default '[]'::jsonb,
  status       text not null default 'running'
               check (status in ('running', 'completed', 'partial', 'failed', 'interrupted', 'skipped')),
  total_stored integer not null default 0,
  results      jsonb not null default '{}'::jsonb
);
create index if not exists table_harvest_runs_started_idx on public.table_harvest_runs (started_at desc);

-- Server-side only (service-role key); no browser access.
alter table public.table_harvest_runs enable row level security;
