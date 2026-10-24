-- Patch 0038: the helper function that enables RLS on new tables was callable through the public
-- REST API (/rest/v1/rpc/rls_auto_enable) by anonymous visitors. Event triggers run as the owner,
-- so revoking EXECUTE from API roles does not affect it. Already applied in production.
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
