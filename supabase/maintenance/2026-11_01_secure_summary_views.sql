-- Supabase security advisor: v_region_counts and v_catalog were SECURITY DEFINER views readable by
-- anon. Run once in the SQL editor. The app is unaffected (it uses the service-role key); until it is
-- run the old behaviour simply continues. Safe to repeat.
alter view public.v_region_counts set (security_invoker = true);
alter view public.v_catalog set (security_invoker = true);
revoke all on public.v_region_counts, public.v_catalog from anon, authenticated;
grant select on public.v_region_counts, public.v_catalog to service_role;
