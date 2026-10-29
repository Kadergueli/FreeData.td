-- Patch 0058: keep 30 days of audit trail. The application now does the same after every harvest
-- (ObservationRepository.purge_old_logs); this file is the one-off catch-up.
delete from public.table_logs where timestamp < now() - interval '30 days';
