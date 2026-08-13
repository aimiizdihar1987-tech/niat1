#!/usr/bin/env python3
"""
Push the CEFR B1 Preliminary word list (data/cefr_b1_wordlist.json) to Supabase.

  - upserts every word into public.vocab_words (needs the table — see
    supabase/schema.sql, "vocab_words" block, run once in the SQL Editor)
  - also uploads the JSON itself to Storage (bucket "wordlists") as a backup

Safe to re-run: upsert on word, storage upload overwrites.
"""

import json
import os
import sys

import supabase_client as sb
import wordlist

ROOT = os.path.dirname(os.path.abspath(__file__))
BATCH = 500


def main():
    if not sb.configured():
        print("supabase_config.txt is not filled in — aborting.")
        sys.exit(1)

    words = wordlist.display_words()
    if not words:
        print("data/cefr_b1_wordlist.json is missing or empty — run the extractor first.")
        sys.exit(1)
    print("Pushing {} words to Supabase...".format(len(words)))

    # 1) table upsert, in batches
    rows = [{"word": w} for w in words]
    pushed = 0
    try:
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            sb.insert("vocab_words", chunk, role="service", upsert_on="word")
            pushed += len(chunk)
            print("  vocab_words: {}/{}".format(pushed, len(rows)))
        total = sb.select("vocab_words", params={"select": "count"}, role="service")
        print("  table done — row count now:", total)
    except sb.SupabaseError as e:
        if "does not exist" in str(e) or "PGRST205" in str(e) or "42P01" in str(e):
            print("\n  !! Table public.vocab_words does not exist yet.")
            print("  Run the 'vocab_words' block from supabase/schema.sql in the")
            print("  Supabase dashboard -> SQL Editor, then re-run this script.")
        else:
            print("\n  !! Supabase error:", e)

    # 2) storage backup of the raw JSON
    try:
        with open(os.path.join(ROOT, "data", "cefr_b1_wordlist.json"), "rb") as f:
            data = f.read()
        sb.storage_create_bucket("wordlists", public=False)
        sb.storage_upload("wordlists", "cefr_b1_wordlist.json", data,
                          content_type="application/json")
        print("  storage backup done: wordlists/cefr_b1_wordlist.json")
    except sb.SupabaseError as e:
        print("  !! storage upload failed:", e)


if __name__ == "__main__":
    main()
