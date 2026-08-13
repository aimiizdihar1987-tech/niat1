-- ============================================================
--  Niat — migration: give timetable_classes an owner
-- ============================================================
--  WHY: the original timetable_classes table is (day, time, class, duration)
--  only. timetable.json is per-teacher (keyed by login username), so the
--  table cannot represent who a slot belongs to. Without these columns,
--  server.py's _load_timetable(username) CANNOT safely read from Supabase:
--  it would hand every teacher's schedule to every teacher.
--
--  Run this in: Supabase dashboard -> SQL Editor -> New query -> Run.
--  Then re-run:  python migrate_to_supabase.py --timetable
--  Only after BOTH steps should the cloud read path be switched on.
-- ============================================================

alter table public.timetable_classes
  add column if not exists owner_username text,
  add column if not exists teacher_name   text default '',
  add column if not exists school         text default '',
  add column if not exists class_pupils   int;

-- One teacher cannot have two slots at the same day+time+class.
create unique index if not exists timetable_owner_slot_uniq
  on public.timetable_classes (owner_username, day, "time", class);

create index if not exists timetable_owner_idx
  on public.timetable_classes (owner_username);

-- Tighten RLS: a teacher sees only their own rows; admins see all.
drop policy if exists "timetable readable by authenticated users"
  on public.timetable_classes;

create policy "timetable readable by owner"
  on public.timetable_classes for select
  using (
    owner_username = (auth.jwt() -> 'user_metadata' ->> 'username')
    or coalesce(auth.jwt() -> 'user_metadata' ->> 'role', 'teacher')
       in ('admin', 'super_admin')
  );

-- Existing rows predate the owner column. They are Cikgu Aimi's (the only
-- teacher migrated so far — see migrate_to_supabase.py migrate_timetable()).
-- Adjust the username if that is not correct for your project.
update public.timetable_classes
   set owner_username = 'aimiizdihar'
 where owner_username is null;
