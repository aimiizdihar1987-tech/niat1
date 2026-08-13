#!/usr/bin/env python3
"""
Push existing profile photos (web/avatars/*.png) to Supabase Storage.

web/avatars/ is gitignored and Cloud Run wipes its disk, so a photo saved
before this change only ever existed on the laptop that uploaded it. Run this
once to move those photos into the private "avatars" bucket and point
profiles.avatar_url at them — after that the server keeps both in step on
every upload (see avatar_save() in server.py).

Safe to re-run: the upload overwrites and the profiles update is idempotent.
"""

import os
import re
import sys
import time

import supabase_client as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
AVATAR_DIR = os.path.join(ROOT, "web", "avatars")
BUCKET = "avatars"
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")


def main():
    if not sb.configured():
        print("supabase_config.txt is not filled in — aborting.")
        sys.exit(1)

    try:
        files = sorted(f for f in os.listdir(AVATAR_DIR) if f.endswith(".png"))
    except FileNotFoundError:
        files = []
    if not files:
        print("No photos in web/avatars/ — nothing to push.")
        return

    print("Found {} photo(s) in web/avatars/".format(len(files)))
    sb.storage_create_bucket(BUCKET, public=False)

    pushed = skipped = 0
    for name in files:
        user = name[:-4].lower()
        if not USERNAME_RE.match(user):
            print("  skip {} — not a valid username".format(name))
            skipped += 1
            continue
        # Only push photos that belong to a real account, so a stale file from
        # a deleted teacher doesn't quietly reappear.
        try:
            rows = sb.select("profiles", {"select": "username", "username": "eq." + user})
        except sb.SupabaseError as e:
            print("  !! {} — could not check profiles: {}".format(user, e))
            skipped += 1
            continue
        if not rows:
            print("  skip {} — no such account in profiles".format(user))
            skipped += 1
            continue

        with open(os.path.join(AVATAR_DIR, name), "rb") as f:
            data = f.read()
        url = "/avatars/{}.png?v={}".format(user, int(time.time()))
        try:
            sb.storage_upload(BUCKET, user + ".png", data, content_type="image/png")
            sb.update("profiles", {"username": "eq." + user}, {"avatar_url": url},
                      role="service")
        except sb.SupabaseError as e:
            print("  !! {} — upload failed: {}".format(user, e))
            skipped += 1
            continue
        print("  pushed {} ({:.0f} KB) -> {}".format(user, len(data) / 1024, url))
        pushed += 1

    print("\nDone: {} pushed, {} skipped.".format(pushed, skipped))
    if pushed:
        print("Photos now follow the account — redeploy and they will still be there.")


if __name__ == "__main__":
    main()
