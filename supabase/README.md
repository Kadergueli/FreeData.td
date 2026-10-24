# Supabase SQL — what to run, in which order

A new project needs these files, in this order (all are idempotent unless noted):

1. `core_schema.sql` — the five pipeline tables (`table_raw`, `table_clean`, `table_public`, `table_logs`, `table_rapports`). `schema.sql` is the **legacy** prototype table: skip it.
2. `post_setup.sql` — indexes (including the unique key that prevents duplicate public rows).
3. `studies.sql` — AI studies (`table_etudes`).
4. `admin_setup.sql` — administrators and audit log.
5. `harvest_runs_setup.sql` — history of collection runs.
6. `quarantine_setup.sql` — rows held for review.
7. `data_admin_setup.sql` — archive of deleted observations.
8. `maintenance/*.sql` — dated, one-off fixes already applied in production (widened columns,
   revoked RPC, cleanup). Run those whose date is after your project's creation.

Every table has row-level security enabled **with no policy**: only the server (service-role key)
reads and writes. The "RLS enabled, no policy" advisories in the Supabase dashboard are intentional.

Manual dashboard settings that SQL cannot change: Auth -> Providers -> Email -> *Leaked password
protection* (if your plan offers it), and disabling public sign-ups (admins are created by hand).
