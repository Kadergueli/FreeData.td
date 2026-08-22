-- Optional but strongly recommended after creating your five FreeDatatd tables.
-- Prevents duplicate public rows and makes dashboard filters fast.
create unique index if not exists table_public_dedup_idx
  on public.table_public (secteur, source_api, date_reference, indicateur, region);

create index if not exists table_public_sector_date_idx
  on public.table_public (secteur, date_reference desc);
create index if not exists table_clean_raw_idx on public.table_clean (id_raw);
create index if not exists table_rapports_raw_idx on public.table_rapports (id_raw);

-- Keep writes server-side using SUPABASE_SERVICE_ROLE_KEY; do not expose it in the browser.
alter table public.table_raw enable row level security;
alter table public.table_clean enable row level security;
alter table public.table_public enable row level security;
alter table public.table_logs enable row level security;
alter table public.table_rapports enable row level security;
