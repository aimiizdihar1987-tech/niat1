#!/usr/bin/env python3
"""
Bank Soalan — storan soalan worksheet yang diluluskan guru (Agent 0 / Memori).

Guna SQLite (modul `sqlite3` — sebahagian Python stdlib, jadi TIADA pip install).
Satu fail pangkalan data: bank_soalan.db di folder projek.

Peranan dalam sistem:
  - Apabila guru tekan "Setuju" pada worksheet, soalan disimpan ke sini
    (status 'diluluskan'). Soalan yang ditolak / draf TIDAK masuk.
  - Semasa Agent 3 menjana worksheet baharu (mod "bank dahulu"), soalan
    diluluskan untuk SP yang sama diambil dahulu; AI cuma menampung baki.
  - Setiap teks soalan dicapjari (hash) supaya tiada duplikasi.
  - Menyimpan statistik guna (kali_diguna) untuk memutar soalan & elak berulang.
"""

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(ROOT, "bank_soalan.db")

ARAS_SAH = ("LOTS", "MOTS", "HOTS")


def _conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Cipta jadual jika belum wujud. Selamat dipanggil berulang kali."""
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS soalan (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                sp_kod            TEXT NOT NULL,
                aras              TEXT NOT NULL,
                soalan            TEXT NOT NULL,
                pilihan           TEXT NOT NULL,          -- JSON array A-D
                jawapan_betul     TEXT NOT NULL,
                maklum_balas      TEXT DEFAULT '',
                markah            INTEGER DEFAULT 1,
                hash              TEXT UNIQUE NOT NULL,    -- elak duplikasi
                status            TEXT DEFAULT 'diluluskan',
                kali_diguna       INTEGER DEFAULT 0,
                kadar_betul       REAL,                   -- diisi kelak oleh Agent 6/7
                tarikh_cipta      TEXT,
                tarikh_akhir_guna TEXT
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_sp_aras ON soalan(sp_kod, aras, status)")
        # Migrasi: kolum topik/tema (soalan hanya diguna semula untuk topik yang sama).
        for col in ("topic", "theme"):
            try:
                c.execute("ALTER TABLE soalan ADD COLUMN {} TEXT DEFAULT ''".format(col))
            except sqlite3.OperationalError:
                pass  # kolum sudah wujud


def _norm_aras(aras):
    a = (aras or "MOTS").strip().upper()
    return a if a in ARAS_SAH else "MOTS"


def _hash(soalan):
    """Cap jari teks soalan (dinormalkan) untuk mengesan duplikasi."""
    norm = re.sub(r"\s+", " ", (soalan or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _row_to_q(r):
    """Tukar baris pangkalan data → objek soalan (format Agent 3)."""
    try:
        pilihan = json.loads(r["pilihan"])
    except (ValueError, TypeError):
        pilihan = []
    return {
        "id": r["id"],
        "sp_rujukan": r["sp_kod"],
        "aras": r["aras"],
        "soalan": r["soalan"],
        "pilihan": pilihan,
        "jawapan_betul": r["jawapan_betul"],
        "markah": r["markah"],
        "maklum_balas": r["maklum_balas"],
        "_dari_bank": True,
    }


def add_questions(questions, status="diluluskan", topic="", theme=""):
    """Tambah soalan ke bank (dengan topik/tema lesson asal supaya penggunaan
    semula hanya berlaku untuk topik yang sama). Duplikasi (hash) diabaikan."""
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    ditambah = 0
    with _conn() as c:
        for q in questions or []:
            sp = q.get("sp_rujukan") or q.get("sp_kod") or ""
            soalan = (q.get("soalan") or "").strip()
            if not soalan or not sp:
                continue
            try:
                c.execute(
                    """INSERT INTO soalan
                       (sp_kod, aras, soalan, pilihan, jawapan_betul, maklum_balas,
                        markah, hash, status, tarikh_cipta, topic, theme)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        sp,
                        _norm_aras(q.get("aras")),
                        soalan,
                        json.dumps(q.get("pilihan", []), ensure_ascii=False),
                        q.get("jawapan_betul", ""),
                        q.get("maklum_balas", ""),
                        int(q.get("markah", 1) or 1),
                        _hash(soalan),
                        status,
                        now,
                        (topic or "").strip(),
                        (theme or "").strip(),
                    ),
                )
                ditambah += 1
            except sqlite3.IntegrityError:
                pass  # duplikat — abaikan
    return ditambah


def fetch_for_generation(sp_kods, per_aras, topic=""):
    """Ambil soalan diluluskan untuk SP yang dipilih, mengikut sasaran setiap aras.

    PENTING: hanya soalan dengan TOPIK YANG SAMA diguna semula — soalan
    'Food, Food, Food!' tidak akan muncul dalam lesson 'Future Homes'
    walaupun Learning Standard-nya sama. Soalan lama tanpa topik direkod
    tidak diguna semula.
    Pilih yang PALING JARANG diguna dahulu (putar soalan; elak berulang).
    """
    init_db()
    topic = (topic or "").strip()
    if not sp_kods or not topic:
        return []
    hasil = []
    ph = ",".join("?" * len(sp_kods))
    with _conn() as c:
        for aras, mahu in per_aras.items():
            if not mahu or mahu <= 0:
                continue
            rows = c.execute(
                """SELECT * FROM soalan
                   WHERE status='diluluskan' AND aras=? AND sp_kod IN (%s)
                     AND LOWER(COALESCE(topic,'')) = LOWER(?)
                   ORDER BY kali_diguna ASC, RANDOM()
                   LIMIT ?""" % ph,
                [aras, *sp_kods, topic, mahu],
            ).fetchall()
            hasil.extend(_row_to_q(r) for r in rows)
    return hasil


def mark_used(ids):
    """Tambah kiraan guna untuk soalan yang benar-benar diluluskan dalam worksheet."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        return
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as c:
        c.executemany(
            "UPDATE soalan SET kali_diguna = kali_diguna + 1, tarikh_akhir_guna=? WHERE id=?",
            [(now, i) for i in ids],
        )


def list_questions(q="", limit=300):
    """Admin browse: return question rows (newest first), optional text filter."""
    init_db()
    q = (q or "").strip()
    sql = ("SELECT id, sp_kod, aras, soalan, jawapan_betul, markah, topic, theme, "
           "kali_diguna, status FROM soalan")
    params = []
    if q:
        like = "%" + q + "%"
        sql += " WHERE soalan LIKE ? OR sp_kod LIKE ? OR topic LIKE ? OR theme LIKE ?"
        params = [like] * 4
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def delete_question(qid):
    """Admin remove one question from the bank by id."""
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM soalan WHERE id=?", (int(qid),))
    return {"deleted": True, "id": int(qid)}


def stats():
    """Ringkasan bank untuk dipaparkan: jumlah + pecahan ikut SP & aras."""
    init_db()
    with _conn() as c:
        jumlah = c.execute(
            "SELECT COUNT(*) FROM soalan WHERE status='diluluskan'"
        ).fetchone()[0]
        ikut_sp = c.execute(
            """SELECT sp_kod, COUNT(*) n FROM soalan
               WHERE status='diluluskan' GROUP BY sp_kod ORDER BY sp_kod"""
        ).fetchall()
        ikut_aras = c.execute(
            """SELECT aras, COUNT(*) n FROM soalan
               WHERE status='diluluskan' GROUP BY aras"""
        ).fetchall()
    return {
        "jumlah": jumlah,
        "ikut_sp": {r["sp_kod"]: r["n"] for r in ikut_sp},
        "ikut_aras": {r["aras"]: r["n"] for r in ikut_aras},
    }
