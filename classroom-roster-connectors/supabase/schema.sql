create extension if not exists pgcrypto;

create table if not exists public.classroom_members (
  id uuid primary key default gen_random_uuid(),
  student_email text not null unique,
  class_name text not null check (class_name in ('3 Delima', '3 Zamrud', '3 Berlian')),
  achievement_level text not null check (
    achievement_level in ('advanced', 'intermediate', 'lower_achiever')
  ),
  is_active boolean not null default true,
  source text not null default 'classroom_invite_confirmed_by_user',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists classroom_members_class_name_idx
  on public.classroom_members (class_name);

create index if not exists classroom_members_achievement_level_idx
  on public.classroom_members (achievement_level);

alter table public.classroom_members enable row level security;

comment on table public.classroom_members is
  'Keahlian kelas yang disahkan pengguna. Import dijalankan dari persekitaran tempatan; ID tidak disimpan dalam repositori.';
