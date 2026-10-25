-- Patch 0040: "Active market price datasets" counted HDX files; it is metadata, not a measurement.
-- The collector that produced it was removed. Already applied in production (1 row).
delete from public.table_public
 where source_api = 'HDX / UN OCHA' and indicateur = 'Active market price datasets';
