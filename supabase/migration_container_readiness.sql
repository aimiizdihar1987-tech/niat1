-- Run once on an existing Niat Supabase project before container deployment.
-- New projects receive the same table from supabase/schema.sql.

create table if not exists public.app_settings (
  key        text primary key,
  value      jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.app_settings enable row level security;

-- No browser/client policy is intentional. Niat's backend accesses these
-- operational settings with the service role; authenticated clients cannot
-- fetch another teacher's timetable directly.
