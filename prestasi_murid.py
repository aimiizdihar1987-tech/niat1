#!/usr/bin/env python3
"""
Prestasi Murid — cumulative per-student performance store (Agent 5 / Pembezaan).

Sumber isyarat untuk pembelajaran terbeza (differentiated learning): setiap kali
keputusan kuiz Google Form dibaca, markah setiap murid disimpan di sini. Agent 5
kemudian mengira purata terkumpul setiap murid merentas beberapa pelajaran untuk
memutuskan aras worksheet yang sesuai.

DUA backend, fungsi awam sama (ikut corak bank_soalan.py):
  - Supabase (jadual `prestasi_murid`) — bila supabase_config.txt / env var diisi.
  - SQLite (prestasi_murid.db) — fallback lokal bila Supabase tiada / NIAT_STORAGE=local.
"""

import os
import sqlite3
from datetime import datetime

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(ROOT, "prestasi_murid.db")

TABLE = "prestasi_murid"


# --------------------------------------------------------------------------
# SQLite (fallback tempatan)
# --------------------------------------------------------------------------
def _conn():
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    return c


def _init_sqlite():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS prestasi_murid (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                emel          TEXT NOT NULL,
                nama          TEXT,
                kelas         TEXT,
                peratus       REAL NOT NULL,   -- 0..100
                topik         TEXT,
                sp            TEXT,             -- learning standard code(s)
                lesson_id     TEXT,
                dicipta       TEXT NOT NULL
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_prestasi_emel ON prestasi_murid (emel)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_prestasi_kelas ON prestasi_murid (kelas)"
        )


# --------------------------------------------------------------------------
# Rekod markah
# --------------------------------------------------------------------------
def _normalise(per_student):
    """Terima senarai keputusan kuiz {email, percent | score/max, name?} →
    baris seragam {emel, nama, peratus}."""
    rows = []
    for s in per_student or []:
        emel = (s.get("email") or s.get("emel") or "").strip().lower()
        if "@" not in emel:
            continue
        peratus = s.get("percent")
        if peratus in (None, ""):
            try:
                score = float(s.get("score") or 0)
                mx = float(s.get("max") or 0)
                peratus = round(100.0 * score / mx, 1) if mx else None
            except (TypeError, ValueError):
                peratus = None
        if peratus in (None, ""):
            continue
        try:
            peratus = max(0.0, min(100.0, float(peratus)))
        except (TypeError, ValueError):
            continue
        rows.append({
            "emel": emel,
            "nama": (s.get("name") or s.get("nama") or "").strip(),
            "peratus": peratus,
        })
    return rows


def record_scores(class_name, per_student, topic="", sp="", lesson_id=""):
    """Simpan markah setiap murid daripada satu keputusan kuiz. Kembalikan
    bilangan baris yang disimpan."""
    rows = _normalise(per_student)
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    sp_txt = "; ".join(sp) if isinstance(sp, (list, tuple)) else (sp or "")

    if sb.use_cloud():
        payload = [{
            "emel": r["emel"], "nama": r["nama"], "kelas": class_name or "",
            "peratus": r["peratus"], "topik": topic or "", "sp": sp_txt,
            "lesson_id": str(lesson_id or ""), "dicipta": now,
        } for r in rows]
        sb.insert(TABLE, payload, role="service")
        return len(payload)

    _init_sqlite()
    with _conn() as c:
        for r in rows:
            c.execute(
                "INSERT INTO prestasi_murid "
                "(emel, nama, kelas, peratus, topik, sp, lesson_id, dicipta) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (r["emel"], r["nama"], class_name or "", r["peratus"],
                 topic or "", sp_txt, str(lesson_id or ""), now),
            )
    return len(rows)


# --------------------------------------------------------------------------
# Baca prestasi terkumpul
# --------------------------------------------------------------------------
def _fetch_rows(class_name):
    if sb.use_cloud():
        params = {"select": "emel,nama,peratus,topik,dicipta", "order": "dicipta.asc"}
        if class_name:
            params["kelas"] = "eq." + class_name
        return sb.select(TABLE, params=params, role="service") or []
    _init_sqlite()
    with _conn() as c:
        if class_name:
            cur = c.execute(
                "SELECT emel, nama, peratus, topik, dicipta FROM prestasi_murid "
                "WHERE kelas=? ORDER BY dicipta ASC", (class_name,))
        else:
            cur = c.execute(
                "SELECT emel, nama, peratus, topik, dicipta FROM prestasi_murid "
                "ORDER BY dicipta ASC")
        return [dict(r) for r in cur.fetchall()]


def cumulative_by_student(class_name, recent=5):
    """Purata terkumpul setiap murid dalam SATU kelas.

    Kembalikan senarai (disusun mengikut purata menaik — yang paling lemah dahulu):
      {emel, nama, purata, bil, terkini: [peratus...], trend}
    `terkini` = sehingga `recent` markah terakhir. `trend` = 'naik'/'turun'/'stabil'
    berdasarkan separuh awal vs separuh akhir sejarah.
    """
    rows = _fetch_rows(class_name)
    by_email = {}
    for r in rows:
        emel = (r.get("emel") or "").strip().lower()
        if not emel:
            continue
        try:
            p = float(r.get("peratus"))
        except (TypeError, ValueError):
            continue
        rec = by_email.setdefault(emel, {"emel": emel, "nama": "", "markah": []})
        if r.get("nama"):
            rec["nama"] = r["nama"]
        rec["markah"].append(p)

    out = []
    for rec in by_email.values():
        marks = rec["markah"]
        if not marks:
            continue
        purata = round(sum(marks) / len(marks), 1)
        trend = "stabil"
        if len(marks) >= 4:
            half = len(marks) // 2
            awal = sum(marks[:half]) / half
            akhir = sum(marks[half:]) / (len(marks) - half)
            if akhir - awal >= 8:
                trend = "naik"
            elif awal - akhir >= 8:
                trend = "turun"
        out.append({
            "emel": rec["emel"],
            "nama": rec["nama"] or rec["emel"].split("@")[0],
            "purata": purata,
            "bil": len(marks),
            "terkini": [round(m, 1) for m in marks[-recent:]],
            "trend": trend,
        })
    out.sort(key=lambda x: x["purata"])
    return out


def has_data(class_name=None):
    """True jika ada sebarang rekod prestasi (untuk kelas ini, jika diberi)."""
    return bool(cumulative_by_student(class_name)) if class_name else bool(_fetch_rows(""))
