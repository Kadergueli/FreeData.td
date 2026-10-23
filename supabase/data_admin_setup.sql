-- Patch D: archive of observations an administrator deleted from the public data, so a
-- mistaken deletion can be undone. Run once in the Supabase SQL editor (idempotent, additive).
create table if not exists public.table_deleted_observations (
  id          bigint generated always as identity primary key,
  deleted_at  timestamptz not null default now(),
  deleted_by  text not null,
  reason      text not null,
  row         jsonb not null,
  restored_at timestamptz,
  restored_by text
);
create index if not exists table_deleted_observations_idx on public.table_deleted_observations (deleted_at desc);

-- Server-side only (service-role key); no browser access.
alter table public.table_deleted_observations enable row level security;
