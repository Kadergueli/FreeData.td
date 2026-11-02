-- FreeData.td - two read-only summary views (run once in the Supabase SQL editor).
--
-- Supabase returns at most 1000 rows per request, so the app can no longer rebuild the region
-- list and the indicator catalog by reading table_public rows itself: it only ever saw the newest
-- 1000. These views let the database do the counting. Until they exist the app keeps working with
-- its old (sampled) method, so running this file is safe at any time and can be repeated.

create or replace view public.v_region_counts as
select region, count(*)::bigint as n
from public.table_public
where region is not null
group by region;

create or replace view public.v_catalog as
select secteur, indicateur, source_api,
       count(*)::bigint as records,
       min(date_reference) as first_date,
       max(date_reference) as last_date
from public.table_public
group by secteur, indicateur, source_api;

grant select on public.v_region_counts to anon, authenticated, service_role;
grant select on public.v_catalog to anon, authenticated, service_role;
