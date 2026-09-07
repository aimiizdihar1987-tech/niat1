#!/usr/bin/env python3
"""
Student Levels — static per-pupil differentiation levels the teacher has
already assigned (advance / intermediate / below average).

TWO backends, same public function (matches the pattern used everywhere
else in this project — e.g. peringatan.py, prestasi_murid.py):
  - Supabase `app_settings` (key "student-levels:<class>") — the durable
    source, required for this to work on Cloud Run (the container never has
    the local text file). Pushed there by sync_from_file() /
    `python student_levels.py --sync`.
  - Local text file "id delima murid dan level.txt" at the project root —
    what the teacher actually edits by hand; also the fallback when Supabase
    isn't configured (desktop/offline use).

File format (blank-line separated blocks):
    <Class name>
    <email> - <level>
    <email> - <level>

    <Next class name>
    ...

Unlike prestasi_murid.py's history-based Agent 4 differentiation (built from
past quiz scores, needs at least one quiz read first), this is a DIRECT
source: the teacher already knows each pupil's level, so a class listed here
gets differentiated worksheets from the very first lesson, automatically,
with no quiz history and no extra click.

Whenever the teacher edits the text file, re-run `python student_levels.py
--sync` (or `migrate_to_supabase.py --student-levels`) so the deployed app
picks up the change — same as timetable.json/app_settings elsewhere here.
"""

import os
import sys

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
LEVELS_FILE = os.path.join(ROOT, "id delima murid dan level.txt")

# Same three bands as prestasi_murid-based Agent 4 (server.BAND_ORDER /
# _BAND_COG) — a pupil differentiated by a fixed level or by cumulative
# quiz score lands in the exact same three worksheet shapes either way.
_LEVEL_TO_BAND = {
    "advance": "extension",
    "advanced": "extension",
    "intermediate": "core",
    "below average": "remedial",
    "below-average": "remedial",
    "weak": "remedial",
}


def _setting_key(class_name):
    return "student-levels:" + (class_name or "").strip().lower()


def _parse_file(path):
    """Return {class_name_lower: {emel: band}} from the local text file."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f]
    except FileNotFoundError:
        return {}
    classes = {}
    current = None
    for raw in lines:
        line = raw.strip()
        if not line:
            current = None
            continue
        if "@" not in line:
            current = line.strip().lower()
            classes.setdefault(current, {})
            continue
        if current is None:
            continue
        # Split on " - " (with spaces), not bare "-" — emails like
        # "m-test1@moe-dl.edu.my" contain hyphens of their own.
        emel, _, level = line.partition(" - ")
        emel = emel.strip().lower()
        band = _LEVEL_TO_BAND.get(level.strip().lower())
        if emel and band:
            classes[current][emel] = band
    return classes


def sync_from_file(path=None):
    """Push every class block in the local text file into Supabase
    app_settings, so the Cloud Run container (which never sees this local
    file) can use the same data. Returns {class_name: pupil_count}."""
    classes = _parse_file(path or LEVELS_FILE)
    pushed = {}
    for class_name, bands in classes.items():
        sb.insert("app_settings", {
            "key": _setting_key(class_name),
            "value": bands,
        }, upsert_on="key")
        pushed[class_name] = len(bands)
    return pushed


def bands_for_class(class_name):
    """{"emel": "band"} for one class, or {} if that class has no assigned
    levels anywhere (callers should fall back to the ordinary
    one-worksheet-for-everyone distribution, or to prestasi_murid-based
    differentiation, in that case)."""
    key = _setting_key(class_name)
    if sb.use_cloud():
        try:
            rows = sb.select("app_settings", params={"select": "value", "key": "eq." + key})
            if rows and rows[0].get("value"):
                return dict(rows[0]["value"])
        except sb.SupabaseError:
            pass  # fall through to the local file (offline/desktop use)
    return _parse_file(LEVELS_FILE).get((class_name or "").strip().lower(), {})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":
        result = sync_from_file()
        if not result:
            print("No class blocks found in", LEVELS_FILE)
        for name, count in result.items():
            print("  {} -> {} pupil(s)".format(name, count))
        print("Synced {} class(es) to Supabase.".format(len(result)))
    else:
        print(__doc__)
