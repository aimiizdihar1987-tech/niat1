#!/usr/bin/env python3
"""
Niat login system — Python stdlib only.

- Passwords are NEVER stored in plain text: PBKDF2-HMAC-SHA256 with a
  per-user random salt (260,000 rounds), kept in users.json.
- Sessions are signed tokens (HMAC-SHA256) in an HttpOnly cookie, so they
  survive server restarts without a session database. The signing secret is
  auto-generated once into auth_secret.txt (keep it private, like a password).

Manage teachers from a terminal in this folder:
    python auth.py add  <username>     (prompts for the password)
    python auth.py del  <username>
    python auth.py list
"""

import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(ROOT, "users.json")
SECRET_FILE = os.path.join(ROOT, "auth_secret.txt")

ROUNDS = 260_000
SESSION_DAYS = 30
COOKIE_NAME = "niat_session"
_USER_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")


# --------------------------------------------------------------------------
# Secret + users store
# --------------------------------------------------------------------------
def _secret():
    try:
        with open(SECRET_FILE, encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s.encode("utf-8")
    except FileNotFoundError:
        pass
    s = secrets.token_hex(32)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(s + "\n")
    return s.encode("utf-8")


def _load_users():
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def _hash_pw(password, salt_hex):
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             bytes.fromhex(salt_hex), ROUNDS)
    return dk.hex()


def add_user(username, password):
    username = (username or "").strip().lower()
    if not _USER_RE.match(username):
        raise ValueError("Username must be 3-32 chars: a-z 0-9 _ . -")
    if len(password or "") < 6:
        raise ValueError("Password must be at least 6 characters.")
    users = _load_users()
    salt = secrets.token_hex(16)
    users[username] = {"salt": salt, "hash": _hash_pw(password, salt)}
    _save_users(users)
    return True


def remove_user(username):
    users = _load_users()
    if users.pop((username or "").strip().lower(), None) is None:
        return False
    _save_users(users)
    return True


def verify(username, password):
    users = _load_users()
    rec = users.get((username or "").strip().lower())
    if not rec:
        # constant-ish time even for unknown users
        _hash_pw(password or "", "00" * 16)
        return False
    return hmac.compare_digest(rec["hash"], _hash_pw(password or "", rec["salt"]))


# --------------------------------------------------------------------------
# Signed session tokens (stateless — survive server restarts)
# --------------------------------------------------------------------------
def make_token(username):
    exp = str(int(time.time()) + SESSION_DAYS * 86400)
    payload = "{}|{}".format(username, exp)
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = "{}|{}".format(payload, sig)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def check_token(token):
    """Return the username if the token is valid and unexpired, else None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, exp, sig = raw.rsplit("|", 2)
        payload = "{}|{}".format(username, exp)
        good = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        if int(exp) < time.time():
            return None
        # Trust the signature + expiry alone (standard session-token design).
        # We deliberately do NOT also require `username in _load_users()` here:
        # accounts created via Supabase Auth (signup, or migrated teachers)
        # never appear in the local users.json store at all, so that check
        # would reject every Supabase-only session as "logged out" the
        # instant it was issued.
        return username
    except Exception:  # noqa: BLE001
        return None


def user_from_cookie(cookie_header):
    """Extract + validate the session from a raw Cookie header. None if absent/bad."""
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE_NAME and v:
            return check_token(v)
    return None


def session_cookie(token):
    return ("{}={}; Path=/; HttpOnly; SameSite=Lax; Max-Age={}"
            .format(COOKIE_NAME, token, SESSION_DAYS * 86400))


def clear_cookie():
    return "{}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0".format(COOKIE_NAME)


# --------------------------------------------------------------------------
# CLI for managing teachers
# --------------------------------------------------------------------------
def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "").lower()
    if cmd == "add" and len(argv) >= 3:
        pw = argv[3] if len(argv) >= 4 else getpass.getpass("Password for {}: ".format(argv[2]))
        add_user(argv[2], pw)
        print("User '{}' saved.".format(argv[2].lower()))
    elif cmd == "del" and len(argv) >= 3:
        print("Removed." if remove_user(argv[2]) else "User not found.")
    elif cmd == "list":
        for u in sorted(_load_users()):
            print(" -", u)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
