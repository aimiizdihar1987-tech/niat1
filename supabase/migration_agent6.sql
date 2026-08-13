-- ==========================================================================
-- Agent 6 (Reminder) — tables that were missing from the live database.
--
-- The original schema.sql was run before these two tables existed, so Agent 6
-- crashed on every run with PGRST205 "Could not find the table in the schema
-- cache". Paste this whole file into the Supabase SQL editor and Run.
--
-- Safe to run more than once: the tables are guarded by IF NOT EXISTS and each
-- policy is dropped before it is recreated (Postgres has no CREATE POLICY IF
-- NOT EXISTS). Re-running the full schema.sql instead would fail on the
-- policies that already exist — use this file.
-- ==========================================================================

-- ---------- peringatan (reminder escalation tracker) ----------
-- One row per (pupil, assignment). `kali` = how many reminders that pupil has
-- already had, which is what picks the escalation level:
--   0 -> gentle    1 -> firm    2+ -> notify_teacher (and the teacher is emailed)
create table if not exists public.peringatan (
  emel       text not null,
  kelas      text,
  tugasan    text not null,
  kali       integer not null default 0,
  aras_akhir text,                     -- gentle | firm | notify_teacher
  terakhir   timestamptz,
  primary key (emel, tugasan)
);
create index if not exists idx_peringatan_tugasan on public.peringatan (tugasan);
alter table public.peringatan enable row level security;

drop policy if exists "peringatan readable by authenticated users" on public.peringatan;
create policy "peringatan readable by authenticated users"
  on public.peringatan for select using (auth.role() = 'authenticated');
drop policy if exists "peringatan writable by authenticated users" on public.peringatan;
create policy "peringatan writable by authenticated users"
  on public.peringatan for insert with check (auth.role() = 'authenticated');
drop policy if exists "peringatan updatable by authenticated users" on public.peringatan;
create policy "peringatan updatable by authenticated users"
  on public.peringatan for update using (auth.role() = 'authenticated');

-- ---------- prestasi_murid (per-pupil quiz performance) ----------
-- Feeds Agent 5's banding and Agent 6's tone (a strong pupil and a struggling
-- pupil get very differently worded reminders).
create table if not exists public.prestasi_murid (
  id         bigint generated always as identity primary key,
  emel       text not null,
  nama       text,
  kelas      text,
  peratus    real not null,          -- 0..100
  topik      text,
  sp         text,                   -- learning standard code(s)
  lesson_id  text,
  dicipta    timestamptz not null default now()
);
create index if not exists idx_prestasi_emel on public.prestasi_murid (emel);
create index if not exists idx_prestasi_kelas on public.prestasi_murid (kelas);
alter table public.prestasi_murid enable row level security;

drop policy if exists "prestasi readable by authenticated users" on public.prestasi_murid;
create policy "prestasi readable by authenticated users"
  on public.prestasi_murid for select using (auth.role() = 'authenticated');
drop policy if exists "prestasi writable by authenticated users" on public.prestasi_murid;
create policy "prestasi writable by authenticated users"
  on public.prestasi_murid for insert with check (auth.role() = 'authenticated');
