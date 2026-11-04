-- Read-only audit: retail prices more than 3 times above, or 3 times below, the median of the SAME
-- product in the SAME market. A single odd month is usually a typo; the same product jumping in
-- dozens of markets in the same months is usually a change of unit or product variant upstream.
-- Run in the Supabase SQL editor. Nothing is modified.
with m as (
  select indicateur, region, percentile_cont(0.5) within group (order by valeur) as med
  from public.table_public
  where secteur = 'markets' and source_api in ('WFP', 'FEWS NET')
  group by 1, 2
  having count(*) >= 12
)
select p.indicateur, to_char(p.date_reference, 'YYYY-MM') as mois, count(*) as lignes, count(distinct p.region) as marches,
       round(min(p.valeur / m.med)::numeric, 2) as ratio_min, round(max(p.valeur / m.med)::numeric, 2) as ratio_max
from public.table_public p
join m using (indicateur, region)
where p.secteur = 'markets' and p.source_api in ('WFP', 'FEWS NET')
  and (p.valeur > 3 * m.med or p.valeur < m.med / 3)
group by 1, 2
order by lignes desc, p.indicateur, mois;
