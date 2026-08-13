#!/usr/bin/env python3
"""Validate + load the generated question-bank JSON files into the Niat bank.

Dry-run by default (validates + prints stats). Pass --insert to actually write
to the configured backend (Supabase in cloud mode) via bank_soalan.add_questions.
"""
import os, sys, json, glob, re

ROOT = r"C:/Users/HP/Desktop/PRESTIJ KAK AIMI"
BANKDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import bank_soalan as bank  # noqa: E402

FORM_OF = {"f1": 1, "f2": 2, "f3a": 3, "f3b": 3,
           "f4a": 4, "f4b": 4, "f5a": 5, "f5b": 5}
ARAS = {"LOTS", "MOTS", "HOTS"}
LETTERS = {"A", "B", "C", "D"}


def form_meta(form):
    d = json.load(open(os.path.join(ROOT, "dskp_english_f%d.json" % form), encoding="utf-8"))
    sp = set()
    for b in d["bidang"]:
        for sk in b["standard_kandungan"]:
            for s in sk["standard_pembelajaran"]:
                sp.add(s["kod"])
    units = set(d["textbook_units"])
    themes = set(d.get("themes", []))
    return sp, units, themes


def main():
    do_insert = "--insert" in sys.argv
    valid, invalid = [], []
    per_form = {}
    seen_text = set()
    meta_cache = {}
    for path in sorted(glob.glob(os.path.join(BANKDIR, "bank_f*.json"))):
        key = os.path.basename(path)[len("bank_"):-len(".json")]
        form = FORM_OF.get(key)
        if not form:
            print("SKIP unknown file", path); continue
        if form not in meta_cache:
            meta_cache[form] = form_meta(form)
        sp_ok, units_ok, themes_ok = meta_cache[form]
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print("PARSE FAIL", path, e); continue
        for q in data:
            reason = None
            sp = (q.get("sp_rujukan") or q.get("sp_kod") or "").strip()
            aras = (q.get("aras") or "").strip().upper()
            soalan = (q.get("soalan") or "").strip()
            pil = q.get("pilihan") or []
            jw = (q.get("jawapan_betul") or "").strip().upper()
            topic = (q.get("topic") or "").strip()
            theme = (q.get("theme") or "").strip()
            if not soalan: reason = "empty soalan"
            elif sp not in sp_ok: reason = "bad sp %r" % sp
            elif aras not in ARAS: reason = "bad aras"
            elif not isinstance(pil, list) or len(pil) != 4: reason = "pilihan!=4"
            elif jw not in LETTERS: reason = "bad letter"
            elif topic not in units_ok: reason = "bad topic %r" % topic
            elif theme not in themes_ok: reason = "bad theme %r" % theme
            else:
                norm = re.sub(r"\s+", " ", soalan.lower())
                if norm in seen_text: reason = "dup in batch"
                else: seen_text.add(norm)
            if reason:
                invalid.append((key, reason, soalan[:50]))
                continue
            valid.append({"sp_rujukan": sp, "aras": aras, "soalan": soalan,
                          "pilihan": pil, "jawapan_betul": jw, "markah": 1,
                          "maklum_balas": q.get("maklum_balas", ""),
                          "topic": topic, "theme": theme, "_form": form})
            per_form[form] = per_form.get(form, 0) + 1

    print("=== VALIDATION ===")
    print("valid:", len(valid), "| invalid:", len(invalid))
    for f in sorted(per_form): print("  Form %d: %d" % (f, per_form[f]))
    if invalid:
        print("--- first 15 invalid ---")
        for row in invalid[:15]: print("  ", row)

    if not do_insert:
        print("\n(dry-run — pass --insert to write to the bank)")
        return

    # group by (topic, theme) so add_questions tags each group correctly
    groups = {}
    for q in valid:
        groups.setdefault((q["topic"], q["theme"]), []).append(q)
    total = 0
    for (topic, theme), qs in groups.items():
        n = bank.add_questions(qs, status="diluluskan", topic=topic, theme=theme)
        total += n
    print("\n=== INSERT DONE === newly inserted (dedupe applied):", total)


if __name__ == "__main__":
    main()
