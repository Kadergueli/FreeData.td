-- Patch 0035: the pipeline log label did not fit varchar(20); widen it (already applied in production).
alter table public.table_logs alter column agent type varchar(60);
