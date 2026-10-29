-- Patch 0057: OpenStreetMap is no longer collected for the transport sector (the public Overpass
-- servers cannot answer the road / aerodrome counts in time; airports now come from OurAirports).
-- Removes the 5 partial rows left by the first, interrupted attempt (3 regions only), which would
-- otherwise look like a complete regional series.
delete from public.table_public where secteur = 'transport' and source_api = 'OpenStreetMap';
