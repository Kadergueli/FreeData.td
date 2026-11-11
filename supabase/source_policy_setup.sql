-- Admin decisions per data source: status, layer (open / both), call limits, notes.
-- Server-only (service role). Idempotent: safe to run again.
create table if not exists public.table_source_policy (
  source_id    text primary key,
  status       text not null default 'active' check (status in ('active','paused','planned','retired')),
  layer        text not null default 'open'   check (layer in ('open','both')),
  limit_minute integer check (limit_minute >= 0),
  limit_hour   integer check (limit_hour >= 0),
  limit_day    integer check (limit_day >= 0),
  limit_month  integer check (limit_month >= 0),
  notes        text,
  updated_by   text,
  updated_at   timestamptz not null default now()
);

alter table public.table_source_policy enable row level security;
revoke all on public.table_source_policy from anon, authenticated;
grant all on public.table_source_policy to service_role;
