#!/usr/bin/env python3
"""
Lesson Library — stores approved lesson plans + worksheets so the teacher can
search, reopen, re-download, duplicate and delete past lessons.

TWO backends behind the same public functions:
  - Supabase (`lessons` table) — used whenever credentials are configured;
    this is what survives on Cloud Run (container storage is ephemeral).
  - SQLite — local fallback: the SAME file as the Question Bank
    (bank_soalan.db) but a separate `lessons` table, so the existing daily
    backup already covers it. Stdlib only.
"""

import json
import os
import sqlite3
from datetime import datetime

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(ROOT, "bank_soalan.db")  # one project database, separate table


def _conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if sb.use_cloud():
        return  # table lives in Supabase (supabase/schema.sql)
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    TEXT,
                title         TEXT,
                kelas         TEXT,
                tarikh        TEXT,
                minggu        TEXT,
                theme         TEXT,
                topic         TEXT,
                skill         TEXT,
                plan_json     TEXT,
                worksheet_json TEXT,
                inputs_json   TEXT,
                score         REAL
            )
            """
        )
        # Migration: add the score column to older databases that lack it.
        cols = [r[1] for r in c.execute("PRAGMA table_info(lessons)").fetchall()]
        if "score" not in cols:
            c.execute("ALTER TABLE lessons ADD COLUMN score REAL")


def _local_iso(ts):
    """Supabase returns UTC timestamps ('...+00:00'); show them in local time
    with the same 'YYYY-MM-DDTHH:MM:SS' shape the SQLite version stored."""
    if not ts:
        return ts
    try:
        return (datetime.fromisoformat(ts.replace("Z", "+00:00"))
                .astimezone().isoformat(timespec="seconds")[:19])
    except (ValueError, TypeError):
        return ts


def _as_obj(v):
    """jsonb comes back as dict already; SQLite stores a JSON string."""
    if isinstance(v, str):
        return json.loads(v or "{}")
    return v or {}


def _owner_id(username):
    """Resolve a signed-in Niat username to its Supabase Auth UUID."""
    username = (username or "").strip().lower()
    if not username:
        return None
    rows = sb.select("profiles", params={"select": "id", "username": "eq." + username})
    return rows[0].get("id") if rows else None


def save_lesson(rec, owner_username=None):
    """Save one lesson (plan + worksheet + the Agent-1 inputs). Returns new id."""
    plan = rec.get("plan") or {}
    ws = rec.get("worksheet") or {}
    inputs = rec.get("inputs") or {}
    title = plan.get("tajuk") or plan.get("tema_bidang") or ws.get("tajuk") or "Lesson"
    fields = {
        "title": title,
        "kelas": plan.get("tingkatan_kelas") or inputs.get("nama_kelas", ""),
        "tarikh": plan.get("tarikh") or inputs.get("tarikh", ""),
        "minggu": plan.get("minggu") or inputs.get("minggu", ""),
        "theme": plan.get("tema_bidang") or inputs.get("theme", ""),
        "topic": plan.get("tajuk") or inputs.get("topic", ""),
        "skill": plan.get("mata_pelajaran", ""),
    }

    if sb.use_cloud():
        owner = _owner_id(owner_username)
        if not owner:
            raise sb.SupabaseError("Cannot save lesson: signed-in owner profile was not found.")
        row = dict(fields)
        row["owner"] = owner
        row["created_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        row["plan_json"] = plan
        row["worksheet_json"] = ws
        row["inputs_json"] = inputs
        inserted = sb.insert("lessons", row)
        return inserted[0]["id"]

    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO lessons
               (created_at, title, kelas, tarikh, minggu, theme, topic, skill,
                plan_json, worksheet_json, inputs_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now, fields["title"], fields["kelas"], fields["tarikh"],
                fields["minggu"], fields["theme"], fields["topic"], fields["skill"],
                json.dumps(plan, ensure_ascii=False),
                json.dumps(ws, ensure_ascii=False),
                json.dumps(inputs, ensure_ascii=False),
            ),
        )
        return cur.lastrowid


def list_lessons(q="", owner_username=None):
    """Return lesson summaries (no heavy JSON), newest first; optional text filter."""
    q = (q or "").strip()
    cols = ("id", "created_at", "title", "kelas", "tarikh", "minggu",
            "theme", "topic", "skill")

    if sb.use_cloud():
        params = {"select": ",".join(cols), "order": "id.desc", "limit": "500"}
        if owner_username is not None:
            owner = _owner_id(owner_username)
            if not owner:
                return []
            params["owner"] = "eq." + owner
        if q:
            import re as _re
            safe = _re.sub(r"[,()\\*]", " ", q).strip()
            if safe:
                pat = "ilike.*{}*".format(safe)
                params["or"] = "({})".format(",".join(
                    "{}.{}".format(col, pat)
                    for col in ("title", "kelas", "tarikh", "theme", "topic", "skill")))
        rows = sb.select("lessons", params=params)
        for r in rows:
            r["created_at"] = _local_iso(r.get("created_at"))
        return rows

    init_db()
    sql = "SELECT {} FROM lessons".format(", ".join(cols))
    params = []
    if q:
        like = "%" + q + "%"
        sql += (" WHERE title LIKE ? OR kelas LIKE ? OR tarikh LIKE ? OR theme LIKE ?"
                " OR topic LIKE ? OR skill LIKE ?")
        params = [like] * 6
    sql += " ORDER BY id DESC LIMIT 500"
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def get_lesson(lesson_id, owner_username=None):
    """Return one full lesson (plan + worksheet + inputs parsed)."""
    if sb.use_cloud():
        params = {"select": "*", "id": "eq.{}".format(int(lesson_id))}
        if owner_username is not None:
            owner = _owner_id(owner_username)
            if not owner:
                return None
            params["owner"] = "eq." + owner
        rows = sb.select("lessons", params=params)
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r["id"],
            "created_at": _local_iso(r.get("created_at")),
            "title": r.get("title"),
            "kelas": r.get("kelas"),
            "tarikh": r.get("tarikh"),
            "plan": _as_obj(r.get("plan_json")),
            "worksheet": _as_obj(r.get("worksheet_json")),
            "inputs": _as_obj(r.get("inputs_json")),
        }

    init_db()
    with _conn() as c:
        r = c.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "title": r["title"],
        "kelas": r["kelas"],
        "tarikh": r["tarikh"],
        "plan": _as_obj(r["plan_json"]),
        "worksheet": _as_obj(r["worksheet_json"]),
        "inputs": _as_obj(r["inputs_json"]),
    }


def delete_lesson(lesson_id, owner_username=None):
    if sb.use_cloud():
        match = {"id": "eq.{}".format(int(lesson_id))}
        if owner_username is not None:
            owner = _owner_id(owner_username)
            if not owner:
                return {"deleted": False, "id": lesson_id}
            match["owner"] = "eq." + owner
        sb.delete("lessons", match)
        return {"deleted": True, "id": lesson_id}
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
    return {"deleted": True, "id": lesson_id}


def update_reflection(lesson_id, refleksi, score=None, owner_username=None):
    """Write the reflection into a saved lesson; optionally record the class score (%)."""
    try:
        score_val = float(str(score).replace("%", "").strip()) if score not in (None, "") else None
    except (ValueError, TypeError):
        score_val = None

    if sb.use_cloud():
        match = {"id": "eq.{}".format(int(lesson_id))}
        if owner_username is not None:
            owner = _owner_id(owner_username)
            if not owner:
                return {"ok": False, "id": lesson_id}
            match["owner"] = "eq." + owner
        params = dict(match)
        params["select"] = "plan_json"
        rows = sb.select("lessons", params=params)
        if not rows:
            return {"ok": False, "id": lesson_id}
        plan = _as_obj(rows[0].get("plan_json"))
        plan["refleksi"] = refleksi
        patch = {"plan_json": plan}
        if score_val is not None:
            patch["score"] = score_val
        sb.update("lessons", match, patch)
        return {"ok": True, "id": lesson_id, "score": score_val}

    init_db()
    with _conn() as c:
        r = c.execute("SELECT plan_json FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not r:
            return {"ok": False, "id": lesson_id}
        plan = json.loads(r["plan_json"] or "{}")
        plan["refleksi"] = refleksi
        if score_val is not None:
            c.execute("UPDATE lessons SET plan_json=?, score=? WHERE id=?",
                      (json.dumps(plan, ensure_ascii=False), score_val, lesson_id))
        else:
            c.execute("UPDATE lessons SET plan_json=? WHERE id=?",
                      (json.dumps(plan, ensure_ascii=False), lesson_id))
    return {"ok": True, "id": lesson_id, "score": score_val}


def progress(owner_username=None):
    """Lessons that have a recorded score, oldest first — for the progress dashboard."""
    if sb.use_cloud():
        params = {
            "select": "kelas,tarikh,title,score,created_at",
            "score": "not.is.null",
            "order": "tarikh.asc,id.asc",
        }
        if owner_username is not None:
            owner = _owner_id(owner_username)
            if not owner:
                return []
            params["owner"] = "eq." + owner
        rows = sb.select("lessons", params=params)
        for r in rows:
            r["created_at"] = _local_iso(r.get("created_at"))
        return rows

    init_db()
    with _conn() as c:
        rows = c.execute(
            """SELECT kelas, tarikh, title, score, created_at FROM lessons
               WHERE score IS NOT NULL ORDER BY tarikh ASC, id ASC"""
        ).fetchall()
    return [dict(r) for r in rows]
