#!/usr/bin/env python3
"""
Guardrail — the Curriculum Guardrail / Validator Agent (Python stdlib only).

Sits between the generator agents and the teacher: every RPH and worksheet is
checked (and auto-repaired where safe) BEFORE it is shown. Rules enforced:

Worksheet:
  - every question has non-empty text and EXACTLY 4 options
  - jawapan_betul is a single letter A-D that points at a real option
  - aras is one of LOTS/MOTS/HOTS (else normalised to MOTS)
  - sp_rujukan is one of the Learning Standards the teacher selected
    (else re-tagged to the first selected code)
  - no duplicate questions (normalised-text hash)
  - numbering and mark totals are recomputed

RPH:
  - all mandatory JPN Perlis fields exist; context fields (tarikh, kelas, masa,
    tema, tajuk...) are backfilled from the teacher's inputs when missing
  - list fields (objektif/aktiviti/standard_pembelajaran) are real lists
  - refleksi is forced to "" (teacher fills it after the lesson)

Each check returns (fixed_artifact, report) where report = {"ok": bool,
"repairs": [...], "dropped": [...]} — repairs are silent fixes, dropped items
could not be safely repaired and were removed.
"""

import re

ARAS_SAH = ("LOTS", "MOTS", "HOTS")
LETTERS = ("A", "B", "C", "D")

RPH_TEXT_FIELDS = (
    "minggu", "tarikh", "hari", "masa", "tingkatan_kelas",
    "minimum_jam_setahun", "mata_pelajaran", "tema_bidang", "tajuk",
    "standard_kandungan",
)
RPH_LIST_FIELDS = ("standard_pembelajaran", "objektif_pembelajaran", "aktiviti_pembelajaran")


def _norm_text(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# --------------------------------------------------------------------------
# Worksheet
# --------------------------------------------------------------------------
def check_worksheet(worksheet, sp_kods):
    """Validate + repair a worksheet dict in place. Returns (worksheet, report)."""
    repairs, dropped = [], []
    if not isinstance(worksheet, dict):
        return worksheet, {"ok": False, "repairs": [], "dropped": ["worksheet is not an object"]}

    valid_sp = [k for k in (sp_kods or []) if k]
    seen = set()
    kept = []

    for q in worksheet.get("soalan", []) or []:
        if not isinstance(q, dict):
            dropped.append("non-object question removed")
            continue
        no = q.get("no", "?")
        text = (q.get("soalan") or "").strip()
        if not text:
            dropped.append("Q{}: empty question text".format(no))
            continue

        # duplicates
        h = _norm_text(text)
        if h in seen:
            dropped.append("Q{}: duplicate question".format(no))
            continue
        seen.add(h)

        # options: exactly 4 non-empty strings
        pilihan = [str(p).strip() for p in (q.get("pilihan") or []) if str(p).strip()]

        # smaller local models often prefix options with their letter ("A. glad")
        # — strip the prefixes when most options carry them.
        prefixed = sum(1 for p in pilihan if re.match(r"^\(?[A-Ea-e][\.\):]\s*", p))
        if pilihan and prefixed >= len(pilihan) - 1 and prefixed >= 3:
            pilihan = [re.sub(r"^\(?[A-Ea-e][\.\):]\s*", "", p).strip() for p in pilihan]
            repairs.append("Q{}: letter prefixes stripped from options".format(no))

        # too many options: trim, but only if the correct answer survives the cut
        ans0 = str(q.get("jawapan_betul") or "").strip().upper()
        if len(pilihan) > 4:
            if ans0 in LETTERS:  # A-D index < 4 → safe to keep the first four
                pilihan = pilihan[:4]
                repairs.append("Q{}: extra options trimmed to 4".format(no))
            else:
                dropped.append("Q{}: has {} options and answer '{}' outside A-D".format(
                    no, len(pilihan), ans0[:10]))
                continue
        if len(pilihan) != 4:
            dropped.append("Q{}: has {} options (needs exactly 4)".format(no, len(pilihan)))
            continue
        if len({_norm_text(p) for p in pilihan}) != 4:
            dropped.append("Q{}: options are not all different".format(no))
            continue
        q["pilihan"] = pilihan

        # correct answer: single letter A-D
        ans = str(q.get("jawapan_betul") or "").strip().upper()
        if ans not in LETTERS:
            # sometimes the model returns the option text instead of the letter
            match = next((LETTERS[i] for i, p in enumerate(pilihan)
                          if _norm_text(p) == _norm_text(ans)), None)
            if match:
                q["jawapan_betul"] = match
                repairs.append("Q{}: answer text converted to letter {}".format(no, match))
            else:
                dropped.append("Q{}: correct answer '{}' is not A-D".format(no, ans[:20]))
                continue
        else:
            q["jawapan_betul"] = ans

        # cognitive level
        aras = (q.get("aras") or "").strip().upper()
        if aras not in ARAS_SAH:
            q["aras"] = "MOTS"
            repairs.append("Q{}: level '{}' normalised to MOTS".format(no, aras or "?"))

        # learning-standard tag must be one the teacher selected
        sp = (q.get("sp_rujukan") or "").strip()
        if valid_sp and sp not in valid_sp:
            q["sp_rujukan"] = valid_sp[0]
            repairs.append("Q{}: standard '{}' re-tagged to {}".format(no, sp or "?", valid_sp[0]))

        # marks
        try:
            q["markah"] = max(1, int(q.get("markah", 1) or 1))
        except (TypeError, ValueError):
            q["markah"] = 1
            repairs.append("Q{}: invalid mark reset to 1".format(no))

        kept.append(q)

    # renumber + recompute totals
    for i, q in enumerate(kept, 1):
        q["no"] = i
    worksheet["soalan"] = kept
    worksheet["jumlah_soalan"] = len(kept)
    worksheet["jumlah_markah"] = sum(q["markah"] for q in kept)

    ok = len(kept) > 0
    if not ok:
        dropped.append("no valid questions survived validation")
    return worksheet, {"ok": ok, "repairs": repairs, "dropped": dropped}


# --------------------------------------------------------------------------
# RPH (Daily Lesson Plan)
# --------------------------------------------------------------------------
def check_rph(rph, inputs, cur):
    """Validate + backfill an RPH dict. Returns (rph, report)."""
    repairs, dropped = [], []
    if not isinstance(rph, dict):
        return rph, {"ok": False, "repairs": [], "dropped": ["rph is not an object"]}

    inputs = inputs or {}
    backfill = {
        "minggu": inputs.get("minggu", ""),
        "tarikh": inputs.get("tarikh", ""),
        "hari": inputs.get("hari", ""),
        "masa": inputs.get("masa", ""),
        "tingkatan_kelas": inputs.get("nama_kelas", ""),
        "minimum_jam_setahun": "144",
        "mata_pelajaran": "Bahasa Inggeris",
        "tema_bidang": inputs.get("theme", ""),
        "tajuk": inputs.get("topic", ""),
        "standard_kandungan": (
            "{} {}".format(cur["sk"]["kod"], cur["sk"]["nama"])
            if cur and cur.get("sk") else ""
        ),
    }
    for f in RPH_TEXT_FIELDS:
        val = str(rph.get(f) or "").strip()
        if not val and backfill.get(f):
            rph[f] = backfill[f]
            repairs.append("field '{}' backfilled from context".format(f))
        elif not val:
            dropped.append("field '{}' is empty and could not be backfilled".format(f))
        else:
            rph[f] = val

    # mata_pelajaran must be the fixed template value
    if rph.get("mata_pelajaran") != "Bahasa Inggeris":
        rph["mata_pelajaran"] = "Bahasa Inggeris"
        repairs.append("mata_pelajaran fixed to 'Bahasa Inggeris'")

    # list fields
    sp_fallback = (
        ["{} {}".format(s["kod"], s["huraian"]) for s in (cur.get("sp") or [])]
        if cur else []
    )
    for f in RPH_LIST_FIELDS:
        v = rph.get(f)
        if isinstance(v, str):
            rph[f] = [x.strip() for x in v.split("\n") if x.strip()]
            repairs.append("field '{}' converted from text to list".format(f))
        elif not isinstance(v, list):
            rph[f] = []
        rph[f] = [str(x).strip() for x in rph[f] if str(x).strip()]
        if not rph[f]:
            if f == "standard_pembelajaran" and sp_fallback:
                rph[f] = sp_fallback
                repairs.append("standard_pembelajaran backfilled from selection")
            else:
                dropped.append("list field '{}' is empty".format(f))

    # refleksi is completed by the teacher, never the model
    if rph.get("refleksi"):
        rph["refleksi"] = ""
        repairs.append("refleksi cleared (teacher fills after the lesson)")
    else:
        rph["refleksi"] = ""

    ok = not dropped
    return rph, {"ok": ok, "repairs": repairs, "dropped": dropped}
