-- Assistant question log: what people ask, what was understood, and whether the answer helped.
-- Run once in the Supabase SQL editor (idempotent, additive: touches no existing table).
create table if not exists public.table_assistant_log (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  channel    text not null default 'admin',     -- admin | whatsapp (later)
  user_ref   text,                              -- admin e-mail today; a salted hash of the number for WhatsApp
  question   text not null,
  intent     text not null,
  lens       text,
  refused    boolean not null default false,
  corrected  boolean not null default false,
  followup   boolean not null default false,
  latency_ms integer,
  feedback   smallint check (feedback in (-1, 1))
);
create index if not exists table_assistant_log_created_idx on public.table_assistant_log (created_at desc);

-- Server-side only (service-role key); no browser access.
alter table public.table_assistant_log enable row level security;
