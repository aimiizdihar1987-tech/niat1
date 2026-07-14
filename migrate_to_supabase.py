#!/usr/bin/env python3
"""
One-time migration: local files -> Supabase. Python stdlib only.

BEFORE running this:
  1. Create a Supabase project at supabase.com.
  2. Open Supabase dashboard -> SQL Editor -> New query, paste the contents
     of supabase/schema.sql, and click Run.
  3. Fill in supabase_config.txt with your Project URL + anon key + service_role key.

Usage (run from this folder):
    python migrate_to_supabase.py --check     verify the connection only
    python migrate_to_supabase.py --users     create teacher accounts in Supabase Auth
                                               (asks you to type a NEW password for each
                                               existing username, right here in the
                                               terminal — hidden input, sent only to
                                               your own Supabase project, never shown
                                               on screen or logged anywhere else)
    python migrate_to_supabase.py --data      push question bank + lessons + classrooms
                                               + students + timetable
    python migrate_to_supabase.py --all       both of the above

Safe to re-run: questions/classrooms/students are upserted by their unique key
(hash / class_name / email), so running twice won't create duplicates. Lessons
and timetable rows do NOT have a natural unique key in the old schema, so running
--data twice will duplicate those two — that's why each step prints a count and
you should only run --data once per table (or truncate the table in Supabase
first if you need a clean re-import).
"""
import argparse
import getpass
import json
import os
import sqlite3
import sys

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))


def _iso_or_none(v):
    return v if v else None


def check_connection():
    if not sb.configured():
        print("supabase_config.txt is missing values.")
        print("Fill in SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY first.")
        return False
    try:
        sb.select("classrooms", params={"select": "class_name", "limit": "1"})
        print("Connected to Supabase OK.")
        return True
    except sb.SupabaseError as e:
        print("Connection failed:", e)
        print("Did you run supabase/schema.sql yet? (Supabase dashboard -> SQL Editor)")
        return False


def migrate_users():
    users_file = os.path.join(ROOT, "users.json")
    try:
        with open(users_file, encoding="utf-8") as f:
            users = json.load(f)
    except FileNotFoundError:
        print("No users.json found -- nothing to migrate.")
        return
    print("Existing local accounts:", ", ".join(users))
    print("Old passwords are hashed and cannot be recovered, so set a NEW")
    print("password for each account below. Nothing you type here is sent")
    print("anywhere except your own Supabase project.\n")
    for username, rec in users.items():
        full_name = rec.get("full_name") or username
        role = (rec.get("role") or "teacher").lower()
        role_norm = role if role in ("teacher", "admin", "super_admin") else "teacher"
        pw = getpass.getpass("New Supabase password for '{}' ({}), min 6 chars: "
                              .format(username, full_name))
        if len(pw) < 6:
            print("  Skipped -- password must be at least 6 characters.")
            continue
        try:
            sb.admin_create_user(username, pw, full_name=full_name, role_name=role_norm)
            print("  Created Supabase account for '{}' (role: {}).".format(username, role_norm))
        except sb.SupabaseError as e:
            print("  FAILED for '{}':".format(username), e)


def migrate_classrooms():
    path = os.path.join(ROOT, "classrooms.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("No classrooms.json found -- skipped.")
        return
    rows = [{"class_name": "lesson_plan", "classroom_id": data["lesson_plan"]}]
    for name, cid in (data.get("classes") or {}).items():
        rows.append({"class_name": name, "classroom_id": cid})
    sb.insert("classrooms", rows, upsert_on="class_name")
    print("Migrated {} classrooms.".format(len(rows)))


def migrate_students():
    path = os.path.join(ROOT, "Email Student Prototype.txt")
    try:
        with open(path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        print("No 'Email Student Prototype.txt' found -- skipped.")
        return
    rows = []
    for line in lines:
        if ":" in line:
            label, email = line.split(":", 1)
        elif "," in line:
            label, email = line.split(",", 1)
        else:
            label, email = "Student", line
        email = email.strip()
        if "@" in email:
            rows.append({"label": label.strip(), "email": email})
    if rows:
        sb.insert("students", rows, upsert_on="email")
        print("Migrated {} students.".format(len(rows)))
    else:
        print("No student rows recognised -- check the file format.")


def migrate_timetable():
    # timetable.json is now per-teacher (keyed by login username). The
    # Supabase `timetable_classes` table has no owner column yet (deferred —
    # the live app doesn't read timetables from Supabase at all currently),
    # so this still only migrates Cikgu Aimi's branch, same as before.
    path = os.path.join(ROOT, "timetable.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("No timetable.json found -- skipped.")
        return
    rows = (data.get("teachers") or {}).get("aimiizdihar", {}).get("classes") or []
    if rows:
        sb.insert("timetable_classes", rows)
        print("Migrated {} timetable rows.".format(len(rows)))


def migrate_question_bank():
    db_file = os.path.join(ROOT, "bank_soalan.db")
    if not os.path.isfile(db_file):
        print("No bank_soalan.db found -- nothing to migrate.")
        return
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM soalan").fetchall()
    conn.close()
    if not rows:
        print("Question bank is empty -- nothing to migrate.")
        return
    batch = []
    for r in rows:
        d = dict(r)
        d["pilihan"] = json.loads(d["pilihan"])
        d["tarikh_cipta"] = _iso_or_none(d.get("tarikh_cipta"))
        d["tarikh_akhir_guna"] = _iso_or_none(d.get("tarikh_akhir_guna"))
        d.pop("id", None)
        batch.append(d)
    for i in range(0, len(batch), 200):
        sb.insert("soalan", batch[i:i + 200], upsert_on="hash")
    print("Migrated {} questions.".format(len(batch)))


def migrate_lessons():
    db_file = os.path.join(ROOT, "bank_soalan.db")
    if not os.path.isfile(db_file):
        return
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM lessons").fetchall()
    conn.close()
    if not rows:
        print("No saved lessons -- nothing to migrate.")
        return
    batch = []
    for r in rows:
        d = dict(r)
        d.pop("id", None)
        for key in ("plan_json", "worksheet_json", "inputs_json"):
            d[key] = json.loads(d[key]) if d.get(key) else None
        batch.append(d)
    for i in range(0, len(batch), 100):
        sb.insert("lessons", batch[i:i + 100])
    print("Migrated {} lessons.".format(len(batch)))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify the Supabase connection only")
    ap.add_argument("--users", action="store_true", help="create teacher accounts in Supabase Auth")
    ap.add_argument("--data", action="store_true", help="push bank/lessons/classrooms/students/timetable")
    ap.add_argument("--all", action="store_true", help="--users + --data")
    args = ap.parse_args()

    if not any([args.check, args.users, args.data, args.all]):
        ap.print_help()
        return

    if not check_connection():
        sys.exit(1)
    if args.check:
        return

    if args.users or args.all:
        migrate_users()
    if args.data or args.all:
        migrate_classrooms()
        migrate_students()
        migrate_timetable()
        migrate_question_bank()
        migrate_lessons()
    print("\nDone.")


if __name__ == "__main__":
    main()
