-- FreeData.td core pipeline tables (raw -> clean -> public, plus logs and quality reports).
-- Reconstructed from the production database in October 2026; run it BEFORE post_setup.sql.
-- Column sizes matter: the application truncates its labels to fit them.

create table if not exists public.table_raw (
  id serial primary key,
  date_collecte timestamp default now(),
  secteur varchar(50) not null,
  source_api varchar(50) not null,
  endpoint text,
  donnee_brute jsonb not null,
  statut varchar(20) default 'brut',
  nb_lignes integer,
  notes_agent text
);

create table if not exists public.table_clean (
  id serial primary key,
  id_raw integer references public.table_raw(id),
  date_traitement timestamp default now(),
  secteur varchar(50),
  source_api varchar(50),
  date_reference date,
  indicateur varchar(100),
  valeur double precision,
  unite varchar(30),
  region varchar(50),
  pays varchar(10) default 'TCD',
  statut_qualite varchar(20),
  regles_appliquees text[],
  instructions_texte text,
  code_genere text,
  flag_anomalie boolean default false,
  notes_superviseur text
);

create table if not exists public.table_public (
  id serial primary key,
  id_clean integer references public.table_clean(id),
  date_publication timestamp default now(),
  secteur varchar(50),
  source_api varchar(50),
  date_reference date,
  indicateur varchar(100),
  valeur double precision,
  unite varchar(30),
  region varchar(50),
  pays varchar(10) default 'TCD',
  licence varchar(50) default 'CC BY 4.0',
  score_qualite double precision,
  approuve_par varchar(50),
  notes_publiques text
);

create table if not exists public.table_logs (
  id serial primary key,
  id_donnee integer,
  agent varchar(60),
  type_operation varchar(50),
  valeur_avant text,
  valeur_apres text,
  regle_appliquee varchar(10),
  code_genere text,
  "timestamp" timestamp default now(),
  superviseur varchar(50)
);

create table if not exists public.table_rapports (
  id serial primary key,
  id_raw integer references public.table_raw(id),
  date_rapport timestamp default now(),
  score_global double precision,
  score_completude double precision,
  score_coherence double precision,
  nb_anomalies integer,
  nb_doublons integer,
  statut_final varchar(20),
  commentaire text
);

-- Server-only access: RLS on, no policy (the service-role key bypasses it).
alter table public.table_raw enable row level security;
alter table public.table_clean enable row level security;
alter table public.table_public enable row level security;
alter table public.table_logs enable row level security;
alter table public.table_rapports enable row level security;
