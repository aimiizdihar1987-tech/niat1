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
URL = _CFG.get("SUPABASE_URL", "").rstrip("/")
ANON_KEY = _CFG.get("SUPABASE_ANON_KEY", "")
SERVICE_KEY = _CFG.get("SUPABASE_SERVICE_ROLE_KEY", "")


def configured():
    return bool(URL and ANON_KEY and SERVICE_KEY)


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


# --------------------------------------------------------------------------
# PostgREST table access
# --------------------------------------------------------------------------
def select(table_name, params=None, role="service", access_token=None):
    """params example: {"select": "*", "sp_kod": "eq.B1DL1"}"""
    return _request("GET", "/rest/v1/" + table_name, role=role, params=params,
                     access_token=access_token) or []


def insert(table_name, rows, role="service", access_token=None, upsert_on=None):
    """rows: dict or list of dicts. Returns the inserted rows (Prefer: representation)."""
    headers = {"Prefer": "return=representation"}
    params = None
    if upsert_on:
        headers["Prefer"] += ",resolution=merge-duplicates"
        params = {"on_conflict": upsert_on}
    return _request("POST", "/rest/v1/" + table_name, role=role, body=rows,
                     params=params, access_token=access_token, extra_headers=headers)


def update(table_name, match_params, patch, role="service", access_token=None):
    """match_params example: {"id": "eq.5"}"""
    headers = {"Prefer": "return=representation"}
    return _request("PATCH", "/rest/v1/" + table_name, role=role, body=patch,
                     params=match_params, access_token=access_token, extra_headers=headers)


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
