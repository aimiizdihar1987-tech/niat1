-- ============================================================
--  Niat — migration: lessons.classroom_doc_id / classroom_url / report_text
-- ============================================================
--  WHY: lesson plans are now auto-posted to the "Lesson Plan" Classroom as a
--  Google Doc the moment the teacher approves the RPH (see
--  server.classroom_lessonplan). These columns remember which Doc a lesson
--  was posted as, so the reflection/report step can update THAT SAME Doc
--  (REFLEKSI cell + a class-report section) instead of creating a new
--  Classroom post every time. report_text stores the class report text
--  alongside the reflection so it's available if the lesson is reopened.
--
--  Run this in: Supabase dashboard -> SQL Editor -> New query -> Run.
-- ============================================================

alter table public.lessons
  add column if not exists classroom_doc_id text,
  add column if not exists classroom_url    text,
  add column if not exists report_text      text;
