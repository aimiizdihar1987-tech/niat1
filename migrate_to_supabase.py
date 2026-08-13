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
    python migrate_to_supabase.py --data --owner USERNAME
                                             push question bank + lessons + classrooms,
                                             students, per-teacher timetables and settings
    python migrate_to_supabase.py --timetable push only durable timetable settings
    python migrate_to_supabase.py --all       both of the above

Safe to re-run: questions/classrooms/students/timetables/settings are upserted
by stable keys. Lessons are matched against their existing content before being
inserted. ``--owner`` assigns imported lessons to an existing Supabase profile;
when it is omitted, migration can infer the owner only if exactly one profile
exists.
"""
import argparse
import getpass
import json
import os
import sqlite3
import sys

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
MIGRATION_OWNER = ""


def _iso_or_none(v):
    return v if v else None


def check_connection():
    if not sb.configured():
        print("supabase_config.txt is missing values.")
        print("Fill in SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY first.")
        return False
    try:
        sb.select("classrooms", params={"select": "class_name", "limit": "1"})
        sb.select("app_settings", params={"select": "key", "limit": "1"})
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
    last_name = ""
    for line in lines:
        if ":" in line:
            label, email = line.split(":", 1)
        elif "," in line:
            label, email = line.split(",", 1)
        elif "@" in line:
            label, email = last_name or "Student", line
            last_name = ""
        else:
            last_name = line
            continue
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
    teachers = data.get("teachers") or {}
    for username, block in teachers.items():
        sb.insert("app_settings", {
            "key": "timetable:" + username.strip().lower(), "value": block,
        }, upsert_on="key")
    print("Migrated {} teacher timetable(s).".format(len(teachers)))


def migrate_app_settings():
    """Move singleton JSON settings to durable storage."""
    for filename, key, default in (
            ("schools.json", "schools", {"schools": []}),
            ("announcement.json", "announcement",
             {"items": [], "message": "", "at": ""})):
        path = os.path.join(ROOT, filename)
        try:
            with open(path, encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError:
            value = default
        sb.insert("app_settings", {"key": key, "value": value}, upsert_on="key")
    print("Migrated schools and announcement settings.")


def _lesson_owner_id():
    username = MIGRATION_OWNER.strip().lower()
    if not username:
        try:
            with open(os.path.join(ROOT, "users.json"), encoding="utf-8") as handle:
                usernames = list(json.load(handle))
        except (FileNotFoundError, ValueError):
            usernames = []
        if len(usernames) == 1:
            username = usernames[0].strip().lower()
    if not username:
        return None
    rows = sb.select("profiles", params={"select": "id", "username": "eq." + username})
    return rows[0].get("id") if rows else None


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


def sync_bank_and_lessons():
    """SAFE-to-rerun catch-up sync (for the Supabase cutover): push any local
    questions/lessons that are not in Supabase yet, without ever duplicating.

    - soalan: INSERT ... ON CONFLICT (hash) DO NOTHING
    - lessons: skipped if a Supabase row already has the same (created_at, title)
    """
    db_file = os.path.join(ROOT, "bank_soalan.db")
    if not os.path.isfile(db_file):
        print("No local bank_soalan.db -- nothing to sync.")
        return
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row

    # --- questions: dedup handled by the hash column ---
    rows = conn.execute("SELECT * FROM soalan").fetchall()
    added_q = 0
    batch = []
    for r in rows:
        d = dict(r)
        d["pilihan"] = json.loads(d["pilihan"])
        d["tarikh_cipta"] = _iso_or_none(d.get("tarikh_cipta"))
        d["tarikh_akhir_guna"] = _iso_or_none(d.get("tarikh_akhir_guna"))
        d.pop("id", None)
        batch.append(d)
    for i in range(0, len(batch), 200):
        added_q += len(sb.insert("soalan", batch[i:i + 200], ignore_on="hash") or [])
    print("Questions: {} local, {} were new -> pushed.".format(len(batch), added_q))

    # --- lessons: dedup by (created_at, title) since there is no natural key ---
    owner_id = _lesson_owner_id()
    if not owner_id:
        conn.close()
        print("Lessons skipped: use --owner USERNAME after that Supabase account exists.")
        return
    existing = sb.select("lessons", params={"select": "created_at,title",
                                            "limit": "100000"})
    seen = {((e.get("created_at") or "")[:19], e.get("title") or "") for e in existing}
    lrows = conn.execute("SELECT * FROM lessons").fetchall()
    conn.close()
    added_l = 0
    for r in lrows:
        d = dict(r)
        key = ((d.get("created_at") or "")[:19], d.get("title") or "")
        if key in seen:
            continue
        d.pop("id", None)
        d["owner"] = owner_id
        for k in ("plan_json", "worksheet_json", "inputs_json"):
            d[k] = json.loads(d[k]) if d.get(k) else None
        sb.insert("lessons", d)
        added_l += 1
    print("Lessons: {} local, {} were new -> pushed.".format(len(lrows), added_l))


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
    owner_id = _lesson_owner_id()
    if not owner_id:
        print("Lessons skipped: use --owner USERNAME after that Supabase account exists.")
        return
    batch = []
    for r in rows:
        d = dict(r)
        d.pop("id", None)
        d["owner"] = owner_id
        for key in ("plan_json", "worksheet_json", "inputs_json"):
            d[key] = json.loads(d[key]) if d.get(key) else None
        batch.append(d)
    for i in range(0, len(batch), 100):
        sb.insert("lessons", batch[i:i + 100])
    print("Migrated {} lessons.".format(len(batch)))


def main():
    global MIGRATION_OWNER
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify the Supabase connection only")
    ap.add_argument("--users", action="store_true", help="create teacher accounts in Supabase Auth")
    ap.add_argument("--data", action="store_true", help="push bank/lessons/classrooms/students/timetable")
    ap.add_argument("--all", action="store_true", help="--users + --data")
    ap.add_argument("--sync", action="store_true",
                    help="catch-up sync: push local questions/lessons missing in "
                         "Supabase (safe to re-run, never duplicates)")
    ap.add_argument("--timetable", action="store_true",
                    help="upsert every teacher timetable into app_settings")
    ap.add_argument("--owner", default="",
                    help="Supabase username that owns migrated local lessons")
    args = ap.parse_args()
    MIGRATION_OWNER = args.owner

    if not any([args.check, args.users, args.data, args.all, args.sync, args.timetable]):
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
        migrate_app_settings()
        migrate_question_bank()
        migrate_lessons()
    if args.sync:
        sync_bank_and_lessons()
    if args.timetable and not (args.data or args.all):
        migrate_timetable()
    print("\nDone.")


if __name__ == "__main__":
    main()
