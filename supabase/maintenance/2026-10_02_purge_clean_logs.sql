-- Étape 4 — retire de table_clean les lignes qui ne sont plus référencées par table_public
-- (copies créées à chaque ancienne collecte ; la donnée brute reste dans table_raw),
-- Prérequis : index table_public_id_clean_idx (post_setup.sql). Sur une très grosse table, supprimer
-- par lots (ajouter `and c.id in (select id from table_clean order by id limit 100000)`) pour éviter
-- le délai d'expiration des requêtes.
-- puis les journaux de table_logs qui pointent vers des lignes inexistantes. Rejouable.
delete from public.table_clean c
where not exists (select 1 from public.table_public p where p.id_clean = c.id);

delete from public.table_logs l
where not exists (select 1 from public.table_clean c where c.id = l.id_donnee);
