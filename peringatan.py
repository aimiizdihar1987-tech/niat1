#!/usr/bin/env python3
"""
Peringatan — jejak eskalasi peringatan tugasan (Agent 6 / Reminder).

Setiap kali Agent 6 menghantar peringatan kepada seorang murid untuk satu
tugasan, kiraan (kali_diperingat) dinaikkan. Agent 6 membaca kiraan ini untuk
memutuskan nada & aras eskalasi (lembut → tegas → maklum cikgu) pada pusingan
berikutnya, supaya murid yang sama tidak dihantar mesej yang serupa berulang.

DUA backend, fungsi awam sama (ikut corak prestasi_murid.py):
  - Supabase (jadual `peringatan`) — bila supabase dikonfigur.
  - SQLite (peringatan.db) — fallback lokal.
"""

import os
import sqlite3
from datetime import datetime

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(ROOT, "peringatan.db")
TABLE = "peringatan"


def _conn():
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    return c


def _init_sqlite():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS peringatan (
                emel         TEXT NOT NULL,
                kelas        TEXT,
                tugasan      TEXT NOT NULL,
                kali         INTEGER NOT NULL DEFAULT 0,
                aras_akhir   TEXT,
                terakhir     TEXT,
                PRIMARY KEY (emel, tugasan)
            )
            """
        )


def _key(emel, tugasan):
    return (emel or "").strip().lower(), (tugasan or "").strip()


def counts_for(tugasan, emails):
    """Kembalikan {emel: kali_diperingat} untuk satu tugasan (0 jika belum pernah)."""
    tugasan = (tugasan or "").strip()
    out = {(e or "").strip().lower(): 0 for e in emails}
    if not out:
        return out
    if sb.use_cloud():
        rows = sb.select(TABLE, params={"select": "emel,kali", "tugasan": "eq." + tugasan},
                         role="service") or []
        for r in rows:
            e = (r.get("emel") or "").strip().lower()
            if e in out:
                out[e] = int(r.get("kali") or 0)
        return out
    _init_sqlite()
    with _conn() as c:
        cur = c.execute("SELECT emel, kali FROM peringatan WHERE tugasan=?", (tugasan,))
        for r in cur.fetchall():
            e = (r["emel"] or "").strip().lower()
            if e in out:
                out[e] = int(r["kali"] or 0)
    return out


def record(emel, kelas, tugasan, aras):
    """Naikkan kiraan peringatan untuk (murid, tugasan) selepas emel dihantar."""
    emel, tugasan = _key(emel, tugasan)
    now = datetime.now().isoformat(timespec="seconds")
    if sb.use_cloud():
        existing = sb.select(TABLE, params={
            "select": "kali", "emel": "eq." + emel, "tugasan": "eq." + tugasan},
            role="service") or []
        kali = (int(existing[0].get("kali") or 0) + 1) if existing else 1
        sb.insert(TABLE, [{"emel": emel, "kelas": kelas or "", "tugasan": tugasan,
                           "kali": kali, "aras_akhir": aras or "", "terakhir": now}],
                  role="service", upsert_on="emel,tugasan")
        return kali
    _init_sqlite()
    with _conn() as c:
        row = c.execute("SELECT kali FROM peringatan WHERE emel=? AND tugasan=?",
                        (emel, tugasan)).fetchone()
        kali = (int(row["kali"]) + 1) if row else 1
        c.execute(
            "INSERT INTO peringatan (emel, kelas, tugasan, kali, aras_akhir, terakhir) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(emel, tugasan) DO UPDATE SET "
            "kali=excluded.kali, aras_akhir=excluded.aras_akhir, terakhir=excluded.terakhir",
            (emel, kelas or "", tugasan, kali, aras or "", now))
    return kali
