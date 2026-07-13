#!/usr/bin/env python3
"""
Lesson Library — stores approved lesson plans + worksheets so the teacher can
search, reopen, re-download, duplicate and delete past lessons.

Uses the SAME SQLite file as the Question Bank (bank_soalan.db) but a separate
`lessons` table — so the existing daily backup already covers it. Stdlib only.
"""

import json
import os
import sqlite3
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(ROOT, "bank_soalan.db")  # one project database, separate table


def _conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
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


def save_lesson(rec):
    """Save one lesson (plan + worksheet + the Agent-1 inputs). Returns new id."""
    init_db()
    plan = rec.get("plan") or {}
    ws = rec.get("worksheet") or {}
    inputs = rec.get("inputs") or {}
    title = plan.get("tajuk") or plan.get("tema_bidang") or ws.get("tajuk") or "Lesson"
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO lessons
               (created_at, title, kelas, tarikh, minggu, theme, topic, skill,
                plan_json, worksheet_json, inputs_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now, title,
                plan.get("tingkatan_kelas") or inputs.get("nama_kelas", ""),
                plan.get("tarikh") or inputs.get("tarikh", ""),
                plan.get("minggu") or inputs.get("minggu", ""),
                plan.get("tema_bidang") or inputs.get("theme", ""),
                plan.get("tajuk") or inputs.get("topic", ""),
                plan.get("mata_pelajaran", ""),
                json.dumps(plan, ensure_ascii=False),
                json.dumps(ws, ensure_ascii=False),
                json.dumps(inputs, ensure_ascii=False),
            ),
        )
        return cur.lastrowid


def list_lessons(q=""):
    """Return lesson summaries (no heavy JSON), newest first; optional text filter."""
    init_db()
    q = (q or "").strip()
    sql = "SELECT id, created_at, title, kelas, tarikh, minggu, theme, topic, skill FROM lessons"
    params = []
    if q:
        like = "%" + q + "%"
        sql += (" WHERE title LIKE ? OR kelas LIKE ? OR tarikh LIKE ? OR theme LIKE ?"
                " OR topic LIKE ? OR skill LIKE ?")
        params = [like] * 6
    sql += " ORDER BY id DESC LIMIT 500"
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def get_lesson(lesson_id):
    """Return one full lesson (plan + worksheet + inputs parsed)."""
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
        "plan": json.loads(r["plan_json"] or "{}"),
        "worksheet": json.loads(r["worksheet_json"] or "{}"),
        "inputs": json.loads(r["inputs_json"] or "{}"),
    }


def delete_lesson(lesson_id):
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
    return {"deleted": True, "id": lesson_id}


def update_reflection(lesson_id, refleksi, score=None):
    """Write the reflection into a saved lesson; optionally record the class score (%)."""
    init_db()
    try:
        score_val = float(str(score).replace("%", "").strip()) if score not in (None, "") else None
    except (ValueError, TypeError):
        score_val = None
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


def progress():
    """Lessons that have a recorded score, oldest first — for the progress dashboard."""
    init_db()
    with _conn() as c:
        rows = c.execute(
            """SELECT kelas, tarikh, title, score, created_at FROM lessons
               WHERE score IS NOT NULL ORDER BY tarikh ASC, id ASC"""
        ).fetchall()
    return [dict(r) for r in rows]
