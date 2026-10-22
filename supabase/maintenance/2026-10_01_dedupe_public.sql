-- Étape 2 — supprime les doublons de table_public (garde la ligne la plus récente de chaque groupe).
-- Les lignes supprimées sont d'abord copiées dans table_public_dupes_backup. Rejouable sans risque.
create table if not exists public.table_public_dupes_backup
  as select * from public.table_public with no data;
alter table public.table_public_dupes_backup enable row level security;

with doomed as (
  select id from (
    select id, row_number() over (
      partition by secteur, source_api, date_reference, indicateur, region
      order by id desc) as rn
    from public.table_public) t
  where rn > 1
)
insert into public.table_public_dupes_backup
select p.* from public.table_public p
join doomed d on d.id = p.id
where not exists (select 1 from public.table_public_dupes_backup b where b.id = p.id);

delete from public.table_public p
using (
  select id from (
    select id, row_number() over (
      partition by secteur, source_api, date_reference, indicateur, region
      order by id desc) as rn
    from public.table_public) t
  where rn > 1
) d
where p.id = d.id;
