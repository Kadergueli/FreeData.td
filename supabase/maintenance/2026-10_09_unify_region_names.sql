-- Patch 0058: one spelling per region name (same rules as app/regions.py).
-- The region is part of the unique key of table_public: renaming can make two rows collide (same
-- sector, source, date, indicator and, once renamed, the same region). Those duplicates are copied to
-- table_public_region_merge_backup, then removed: the row that already had the canonical name is kept,
-- otherwise the newest. Safe to run more than once.

begin;

create temp table region_map(old_region text primary key, new_region text not null) on commit drop;
insert into region_map(old_region, new_region) values
    ('Abéché (Ouaddaï)', 'Abeche (Ouaddai)'),
    ('Amdjarass (Ennedi Est)', 'Am-Djarass (Ennedi Est)'),
    ('Bardaï (Tibesti)', 'Bardai (Tibesti)'),
    ('Binder (Mayo Kebbi Ouest)', 'Binder (Mayo-Kebbi Ouest)'),
    ('Bokoro (Hadjer Lamis)', 'Bokoro (Hadjer-Lamis)'),
    ('Bongor (Mayo Kebbi Est)', 'Bongor (Mayo-Kebbi Est)'),
    ('Bousso (Chari Baguirmi)', 'Bousso (Chari-Baguirmi)'),
    ('Danamadji (Moyen Chari)', 'Danamadji (Moyen-Chari)'),
    ('Dembe (Ndjaména)', 'Dembe (N''Djamena)'),
    ('Dourbali (Chari Baguirmi)', 'Dourbali (Chari-Baguirmi)'),
    ('Fianga (Mayo Kebbi Est)', 'Fianga (Mayo-Kebbi Est)'),
    ('Goz Beïda (Sila)', 'Goz Beida (Sila)'),
    ('Gueledeng (Mayo Kebbi Est)', 'Gueledeng (Mayo-Kebbi Est)'),
    ('Kélo (Tandjile)', 'Kelo (Tandjile)'),
    ('Kyabe (Moyen Chari)', 'Kyabe (Moyen-Chari)'),
    ('Laï (Tandjile)', 'Lai (Tandjile)'),
    ('Laï (Tandjilé)', 'Lai (Tandjile)'),
    ('Lere (Mayo Kebbi Ouest)', 'Lere (Mayo-Kebbi Ouest)'),
    ('Mandelia (Chari Baguirmi)', 'Mandelia (Chari-Baguirmi)'),
    ('Maro (Moyen Chari)', 'Maro (Moyen-Chari)'),
    ('Massaguet (Hadjer Lamis)', 'Massaguet (Hadjer-Lamis)'),
    ('Massakory (Hadjer Lamis)', 'Massakory (Hadjer-Lamis)'),
    ('Massenya (Chari Baguirmi)', 'Massenya (Chari-Baguirmi)'),
    ('Mbaïbokoum (Logone Oriental)', 'Mbaibokoum (Logone Oriental)'),
    ('Mbaïnamar (Logone Occidental)', 'Mbainamar (Logone Occidental)'),
    ('Mongo (Guéra)', 'Mongo (Guera)'),
    ('Moussoro (Barh El Gazal)', 'Moussoro (Barh el Gazel)'),
    ('Moussoro (Barh El Gazel)', 'Moussoro (Barh el Gazel)'),
    ('N''djamena (Atrone) (Ndjaména)', 'N''Djamena (Atrone) (N''Djamena)'),
    ('N''Djamena (Chari-Baguirmi)', 'N''Djamena (N''Djamena)'),
    ('Ndjamena (Marche A Mil) (Ndjaména)', 'N''Djamena (Marche A Mil) (N''Djamena)'),
    ('Ndjamena (Ndjaména)', 'N''Djamena (N''Djamena)'),
    ('Oum Hadjer', 'Oum Hadjer (Batha)'),
    ('Oumhadjer (Batha)', 'Oum Hadjer (Batha)'),
    ('Pala (Mayo Kebbi Ouest)', 'Pala (Mayo-Kebbi Ouest)'),
    ('Pont Karol (Mayo Kebbi Est)', 'Pont Karol (Mayo-Kebbi Est)'),
    ('Sarh (Moyen Chari)', 'Sarh (Moyen-Chari)'),
    ('Sido (Moyen Chari)', 'Sido (Moyen-Chari)');

-- every row whose region is renamed, plus the rows that already carry a target name
create temp table region_rank on commit drop as
with eff as (
    select t.id, t.secteur, t.source_api, t.date_reference, t.indicateur,
           coalesce(m.new_region, t.region) as nr, (m.old_region is null) as already
    from public.table_public t
    left join region_map m on m.old_region = t.region
    where t.region in (select old_region from region_map) or t.region in (select new_region from region_map)
)
select id, row_number() over (
           partition by secteur, source_api, date_reference, indicateur, nr
           order by already desc, id desc) as rn
from eff;

create table if not exists public.table_public_region_merge_backup (like public.table_public including defaults);
alter table public.table_public_region_merge_backup enable row level security;

insert into public.table_public_region_merge_backup
    select t.* from public.table_public t where t.id in (select id from region_rank where rn > 1);

delete from public.table_public where id in (select id from region_rank where rn > 1);

update public.table_public t
   set region = m.new_region
  from region_map m
 where t.region = m.old_region;

commit;
