#!/usr/bin/env python3
"""
Seed (or reset) the program-wide SUPER ADMIN account for Niat — the person who
oversees the AI Powered Classroom 1 Malaysia programme and manages every
school, teacher and timetable across it.

Usage:
    python create_superadmin.py                       # uses the defaults below
    python create_superadmin.py <username> <password> "Full Name"

It writes to BOTH stores so login works no matter which one the server uses:
  - Supabase Auth + profiles.role = 'super_admin' (when configured)
  - local users.json  (offline / no-Supabase fallback), role = 'super_admin'
"""

import sys

import auth
import supabase_client as sb

DEFAULT_USER = "superadmin1"
DEFAULT_PASS = "superadmin1"
DEFAULT_NAME = "Super Admin — AI Powered Classroom 1M"
ROLE = "super_admin"


def main(argv):
    username = (argv[1] if len(argv) > 1 else DEFAULT_USER).strip().lower()
    password = argv[2] if len(argv) > 2 else DEFAULT_PASS
    full_name = argv[3] if len(argv) > 3 else DEFAULT_NAME

    # 1) Supabase (authoritative when the app runs against the cloud) --------
    if sb.configured():
        try:
            existing = sb.admin_find_user(username)
            if existing:
                sb.admin_update_user(
                    existing["id"], password=password,
                    user_metadata={"username": username, "full_name": full_name,
                                   "role": ROLE})
                print("Supabase: updated existing auth user '{}'.".format(username))
            else:
                sb.admin_create_user(username, password, full_name=full_name,
                                     role_name=ROLE)
                print("Supabase: created auth user '{}'.".format(username))
            # The DB trigger seeds profiles with the metadata role, but force it
            # here too in case the row already existed at a lower tier.
            sb.set_profile_role(username, ROLE)
            print("Supabase: profiles.role set to '{}'.".format(ROLE))
        except sb.SupabaseError as e:
            print("Supabase step FAILED (local fallback still written): {}".format(e))
    else:
        print("Supabase not configured — writing local account only.")

    # 2) Local users.json fallback ------------------------------------------
    auth.add_user(username, password, full_name=full_name, role=ROLE)
    print("Local users.json: '{}' saved with role '{}'.".format(username, ROLE))

    print("\nDone. Log in with:\n  username: {}\n  password: {}".format(username, password))


if __name__ == "__main__":
    main(sys.argv)
