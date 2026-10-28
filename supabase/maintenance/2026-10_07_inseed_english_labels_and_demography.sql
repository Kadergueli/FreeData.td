-- Patch 0050: demography sector + English indicator names for the INSEED rows.
-- Safe to run more than once. Only rows whose source is 'INSEED' are touched.
-- (The unique key of table_public is secteur+source+date+indicateur+region: renaming in place
--  cannot collide, because the new names are as distinct as the old ones.)

begin;

-- 1. Population moves from economy to demography (it was filed under economy by mistake).
update public.table_public
   set secteur = 'demography'
 where source_api = 'INSEED' and indicateur like 'Population%' and secteur <> 'demography';

-- 2. French -> English indicator names and units, same vocabulary as app/agents/inseed.py.
update public.table_public
   set indicateur = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(
         indicateur,
         'Établissements de santé', 'Health facilities'),
         'hôpital national', 'national hospital'),
         'hôpital provincial', 'provincial hospital'),
         'hôpital de district', 'district hospital'),
         'centre de santé', 'health centre'),
         'clinique', 'clinic'),
         ', privé', ', private'),
         ' - privé', ' - private'),
         'communautaire', 'community'),
         'tous âges', 'all ages'),
         'hommes', 'men'),
         'femmes', 'women'),
         'urbain', 'urban'),
         ' ans et plus', ' years and over'),
         ' ans,', ' years,'),
         'Indice des prix à la consommation', 'Consumer price index'),
       unite = case unite when 'établissements' then 'facilities' when 'habitants' then 'inhabitants' when 'indice' then 'index' else unite end
 where source_api = 'INSEED';

-- "5-9 ans" at the very end of a name (no trailing comma)
update public.table_public
   set indicateur = regexp_replace(indicateur, ' ans$', ' years')
 where source_api = 'INSEED' and indicateur ~ ' ans$';

commit;
