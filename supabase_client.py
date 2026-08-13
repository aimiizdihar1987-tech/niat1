#!/usr/bin/env python3
"""
Niat <-> Supabase — Python stdlib only (urllib), no pip install, matching how
this project already talks to Gemini/Gamma. Reads credentials from
supabase_config.txt (SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY),
same key=value style as reminder_config.txt.

Two client kinds:
  - table(...) with role="anon"    -> respects Row Level Security (use for the
    live app, once a user is signed in and we forward their access token)
  - table(...) with role="service" -> BYPASSES RLS (server-side only: the
    one-time migration script, and admin user creation)
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(ROOT, "supabase_config.txt")


class SupabaseError(RuntimeError):
    pass


def _read_config():
    cfg = {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg


_CFG = _read_config()
# Env vars first (how Cloud Run / Docker supply credentials), then the local
# supabase_config.txt file (how the school laptop supplies them).
URL = (os.environ.get("SUPABASE_URL") or _CFG.get("SUPABASE_URL", "")).rstrip("/")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or _CFG.get("SUPABASE_ANON_KEY", "")
SERVICE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
               or _CFG.get("SUPABASE_SERVICE_ROLE_KEY", ""))


def configured():
    return bool(URL and ANON_KEY and SERVICE_KEY)


def use_cloud():
    """Should app data (question bank, lessons) live in Supabase?

    NIAT_STORAGE=local    -> force SQLite/local files (e.g. offline demo)
    NIAT_STORAGE=supabase -> force Supabase (fail loudly if misconfigured)
    unset / auto          -> Supabase whenever credentials are configured
    """
    mode = os.environ.get("NIAT_STORAGE", "auto").strip().lower()
    if mode == "local":
        return False
    if mode == "supabase":
        return True
    return configured()


def cloud_required():
    """True when falling back to local disk would cause production data loss."""
    return os.environ.get("NIAT_STORAGE", "auto").strip().lower() == "supabase"


def _key_for(role):
    return SERVICE_KEY if role == "service" else ANON_KEY


def _request(method, path, role="service", body=None, params=None, access_token=None,
             extra_headers=None):
    if not URL:
        raise SupabaseError("supabase_config.txt is not filled in yet (SUPABASE_URL missing).")
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(URL + path + qs, method=method)
    key = _key_for(role)
    req.add_header("apikey", key)
    req.add_header("Authorization", "Bearer " + (access_token or key))
    req.add_header("Content-Type", "application/json")
    for k, v in (extra_headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise SupabaseError("{} {} -> {}".format(method, path, detail)) from None
    except (urllib.error.URLError, OSError) as e:
        # No network, DNS gone (a paused Supabase project stops resolving),
        # timeout. Callers already handle SupabaseError and fall back to local
        # data — they should not have to catch urllib's exceptions too.
        raise SupabaseError("{} {} -> unreachable: {}".format(method, path, e)) from None


# --------------------------------------------------------------------------
# PostgREST table access
# --------------------------------------------------------------------------
def select(table_name, params=None, role="service", access_token=None):
    """params example: {"select": "*", "sp_kod": "eq.B1DL1"}"""
    return _request("GET", "/rest/v1/" + table_name, role=role, params=params,
                     access_token=access_token) or []


def insert(table_name, rows, role="service", access_token=None, upsert_on=None,
           ignore_on=None):
    """rows: dict or list of dicts. Returns the inserted rows (Prefer: representation).

    upsert_on: column name — existing rows with the same value get OVERWRITTEN.
    ignore_on: column name — existing rows with the same value are left alone
               (INSERT ... ON CONFLICT DO NOTHING); the response then contains
               only the rows that were actually inserted.
    """
    headers = {"Prefer": "return=representation"}
    params = None
    if upsert_on:
        headers["Prefer"] += ",resolution=merge-duplicates"
        params = {"on_conflict": upsert_on}
    elif ignore_on:
        headers["Prefer"] += ",resolution=ignore-duplicates"
        params = {"on_conflict": ignore_on}
    return _request("POST", "/rest/v1/" + table_name, role=role, body=rows,
                     params=params, access_token=access_token, extra_headers=headers)


def update(table_name, match_params, patch, role="service", access_token=None):
    """match_params example: {"id": "eq.5"}"""
    headers = {"Prefer": "return=representation"}
    return _request("PATCH", "/rest/v1/" + table_name, role=role, body=patch,
                     params=match_params, access_token=access_token, extra_headers=headers)


# --------------------------------------------------------------------------
# Storage (raw file upload/download — service_role only, bypasses RLS)
# --------------------------------------------------------------------------
def _request_raw(method, path, content_type, data, extra_headers=None):
    """Like _request(), but sends a raw byte body instead of JSON-encoding it
    (for file uploads/downloads)."""
    if not URL:
        raise SupabaseError("supabase_config.txt is not filled in yet (SUPABASE_URL missing).")
    req = urllib.request.Request(URL + path, method=method, data=data)
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", "Bearer " + SERVICE_KEY)
    req.add_header("Content-Type", content_type)
    for k, v in (extra_headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            ct = r.headers.get("Content-Type", "")
            return json.loads(raw) if raw and "json" in ct else raw
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise SupabaseError("{} {} -> {}".format(method, path, detail)) from None
    except (urllib.error.URLError, OSError) as e:
        raise SupabaseError("{} {} -> unreachable: {}".format(method, path, e)) from None


def storage_create_bucket(bucket_id, public=False):
    """Create a Storage bucket if it doesn't already exist. Safe to call
    every time before an upload."""
    try:
        _request("POST", "/storage/v1/bucket", role="service",
                  body={"id": bucket_id, "name": bucket_id, "public": public})
    except SupabaseError as e:
        if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
            raise


def storage_upload(bucket, path, data, content_type="application/octet-stream"):
    """Upload (or overwrite) a file. `data` is raw bytes. Returns the storage
    path on success."""
    return _request_raw("POST", "/storage/v1/object/{}/{}".format(bucket, path),
                         content_type, data, extra_headers={"x-upsert": "true"})


def storage_download(bucket, path):
    """Download a file's raw bytes."""
    return _request_raw("GET", "/storage/v1/object/{}/{}".format(bucket, path),
                         "application/octet-stream", None)


def storage_delete(bucket, path):
    """Remove a file. Raises SupabaseError if it wasn't there."""
    return _request("DELETE", "/storage/v1/object/{}/{}".format(bucket, path),
                     role="service")


def delete(table_name, match_params, role="service", access_token=None):
    return _request("DELETE", "/rest/v1/" + table_name, role=role,
                     params=match_params, access_token=access_token)


# --------------------------------------------------------------------------
# Auth (Supabase manages password hashing/storage — we never see raw hashes)
# --------------------------------------------------------------------------
def _synthetic_email(username):
    # Niat logs in with a short username; Supabase Auth wants an email, so we
    # mint one deterministically. Teachers never see or type this address.
    return "{}@niat.local".format(username.strip().lower())


def sign_in(username, password):
    """Returns {"access_token", "refresh_token", "user": {...}} or raises SupabaseError."""
    body = {"email": _synthetic_email(username), "password": password}
    return _request("POST", "/auth/v1/token", role="anon", body=body,
                     params={"grant_type": "password"})


def admin_create_user(username, password, full_name=None, role_name="teacher"):
    """Service-role only. Creates the Auth user; the DB trigger auto-creates
    the matching profiles row."""
    body = {
        "email": _synthetic_email(username),
        "password": password,
        "email_confirm": True,
        "user_metadata": {"username": username, "full_name": full_name, "role": role_name},
    }
    return _request("POST", "/auth/v1/admin/users", role="service", body=body)


def admin_list_users():
    return _request("GET", "/auth/v1/admin/users", role="service") or {}


def admin_delete_user(auth_user_id):
    return _request("DELETE", "/auth/v1/admin/users/" + auth_user_id, role="service")


def admin_find_user(username):
    """Return the Auth user dict whose user_metadata.username matches, else None.
    Service-role only."""
    username = (username or "").strip().lower()
    for u in (admin_list_users().get("users") or []):
        if (u.get("user_metadata") or {}).get("username", "").lower() == username:
            return u
    return None


def admin_update_user(auth_user_id, password=None, user_metadata=None):
    """Service-role only. Update an Auth user's password and/or metadata."""
    body = {}
    if password is not None:
        body["password"] = password
    if user_metadata is not None:
        body["user_metadata"] = user_metadata
    return _request("PUT", "/auth/v1/admin/users/" + auth_user_id, role="service", body=body)


def set_profile_role(username, role):
    """Update the profiles table role (the value the app actually reads).
    Service-role bypasses RLS. Returns the updated rows."""
    return update("profiles", {"username": "eq." + username.strip().lower()},
                  {"role": role}, role="service")


def admin_set_banned(auth_user_id, banned):
    """Deactivate (ban) or reactivate an Auth user. A banned user can no longer
    sign in — GoTrue rejects them at the token endpoint. Service-role only."""
    # 100 years ~= permanent; "none" lifts the ban.
    return _request("PUT", "/auth/v1/admin/users/" + auth_user_id, role="service",
                     body={"ban_duration": "876000h" if banned else "none"})


def is_banned(auth_user):
    """True if the given Auth user dict is currently deactivated/banned."""
    bu = auth_user.get("banned_until")
    return bool(bu)
