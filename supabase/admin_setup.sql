-- Admin area: who may administer, and an audit trail of every sensitive action.
-- Run once in the Supabase SQL editor (idempotent). The first owner is NOT stored here:
-- set ADMIN_EMAILS=you@example.org on the server (owners listed there can never be locked out).
create table if not exists public.table_admins (
  email      text primary key check (email = lower(email)),
  role       text not null default 'admin' check (role in ('owner', 'admin')),
  added_by   text,
  created_at timestamptz not null default now()
);

create table if not exists public.table_admin_audit (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  admin_email text not null,
  action      text not null,
  target      text,
  detail      jsonb not null default '{}'::jsonb
);
create index if not exists table_admin_audit_created_idx on public.table_admin_audit (created_at desc);

-- Server-side only (service-role key); no browser access.
alter table public.table_admins enable row level security;
alter table public.table_admin_audit enable row level security;
