-- The old domain rule bounded every indicator named "...rate" to 0-100. "Under-5 mortality rate"
-- is expressed per 1,000 live births (Chad: ~100-130), so 9 correct World Bank values were
-- published with a DOMAIN_VIOLATION / SUPERVISOR_REVIEW flag and a lowered quality score.
-- The rule is fixed in code (patch C); this clears the wrong flag on the rows already published.
-- Idempotent: after one run nothing matches any more.
with fixed as (
  update public.table_public
     set notes_publiques = trim(regexp_replace(notes_publiques, '\s*\[Data Science Flags: [^]]*\]', '')),
         score_qualite = 1.0
   where indicateur = 'Under-5 mortality rate'
     and notes_publiques like '%DOMAIN_VIOLATION%'
  returning id_clean
)
update public.table_clean c
   set statut_qualite = 'validated',
       flag_anomalie = false,
       instructions_texte = 'Processed via 10 Data Science rules. Flags: none',
       regles_appliquees = array['normalisation', 'validation']
  from fixed f
 where c.id = f.id_clean;
