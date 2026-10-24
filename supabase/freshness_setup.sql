-- Latest data per source, computed in the database (the API cannot GROUP BY, and scanning 50 000
-- rows from Python on every status page load would be slow). Server-only: service role.
create or replace function public.source_freshness()
returns table (sector text, source text, rows bigint, latest_reference date, last_published timestamp)
language sql stable security invoker set search_path = public
as $$
  select secteur::text, source_api::text, count(*), max(date_reference), max(date_publication)
  from public.table_public
  group by secteur, source_api
$$;

revoke execute on function public.source_freshness() from public, anon, authenticated;
grant execute on function public.source_freshness() to service_role;
