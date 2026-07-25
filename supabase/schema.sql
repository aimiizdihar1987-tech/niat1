-- ============================================================
--  NIAT — Supabase schema
--  Run this ONCE in: Supabase dashboard -> SQL Editor -> New query -> Run
-- ============================================================

-- ---------- profiles (extends Supabase Auth users) ----------
-- Supabase Auth (auth.users) handles the password itself (hashed, managed by
-- Supabase). This table holds everything Niat needs on top: display name,
-- role (ready for teacher / admin / super_admin), avatar.
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  username    text unique not null,        -- what the teacher types to log in
  full_name   text,
  role        text not null default 'teacher'
              check (role in ('teacher', 'admin', 'super_admin')),
  avatar_url  text,                        -- Supabase Storage public URL, or null
  created_at  timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Everyone logged in can read profiles (needed to show names/avatars in the UI).
create policy "profiles are readable by any authenticated user"
  on public.profiles for select
  using (auth.role() = 'authenticated');

-- A user may update their own profile (name, avatar) but never their own role.
create policy "users update their own profile"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id and role = (select role from public.profiles where id = auth.uid()));

-- ---------- soalan (question bank) ----------
create table if not exists public.soalan (
  id                bigint generated always as identity primary key,
  sp_kod            text not null,
  aras              text not null check (aras in ('LOTS', 'MOTS', 'HOTS')),
  soalan            text not null,
  pilihan           jsonb not null,             -- ["...", "...", "...", "..."]
  jawapan_betul     text not null,
  maklum_balas      text default '',
  markah            int default 1,
  hash              text unique not null,        -- de-dup, same idea as SQLite version
  status            text default 'diluluskan',
  kali_diguna       int default 0,
  kadar_betul       real,
  topic             text default '',
  theme             text default '',
  tarikh_cipta      timestamptz default now(),
  tarikh_akhir_guna timestamptz
);
create index if not exists idx_soalan_sp_aras on public.soalan (sp_kod, aras, status);

alter table public.soalan enable row level security;
create policy "soalan readable by authenticated users"
  on public.soalan for select using (auth.role() = 'authenticated');
create policy "soalan writable by authenticated users"
  on public.soalan for insert with check (auth.role() = 'authenticated');
create policy "soalan updatable by authenticated users"
  on public.soalan for update using (auth.role() = 'authenticated');

-- ---------- lessons ----------
create table if not exists public.lessons (
  id             bigint generated always as identity primary key,
  owner          uuid references auth.users(id),
  created_at     timestamptz not null default now(),
  title          text,
  kelas          text,
  tarikh         text,
  minggu         text,
  theme          text,
  topic          text,
  skill          text,
  plan_json      jsonb,
  worksheet_json jsonb,
  inputs_json    jsonb,
  score          real
);
create index if not exists idx_lessons_owner on public.lessons (owner);

alter table public.lessons enable row level security;
create policy "lessons readable by authenticated users"
  on public.lessons for select using (auth.role() = 'authenticated');
create policy "lessons writable by authenticated users"
  on public.lessons for insert with check (auth.role() = 'authenticated');
create policy "lessons updatable by owner or admin"
  on public.lessons for update
  using (
    owner = auth.uid()
    or exists (select 1 from public.profiles where id = auth.uid() and role in ('admin', 'super_admin'))
  );
create policy "lessons deletable by owner or admin"
  on public.lessons for delete
  using (
    owner = auth.uid()
    or exists (select 1 from public.profiles where id = auth.uid() and role in ('admin', 'super_admin'))
  );

-- ---------- classrooms (Google Classroom IDs, was classrooms.json) ----------
create table if not exists public.classrooms (
  class_name   text primary key,           -- "3 Delima", or "lesson_plan" for the RPH repo
  classroom_id text not null
);
alter table public.classrooms enable row level security;
create policy "classrooms readable by authenticated users"
  on public.classrooms for select using (auth.role() = 'authenticated');

-- ---------- students (pilot distribution list, was Email Student Prototype.txt) ----------
create table if not exists public.students (
  id     bigint generated always as identity primary key,
  label  text not null,          -- "Student A"
  email  text not null unique
);
alter table public.students enable row level security;
create policy "students readable by authenticated users"
  on public.students for select using (auth.role() = 'authenticated');

-- ---------- timetable (was timetable.json) ----------
create table if not exists public.timetable_classes (
  id       bigint generated always as identity primary key,
  day      text not null,
  time     text not null,
  class    text not null,
  duration int not null
);
alter table public.timetable_classes enable row level security;
create policy "timetable readable by authenticated users"
  on public.timetable_classes for select using (auth.role() = 'authenticated');

-- ---------- vocab_words (CEFR B1 Preliminary allowed-vocabulary list) ----------
-- Populated by push_wordlist_supabase.py from data/cefr_b1_wordlist.json
-- (extracted from "CEFR B1-preliminary-vocabulary-list.pdf"). Worksheet
-- generation only uses words from this list so questions match pupil level.
create table if not exists public.vocab_words (
  id         bigint generated always as identity primary key,
  word       text not null unique,
  level      text not null default 'B1',
  source     text default 'Cambridge B1 Preliminary Vocabulary List (Aug 2025)',
  created_at timestamptz not null default now()
);
alter table public.vocab_words enable row level security;
create policy "vocab readable by authenticated users"
  on public.vocab_words for select using (auth.role() = 'authenticated');

-- ---------- prestasi_murid (per-pupil quiz performance; feeds Agent 5) ----------
-- Each read of a distributed quiz's results banks one row per pupil. Agent 5
-- averages these across recent lessons to decide a differentiated worksheet level.
create table if not exists public.prestasi_murid (
  id         bigint generated always as identity primary key,
  emel       text not null,
  nama       text,
  kelas      text,
  peratus    real not null,          -- 0..100
  topik      text,
  sp         text,                    -- learning standard code(s)
  lesson_id  text,
  dicipta    timestamptz not null default now()
);
create index if not exists idx_prestasi_emel on public.prestasi_murid (emel);
create index if not exists idx_prestasi_kelas on public.prestasi_murid (kelas);
alter table public.prestasi_murid enable row level security;
create policy "prestasi readable by authenticated users"
  on public.prestasi_murid for select using (auth.role() = 'authenticated');
create policy "prestasi writable by authenticated users"
  on public.prestasi_murid for insert with check (auth.role() = 'authenticated');

-- ---------- auto-create a profile row whenever a new Auth user signs up ----------
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, username, full_name, role)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'username', split_part(new.email, '@', 1)),
    new.raw_user_meta_data->>'full_name',
    coalesce(new.raw_user_meta_data->>'role', 'teacher')
  )
  on conflict (id) do nothing;
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
