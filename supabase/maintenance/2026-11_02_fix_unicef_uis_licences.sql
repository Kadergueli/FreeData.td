-- Corrige l'étiquette de licence de deux sources, d'après leurs pages officielles lues le 2026-11-10 :
--   UNICEF Data  -> CC BY 3.0 IGO  (article officiel UNICEF « 100 percent open data compliant »)
--   UNESCO UIS   -> CC BY-SA 4.0   (conditions du navigateur de données de l'UIS ; partage à l'identique)
-- Ne touche que la colonne licence, pour ces deux sources.
update table_public set licence = 'CC BY 3.0 IGO' where source_api = 'UNICEF Data' and licence <> 'CC BY 3.0 IGO';
update table_public set licence = 'CC BY-SA 4.0'  where source_api = 'UNESCO UIS' and licence <> 'CC BY-SA 4.0';
