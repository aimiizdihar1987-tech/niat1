#!/usr/bin/env python3
"""
Bank Soalan — storan soalan worksheet yang diluluskan guru (Agent 0 / Memori).

DUA backend, fungsi awam sama:
  - Supabase (jadual `soalan`) — digunakan bila supabase_config.txt / env var
    diisi. Ini yang KEKAL di cloud (Cloud Run storan sementara sahaja).
  - SQLite (bank_soalan.db) — fallback lokal bila Supabase tiada / NIAT_STORAGE=local.

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
import random
import re
import sqlite3
from datetime import datetime

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(ROOT, "bank_soalan.db")

ARAS_SAH = ("LOTS", "MOTS", "HOTS")


def _conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Cipta jadual SQLite jika belum wujud. Selamat dipanggil berulang kali.
    (Dalam mod Supabase, jadual dicipta oleh supabase/schema.sql — tiada apa
    perlu dibuat di sini.)"""
    if sb.use_cloud():
        return
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
    """Tukar baris pangkalan data → objek soalan (format Agent 3).
    `pilihan` mungkin string JSON (SQLite) atau list sedia (Supabase jsonb)."""
    pilihan = r["pilihan"]
    if isinstance(pilihan, str):
        try:
            pilihan = json.loads(pilihan)
        except (ValueError, TypeError):
            pilihan = []
    return {
        "id": r["id"],
        "sp_rujukan": r["sp_kod"],
        "aras": r["aras"],
        "soalan": r["soalan"],
        "pilihan": pilihan or [],
        "jawapan_betul": r["jawapan_betul"],
        "markah": r["markah"],
        "maklum_balas": r["maklum_balas"],
        "_dari_bank": True,
    }


def _clean_filter_text(q):
    """Buang aksara yang istimewa dalam sintaks penapis PostgREST or=(...)."""
    return re.sub(r"[,()\\*]", " ", q or "").strip()


# ==========================================================================
# add_questions
# ==========================================================================
def add_questions(questions, status="diluluskan", topic="", theme=""):
    """Tambah soalan ke bank (dengan topik/tema lesson asal supaya penggunaan
    semula hanya berlaku untuk topik yang sama). Duplikasi (hash) diabaikan."""
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for q in questions or []:
        sp = q.get("sp_rujukan") or q.get("sp_kod") or ""
        soalan = (q.get("soalan") or "").strip()
        if not soalan or not sp:
            continue
        rows.append({
            "sp_kod": sp,
            "aras": _norm_aras(q.get("aras")),
            "soalan": soalan,
            "pilihan": q.get("pilihan", []),
            "jawapan_betul": q.get("jawapan_betul", ""),
            "maklum_balas": q.get("maklum_balas", ""),
            "markah": int(q.get("markah", 1) or 1),
            "hash": _hash(soalan),
            "status": status,
            "tarikh_cipta": now,
            "topic": (topic or "").strip(),
            "theme": (theme or "").strip(),
        })
    if not rows:
        return 0

    if sb.use_cloud():
        # ON CONFLICT (hash) DO NOTHING — respons hanya baris yang benar-benar masuk.
        inserted = sb.insert("soalan", rows, ignore_on="hash") or []
        return len(inserted)

    init_db()
    ditambah = 0
    with _conn() as c:
        for r in rows:
            try:
                c.execute(
                    """INSERT INTO soalan
                       (sp_kod, aras, soalan, pilihan, jawapan_betul, maklum_balas,
                        markah, hash, status, tarikh_cipta, topic, theme)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        r["sp_kod"], r["aras"], r["soalan"],
                        json.dumps(r["pilihan"], ensure_ascii=False),
                        r["jawapan_betul"], r["maklum_balas"], r["markah"],
                        r["hash"], r["status"], r["tarikh_cipta"],
                        r["topic"], r["theme"],
                    ),
                )
                ditambah += 1
            except sqlite3.IntegrityError:
                pass  # duplikat — abaikan
    return ditambah


# ==========================================================================
# fetch_for_generation
# ==========================================================================
def fetch_for_generation(sp_kods, per_aras, topic=""):
    """Ambil soalan diluluskan untuk SP yang dipilih, mengikut sasaran setiap aras.

    PENTING: hanya soalan dengan TOPIK YANG SAMA diguna semula — soalan
    'Food, Food, Food!' tidak akan muncul dalam lesson 'Future Homes'
    walaupun Learning Standard-nya sama. Soalan lama tanpa topik direkod
    tidak diguna semula.
    Pilih yang PALING JARANG diguna dahulu (putar soalan; elak berulang).
    """
    topic = (topic or "").strip()
    if not sp_kods or not topic:
        return []
    hasil = []

    if sb.use_cloud():
        in_list = "in.({})".format(",".join('"{}"'.format(k.replace('"', "")) for k in sp_kods))
        for aras, mahu in per_aras.items():
            if not mahu or mahu <= 0:
                continue
            # ilike tanpa wildcard = padanan penuh tak sensitif huruf (macam
            # LOWER(topic) = LOWER(?) dalam versi SQLite).
            rows = sb.select("soalan", params={
                "select": "*",
                "status": "eq.diluluskan",
                "aras": "eq." + aras,
                "sp_kod": in_list,
                "topic": "ilike." + topic.replace("*", " "),
                "order": "kali_diguna.asc",
                "limit": str(max(int(mahu) * 4, 12)),
            })
            # ORDER BY kali_diguna ASC, RANDOM(): kocok dalam Python sebagai
            # pemutus seri rawak, kemudian ambil bilangan yang diminta.
            rows.sort(key=lambda r: (r.get("kali_diguna") or 0, random.random()))
            hasil.extend(_row_to_q(r) for r in rows[: int(mahu)])
        return hasil

    init_db()
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


# ==========================================================================
# mark_used
# ==========================================================================
def mark_used(ids):
    """Tambah kiraan guna untuk soalan yang benar-benar diluluskan dalam worksheet."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        return
    now = datetime.now().isoformat(timespec="seconds")

    if sb.use_cloud():
        # PostgREST tiada "SET x = x + 1" — baca nilai semasa, kemudian PATCH satu-satu.
        rows = sb.select("soalan", params={
            "select": "id,kali_diguna",
            "id": "in.({})".format(",".join(str(int(i)) for i in ids)),
        })
        for r in rows:
            sb.update("soalan", {"id": "eq.{}".format(r["id"])},
                      {"kali_diguna": (r.get("kali_diguna") or 0) + 1,
                       "tarikh_akhir_guna": now})
        return

    with _conn() as c:
        c.executemany(
            "UPDATE soalan SET kali_diguna = kali_diguna + 1, tarikh_akhir_guna=? WHERE id=?",
            [(now, i) for i in ids],
        )


# ==========================================================================
# list_questions (admin browse)
# ==========================================================================
def list_questions(q="", limit=300):
    """Admin browse: return question rows (newest first), optional text filter."""
    q = (q or "").strip()
    cols = ("id", "sp_kod", "aras", "soalan", "jawapan_betul", "markah",
            "topic", "theme", "kali_diguna", "status")

    if sb.use_cloud():
        params = {"select": ",".join(cols), "order": "id.desc", "limit": str(int(limit))}
        if q:
            safe = _clean_filter_text(q)
            if safe:
                pat = "ilike.*{}*".format(safe)
                params["or"] = "({})".format(",".join(
                    "{}.{}".format(col, pat) for col in ("soalan", "sp_kod", "topic", "theme")))
        return sb.select("soalan", params=params)

    init_db()
    sql = "SELECT {} FROM soalan".format(", ".join(cols))
    params = []
    if q:
        like = "%" + q + "%"
        sql += " WHERE soalan LIKE ? OR sp_kod LIKE ? OR topic LIKE ? OR theme LIKE ?"
        params = [like] * 4
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


# ==========================================================================
# delete_question (admin)
# ==========================================================================
def delete_question(qid):
    """Admin remove one question from the bank by id."""
    qid = int(qid)
    if sb.use_cloud():
        sb.delete("soalan", {"id": "eq.{}".format(qid)})
        return {"deleted": True, "id": qid}
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM soalan WHERE id=?", (qid,))
    return {"deleted": True, "id": qid}


# ==========================================================================
# stats
# ==========================================================================
def stats():
    """Ringkasan bank untuk dipaparkan: jumlah + pecahan ikut SP & aras."""
    if sb.use_cloud():
        rows = sb.select("soalan", params={
            "select": "sp_kod,aras",
            "status": "eq.diluluskan",
            "limit": "100000",
        })
        ikut_sp, ikut_aras = {}, {}
        for r in rows:
            ikut_sp[r["sp_kod"]] = ikut_sp.get(r["sp_kod"], 0) + 1
            ikut_aras[r["aras"]] = ikut_aras.get(r["aras"], 0) + 1
        return {
            "jumlah": len(rows),
            "ikut_sp": dict(sorted(ikut_sp.items())),
            "ikut_aras": ikut_aras,
        }

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
