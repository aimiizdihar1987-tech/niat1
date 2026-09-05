#!/usr/bin/env python3
"""
Niat — English Form 3 Lesson Plan & Worksheet Generator (Backend, Phase 1 MVP)

Lightweight server with no external dependencies (Python stdlib only):
  - Serves the single-page web app (web/ folder) and the curriculum (DSKP) data.
  - Proxies /api/generate-rph and /api/generate-worksheet to the Gemini API
    (API key from environment / apikey.txt — never exposed to the browser).
  - Saves teacher-approved output to the output/ folder.

Run:
    set GOOGLE_API_KEY=AIza...              (Windows cmd)
    $env:GOOGLE_API_KEY="AIza..."           (PowerShell)
    python server.py

Then open http://localhost:8000
"""

import base64
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from urllib.parse import urlparse, parse_qs

import auth
import supabase_client as sb
import bank_soalan as bank
import export_docx
import export_pptx
import guardrail
import lessons
import peringatan
import prestasi_murid
import wordlist

# When launched with pythonw.exe (windowless, e.g. the auto-start task),
# stdout/stderr are None — guard so prints and request logging don't crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# --------------------------------------------------------------------------
# Konfigurasi
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
PROMPT_DIR = os.path.join(ROOT, "prompts")
CONTAINER_MODE = os.environ.get("NIAT_CONTAINER", "").strip().lower() in ("1", "true", "yes")
OUTPUT_DIR = (os.environ.get("NIAT_OUTPUT_DIR", "").strip()
              or ("/tmp/niat-output" if CONTAINER_MODE else os.path.join(ROOT, "output")))
DSKP_FILE = os.path.join(ROOT, "dskp_english_f3.json")  # default / backward-compat
DSKP_FORMS = (1, 2, 3, 4, 5)


def dskp_file_for(form):
    """Path to the DSKP data file for a given Form (1-5). Falls back to Form 3."""
    try:
        n = int(form)
    except (TypeError, ValueError):
        n = 3
    if n not in DSKP_FORMS:
        n = 3
    path = os.path.join(ROOT, "dskp_english_f{}.json".format(n))
    return path if os.path.exists(path) else DSKP_FILE

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

def _baca_kunci_fail():
    """Baca kunci API dari fail apikey.txt (abaikan baris kosong & baris '#').

    Memudahkan guru: tampal kunci sekali dalam apikey.txt, tak perlu env var.
    """
    try:
        with open(os.path.join(ROOT, "apikey.txt"), encoding="utf-8") as f:
            for baris in f:
                baris = baris.strip()
                if baris and not baris.startswith("#") and "TAMPAL_KUNCI" not in baris:
                    return baris
    except FileNotFoundError:
        pass
    return ""


# Kunci API Google (Gemini) — keutamaan: env var, kemudian fail apikey.txt.
GOOGLE_API_KEY = (
    os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
    or _baca_kunci_fail()
)
# Boleh tukar ke "gemini-2.5-pro" untuk kualiti lebih tinggi (lebih perlahan/mahal),
# atau "gemini-2.0-flash" jika model lalai tidak tersedia untuk kunci anda.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# --- Enjin sandaran luar talian (Ollama, tempatan) ---------------------------
# Jika Gemini gagal (tiada internet / kuota habis), sistem beralih automatik
# ke model tempatan melalui Ollama. Mod: auto (lalai) | gemini | local.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
ENGINE_MODE = os.environ.get("NIAT_ENGINE", "auto").strip().lower()

# --- Login brute-force lockout -----------------------------------------------
# Per-username counter, kept in this process's memory (good enough for a
# single small-school deployment; resets on restart/redeploy, which is fine —
# an attacker who can force a restart has bigger problems to exploit). Keyed
# by username, not IP, so it can't be trivially bypassed by rotating IPs.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60
_login_attempts_lock = threading.Lock()
_login_attempts = {}  # username -> {"count", "first_fail", "locked_until"}


def _login_locked_seconds(username):
    """Seconds left in the lockout for this username, or 0 if not locked."""
    with _login_attempts_lock:
        rec = _login_attempts.get(username)
        if not rec:
            return 0
        remaining = rec.get("locked_until", 0) - time.time()
        return int(remaining) if remaining > 0 else 0


def _login_note_failure(username):
    now = time.time()
    with _login_attempts_lock:
        rec = _login_attempts.get(username)
        if not rec or now - rec.get("first_fail", now) > LOGIN_WINDOW_SECONDS:
            rec = {"count": 0, "first_fail": now}
        rec["count"] += 1
        if rec["count"] >= LOGIN_MAX_ATTEMPTS:
            rec["locked_until"] = now + LOGIN_LOCKOUT_SECONDS
        _login_attempts[username] = rec


def _login_note_success(username):
    with _login_attempts_lock:
        _login_attempts.pop(username, None)


def runtime_configuration_errors():
    """Return secret-free configuration problems that make production unsafe."""
    errors = []
    if not CONTAINER_MODE:
        return errors
    if not GOOGLE_API_KEY:
        errors.append("GOOGLE_API_KEY is required")
    if not sb.configured():
        errors.append("SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY are required")
    if not sb.cloud_required():
        errors.append("NIAT_STORAGE must be supabase")
    if len(os.environ.get("NIAT_AUTH_SECRET", "").strip()) < 32:
        errors.append("NIAT_AUTH_SECRET must contain at least 32 characters")
    if os.environ.get("NIAT_REQUIRE_HUB", "").strip().lower() in ("1", "true", "yes"):
        cfg = _read_reminder_cfg()
        if not cfg.get("APPSCRIPT_HUB_URL") or not cfg.get("APPSCRIPT_HUB_KEY"):
            errors.append("APPSCRIPT_HUB_URL and APPSCRIPT_HUB_KEY are required")
    if os.environ.get("NIAT_REQUIRE_GOOGLE_OAUTH", "").strip().lower() in ("1", "true", "yes"):
        try:
            import niat_google
            oauth_ready = niat_google.available(interactive=False)
        except Exception:
            oauth_ready = False
        if not oauth_ready:
            errors.append("GOOGLE_OAUTH_TOKEN_JSON is required for unattended Google API access")
    return errors

_ENGINE_STATE = threading.local()


def last_engine():
    """Enjin yang digunakan oleh panggilan LLM terakhir dalam thread ini."""
    return getattr(_ENGINE_STATE, "last", "gemini")


def ollama_available():
    """True jika Ollama berjalan dan model sandaran yang dikonfigurasi wujud."""
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        return any(m.get("name") == OLLAMA_MODEL for m in data.get("models", []))
    except Exception:  # noqa: BLE001
        return False

# --------------------------------------------------------------------------
# Pembantu Gemini API (Google AI Studio)
# --------------------------------------------------------------------------
def call_llm(system_prompt, user_prompt, max_tokens=8000):
    """Panggil LLM: Gemini dahulu; jatuh balik automatik ke Ollama tempatan.

    Mod (NIAT_ENGINE): auto (lalai) — Gemini, sandaran Ollama;
    gemini — Gemini sahaja; local — Ollama sahaja (luar talian).
    """
    _ENGINE_STATE.last = "gemini"
    if ENGINE_MODE != "local" and GOOGLE_API_KEY:
        try:
            return call_gemini(system_prompt, user_prompt, max_tokens)
        except RuntimeError:
            if ENGINE_MODE == "gemini" or not ollama_available():
                raise
    # Tiada kunci / dipaksa local / Gemini gagal → cuba model tempatan.
    if not ollama_available():
        raise RuntimeError(
            "Tiada enjin AI tersedia: Gemini tidak boleh dihubungi dan "
            "Ollama ({}) tidak berjalan.".format(OLLAMA_MODEL)
        )
    _ENGINE_STATE.last = "local"
    return call_ollama(system_prompt, user_prompt, max_tokens)


def call_ollama(system_prompt, user_prompt, max_tokens=8000):
    """Panggil model tempatan melalui Ollama /api/chat (format JSON dipaksa)."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"num_predict": max_tokens, "temperature": 0.7},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        # Model tempatan pada CPU boleh lambat — beri masa yang panjang.
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError("Ollama gagal: {}".format(e))
    text = (data.get("message", {}) or {}).get("content", "").strip()
    if not text:
        raise RuntimeError("Ollama tiada respons: " + json.dumps(data)[:300])
    return text


def call_gemini(system_prompt, user_prompt, max_tokens=8000):
    """Panggil Gemini generateContent dan pulangkan teks respons. Guna urllib sahaja."""
    if not GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY tidak ditetapkan. Set pemboleh ubah persekitaran dahulu."
        )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7,
            # Paksa output JSON tulen — padan dengan arahan dalam fail prompt.
            "responseMimeType": "application/json",
        },
    }
    # Cuba sehingga 3 kali untuk ralat sementara (429 kuota / 5xx / rangkaian).
    data = None
    last_err = None
    for attempt in range(3):
        req = urllib.request.Request(
            GEMINI_URL.format(model=MODEL),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-goog-api-key": GOOGLE_API_KEY,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            last_err = "Gemini API ralat {}: {}".format(e.code, detail[:400])
            if e.code not in (429, 500, 502, 503) or attempt == 2:
                raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = "Rangkaian gagal: {}".format(e)
            if attempt == 2:
                raise RuntimeError(last_err)
        time.sleep(2 * (attempt + 1))  # 2s, 4s
    if data is None:
        raise RuntimeError(last_err or "Gemini tiada respons")
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini tiada respons (mungkin disekat): " + json.dumps(data)[:400])
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def extract_json(text):
    """Cabut objek JSON pertama daripada respons model (buang pagar ```json bila ada)."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    # Cuba terus dahulu
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Sandaran: ambil dari '{' pertama ke '}' terakhir
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(candidate[start:end + 1])
    raise ValueError("Respons model bukan JSON sah:\n" + text[:500])


def call_llm_json(system_prompt, user_prompt, max_tokens=8000, retries=1):
    """call_llm + extract_json, retrying the whole call if the model's reply isn't
    valid JSON (occasional truncated/malformed output) — otherwise one bad reply
    crashes the whole agent instead of just costing one extra call."""
    last_err = None
    for _ in range(retries + 1):
        raw = call_llm(system_prompt, user_prompt, max_tokens)
        try:
            return extract_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise last_err


def read_text(path, fallback=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return fallback


def load_dskp(form=3):
    with open(dskp_file_for(form), encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Logik agen
# --------------------------------------------------------------------------
def find_curriculum(inputs):
    """Resolve full Skill / Content Standard / Learning Standard from selected codes.

    JSON keys 'bidang' (=Skill), 'standard_kandungan' (=Content Standard) and
    'standard_pembelajaran' (=Learning Standard) are reused from the engine.
    """
    dskp = load_dskp(inputs.get("form", 3))
    bidang = next((b for b in dskp["bidang"] if b["kod"] == inputs.get("bidang_kod")), None)
    if not bidang:
        return {"bidang": None, "sk": None, "sp": []}
    sk = next((s for s in bidang["standard_kandungan"] if s["kod"] == inputs.get("sk_kod")), None)
    sp_kods = set(inputs.get("sp_kods", []))
    sp = [s for s in (sk["standard_pembelajaran"] if sk else []) if s["kod"] in sp_kods]
    return {"bidang": bidang, "sk": sk, "sp": sp}


def build_context_block(inputs, cur):
    """Build the curriculum context block (text) injected into the prompt."""
    ls_lines = "\n".join("  {} {}".format(s["kod"], s["huraian"]) for s in cur["sp"])
    meta = load_dskp(inputs.get("form", 3))
    form_no = meta.get("form", inputs.get("form", 3))
    return (
        "Subject          : English (KSSM Form {form_no})\n".format(form_no=form_no) +
        "CEFR target      : {cefr}\n"
        "Textbook         : {textbook}\n"
        "Minimum hours/yr : {jam}\n"
        "Week             : {minggu}   Day: {hari}\n"
        "Class            : {kelas}   Date: {tarikh}   Time: {masa}\n"
        "Duration         : {tempoh} min   No. of pupils: {bil}   Proficiency: {tahap}\n\n"
        "Theme            : {theme}\n"
        "Topic / Unit     : {topic}\n"
        "Skill            : {bk} {bn}\n"
        "Content Standard : {sk_k} {sk_n}\n"
        "Learning Standard(s):\n{ls}\n\n"
        "21st Century Learning strategy : {strategi}\n"
        "Cross-Curricular Elements (CCE) : {emk}\n"
        "HOTS target      : {kbat}"
    ).format(
        cefr=meta.get("cefr_target", "B1 Low"),
        textbook=meta.get("textbook", ""),
        jam=meta.get("min_hours_per_year", 144),
        minggu=inputs.get("minggu", ""),
        hari=inputs.get("hari", ""),
        kelas=inputs.get("nama_kelas", ""),
        tarikh=inputs.get("tarikh", ""),
        masa=inputs.get("masa", ""),
        tempoh=inputs.get("tempoh", ""),
        bil=inputs.get("bil_murid", ""),
        tahap=inputs.get("tahap_murid", ""),
        theme=inputs.get("theme", ""),
        topic=inputs.get("topic", ""),
        bk=cur["bidang"]["kod"] if cur["bidang"] else "",
        bn=cur["bidang"]["nama"] if cur["bidang"] else "",
        sk_k=cur["sk"]["kod"] if cur["sk"] else "",
        sk_n=cur["sk"]["nama"] if cur["sk"] else "",
        ls=ls_lines,
        strategi=", ".join(inputs.get("strategi", [])),
        emk=", ".join(inputs.get("emk", [])),
        kbat=inputs.get("kbat", ""),
    )


def generate_rph(inputs):
    cur = find_curriculum(inputs)
    system_prompt = read_text(os.path.join(PROMPT_DIR, "agent1_rph.md"))
    context = build_context_block(inputs, cur)
    nota = inputs.get("nota_guru", "").strip()
    user_prompt = "== LESSON CONTEXT ==\n" + context
    if nota:
        user_prompt += "\n\n== TEACHER IMPROVEMENT NOTES ==\n" + nota
    user_prompt += "\n\nGenerate a complete Daily Lesson Plan in JSON format as instructed."
    rph = call_llm_json(system_prompt, user_prompt, max_tokens=8000)
    rph, laporan = guardrail.check_rph(rph, inputs, cur)
    return {"rph": rph, "konteks": cur_summary(cur, inputs),
            "_guardrail": laporan, "_enjin": last_engine()}


def generate_materials(inputs):
    """Agent 2: turn the approved lesson plan into ready-to-teach slides
    (teaching aids / 'bahan bantu mengajar')."""
    cur = find_curriculum(inputs)
    plan = inputs.get("plan", {}) or {}
    system_prompt = read_text(os.path.join(PROMPT_DIR, "agent2_materials.md"))
    sp = "; ".join(plan.get("standard_pembelajaran", []) or [])
    obj = "\n".join("- " + o for o in (plan.get("objektif_pembelajaran", []) or []))
    act = "\n".join("- " + a for a in (plan.get("aktiviti_pembelajaran", []) or []))
    user_prompt = (
        "== LESSON PLAN ==\n"
        "Class: {kelas}\nTheme/Field: {tema}\nTopic/Unit: {topic}\n"
        "Skill: {skill}\nContent Standard: {sk}\n"
        "Learning Standards: {sp}\n\n"
        "Objectives:\n{obj}\n\nPlanned activities:\n{act}\n\n"
        "Create the teaching slides in JSON as instructed."
    ).format(
        kelas=plan.get("tingkatan_kelas", "") or inputs.get("nama_kelas", ""),
        tema=plan.get("tema_bidang", "") or inputs.get("theme", ""),
        topic=inputs.get("topic", ""),
        skill=cur["bidang"]["nama"] if cur["bidang"] else "",
        sk=("{} {}".format(cur["sk"]["kod"], cur["sk"]["nama"]) if cur["sk"] else ""),
        sp=sp, obj=obj or "(see plan)", act=act or "(see plan)",
    )
    note = inputs.get("nota_guru", "").strip()
    if note:
        user_prompt += "\n\n== TEACHER IMPROVEMENT NOTES ==\n" + note
    materials = call_llm_json(system_prompt, user_prompt, max_tokens=6000)
    return {"materials": materials, "konteks": cur_summary(cur, inputs)}


def _gamma_key():
    """Gamma API key: env var GAMMA_API_KEY, or gamma_apikey.txt in the project folder."""
    key = os.environ.get("GAMMA_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(os.path.join(ROOT, "gamma_apikey.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except FileNotFoundError:
        pass
    return ""


GAMMA_URL = "https://public-api.gamma.app/v1.0/generations"


def generate_gamma(inputs):
    """Agent 2 (Gamma helper): send the lesson plan + slides to Gamma AI, which designs a
    polished presentation / document / webpage. Polls until the deck is ready.
    Needs a Gamma Pro API key in gamma_apikey.txt (or GAMMA_API_KEY env var)."""
    key = _gamma_key()
    if not key:
        return {"ok": False, "error": "No Gamma API key yet - paste your key into "
                "gamma_apikey.txt (Gamma -> Account settings -> API keys, Pro plan)."}

    plan = inputs.get("plan", {}) or {}
    mat = inputs.get("materials", {}) or {}
    fmt = (inputs.get("format") or "presentation").strip().lower()
    if fmt not in ("presentation", "document", "social"):
        fmt = "presentation"

    # Build the source text from the lesson plan + planned teaching slides.
    dskp_meta = load_dskp(inputs.get("form", 3))
    course_label = "KSSM English Form {} (CEFR {})".format(
        dskp_meta.get("form", inputs.get("form", 3)), dskp_meta.get("cefr_target", "B1"))
    lines = ["# " + (plan.get("tajuk") or "English Lesson")]
    meta = [plan.get("tema_bidang", ""), plan.get("tingkatan_kelas", ""),
            plan.get("tarikh", ""), course_label]
    lines.append(" | ".join(x for x in meta if x))
    if plan.get("objektif_pembelajaran"):
        lines.append("\n## Learning objectives")
        lines += ["- " + o for o in plan["objektif_pembelajaran"]]
    slides = mat.get("slides", []) or []
    for s in slides:
        lines.append("\n## " + (s.get("tajuk") or "Slide"))
        lines += ["- " + i for i in (s.get("isi") or [])]
        if s.get("nota_guru"):
            lines.append("(Teacher note: " + s["nota_guru"] + ")")
    if not slides and plan.get("aktiviti_pembelajaran"):
        lines.append("\n## Lesson activities")
        lines += ["- " + a for a in plan["aktiviti_pembelajaran"]]
    input_text = "\n".join(lines)[:20000]

    payload = {
        "inputText": input_text,
        "textMode": "preserve",
        "format": fmt,
        "numCards": max(4, min(20, len(slides) + 2)),
        "additionalInstructions": (
            "This is a lesson for Malaysian Form {} secondary school pupils "
            "(KSSM English, CEFR {}). Keep the language simple, visual and "
            "classroom-friendly. Keep the given content faithful.".format(
                dskp_meta.get("form", inputs.get("form", 3)),
                dskp_meta.get("cefr_target", "B1"))),
        "imageOptions": {"source": "aiGenerated"},
        "textOptions": {"language": "en"},
    }
    if fmt == "presentation":
        payload["exportAs"] = "pptx"

    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    req = urllib.request.Request(
        GAMMA_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "X-API-KEY": key,
                 "accept": "application/json", "user-agent": ua},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            start = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        hint = ""
        if e.code in (401, 403):
            hint = " (check the API key / Pro-plan access)"
        return {"ok": False, "error": "Gamma API error {}{}: {}".format(e.code, hint, detail)}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "error": "Cannot reach Gamma: {}".format(e)}

    gen_id = start.get("generationId") or start.get("id")
    if not gen_id:
        return {"ok": False, "error": "Gamma gave no generation id: " + json.dumps(start)[:300]}

    # Poll until the deck is ready (Gamma usually takes 30-90 s).
    for _ in range(60):
        time.sleep(3)
        req = urllib.request.Request(GAMMA_URL + "/" + str(gen_id),
                                     headers={"X-API-KEY": key,
                                              "accept": "application/json",
                                              "user-agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                st = json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - transient poll errors are fine
            continue
        status = (st.get("status") or "").lower()
        if status in ("completed", "complete", "succeeded"):
            return {"ok": True, "url": st.get("gammaUrl") or st.get("url") or "",
                    "export_url": st.get("exportUrl") or "",
                    "credits": (st.get("credits") or {}).get("remaining")}
        if status in ("failed", "error"):
            return {"ok": False, "error": "Gamma generation failed: " + json.dumps(st)[:300]}
    return {"ok": False, "error": "Gamma timed out after 3 minutes - check gamma.app, "
            "the deck may still appear in your account."}


def materials_summary(mat):
    """Compact text of the teaching slides, to anchor worksheet questions."""
    if isinstance(mat, str):
        return mat[:3000]
    if not isinstance(mat, dict):
        return ""
    lines = []
    for s in (mat.get("slides", []) or [])[:12]:
        isi = "; ".join(s.get("isi", []) or [])
        t = s.get("tajuk", "")
        lines.append("- {}: {}".format(t, isi) if isi else "- " + t)
    return "\n".join(lines)[:3000]


def _agihan_aras(n, lots, mots, hots):
    """Tukar peratus agihan aras → bilangan soalan setiap aras (jumlah = n)."""
    n_lots = round(n * lots / 100)
    n_mots = round(n * mots / 100)
    n_hots = max(0, n - n_lots - n_mots)  # baki, elak ralat pembundaran
    return {"LOTS": n_lots, "MOTS": n_mots, "HOTS": n_hots}


def generate_worksheet(inputs):
    """Setiap worksheet mendapat soalan AI yang segar.

    1. Kira sasaran soalan setiap aras.
    2. AI jana SEMUA soalan (tiada guna semula dari Bank Soalan), supaya murid
       tidak menerima soalan berulang antara satu worksheet dengan yang lain.
    3. Worksheet yang guru luluskan tetap ditambah ke Bank Soalan (lihat
       save_artifact) — bank terus membesar sebagai rekod, cuma tidak dibaca
       semula di sini.
    """
    cur = find_curriculum(inputs)
    ws = inputs.get("worksheet", {})
    sp_lines = "\n".join("  {} {}".format(s["kod"], s["huraian"]) for s in cur["sp"])
    sp_kods = [s["kod"] for s in cur["sp"]]
    nota = inputs.get("nota_guru", "").strip()

    n = int(ws.get("bil_soalan", 10) or 10)
    sasaran = _agihan_aras(
        n, int(ws.get("lots", 40)), int(ws.get("mots", 40)), int(ws.get("hots", 20))
    )

    # (2) Tiada guna semula dari Bank Soalan — setiap worksheet 100% soalan baharu.
    dari_bank = []
    diperoleh = {a: 0 for a in sasaran}
    for q in dari_bank:
        diperoleh[q.get("aras", "MOTS")] = diperoleh.get(q.get("aras", "MOTS"), 0) + 1
    gap = {a: max(0, sasaran[a] - diperoleh.get(a, 0)) for a in sasaran}
    gap_total = sum(gap.values())

    # (3) AI hanya menampung baki.
    dijana_ai = []
    ai_tajuk = ""
    ai_arahan = ""
    if gap_total > 0:
        system_prompt = read_text(os.path.join(PROMPT_DIR, "agent3_worksheet.md"))
        # Constrain vocabulary to the Cambridge B1 Preliminary list (and below)
        # so questions match the pupils' CEFR level.
        system_prompt += wordlist.prompt_block()
        elak = "\n".join("- " + q["soalan"] for q in dari_bank) or "(none)"
        user_prompt = (
            "Learning Standard(s) to be tested:\n{sp}\n\n"
            "Theme: {theme}   Topic/Unit: {topic}\n\n"
            "Generate EXACTLY this many NEW questions per cognitive level:\n"
            "  LOTS : {gl}\n  MOTS : {gm}\n  HOTS : {gh}\n"
            "Total new questions : {gt}\n"
            "Pupil proficiency : {tahap}\n\n"
            "IMPORTANT — do NOT produce questions similar to or overlapping in meaning "
            "with these existing ones:\n{elak}\n"
        ).format(
            sp=sp_lines,
            theme=inputs.get("theme", ""), topic=inputs.get("topic", ""),
            gl=gap["LOTS"], gm=gap["MOTS"], gh=gap["HOTS"], gt=gap_total,
            tahap=inputs.get("tahap_murid", ""), elak=elak,
        )
        # Konteks RPH — soalan MESTI selari dengan apa yang diajar dalam lesson ini.
        plan = inputs.get("plan") or {}
        if plan:
            user_prompt += (
                "\n== LESSON PLAN CONTEXT (every question MUST be about THIS "
                "lesson's topic and content — never an unrelated topic) ==\n"
                "Lesson title : {}\n"
                "Objectives   :\n{}\n"
                "Activities   :\n{}\n"
            ).format(
                plan.get("tajuk", ""),
                "\n".join("- " + o for o in (plan.get("objektif_pembelajaran") or [])) or "(none)",
                "\n".join("- " + a for a in (plan.get("aktiviti_pembelajaran") or [])) or "(none)",
            )
        mat = inputs.get("materials")
        if mat:
            user_prompt += (
                "\n== TAUGHT MATERIAL (base the questions on what pupils were "
                "actually taught in these slides) ==\n" + materials_summary(mat) + "\n"
            )
        if nota:
            user_prompt += "\n== TEACHER IMPROVEMENT NOTES ==\n" + nota
        user_prompt += "\n\nGenerate the multiple-choice worksheet in JSON format as instructed."
        ws_ai = call_llm_json(system_prompt, user_prompt, max_tokens=8000)
        if isinstance(ws_ai, dict):
            dijana_ai = ws_ai.get("soalan", []) or []
            ai_tajuk = (ws_ai.get("tajuk") or "").strip()
            ai_arahan = (ws_ai.get("arahan_murid") or "").strip()

    # Gabung (bank dahulu) + nombor semula, hadkan kepada n.
    gabung = (list(dari_bank) + list(dijana_ai))[:n]
    for i, q in enumerate(gabung, 1):
        q["no"] = i
    worksheet = {
        "tajuk": ai_tajuk or ("Worksheet — " + (cur["sk"]["nama"] if cur["sk"] else "English Form 3")),
        "arahan_murid": ai_arahan,
        "jumlah_soalan": len(gabung),
        "jumlah_markah": sum(int(q.get("markah", 1) or 1) for q in gabung),
        "soalan": gabung,
        "_sumber": {"dari_bank": len(dari_bank), "dijana_ai": len(dijana_ai)},
    }
    worksheet, laporan = guardrail.check_worksheet(worksheet, sp_kods)
    # Flag any words above CEFR B1 so the teacher can review them before sending.
    vocab_flags = wordlist.check_worksheet(worksheet)
    if vocab_flags:
        laporan["vocab"] = vocab_flags
    return {"worksheet": worksheet, "konteks": cur_summary(cur, inputs),
            "_guardrail": laporan, "_enjin": last_engine()}


def cur_summary(cur, inputs):
    return {
        "bidang": "{} {}".format(cur["bidang"]["kod"], cur["bidang"]["nama"]) if cur["bidang"] else "",
        "sk": "{} {}".format(cur["sk"]["kod"], cur["sk"]["nama"]) if cur["sk"] else "",
        "sp": ["{} {}".format(s["kod"], s["huraian"]) for s in cur["sp"]],
        "kelas": inputs.get("nama_kelas", ""),
        "tarikh": inputs.get("tarikh", ""),
    }


def save_artifact(body):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    jenis = re.sub(r"[^a-z0-9_]", "", (body.get("jenis", "artifak")).lower())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    kelas = re.sub(r"[^A-Za-z0-9]+", "-", body.get("kelas", "")).strip("-")
    name = "{}_{}_{}.json".format(jenis, kelas or "kelas", stamp)
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body.get("kandungan", {}), f, ensure_ascii=False, indent=2)
    hasil = {"disimpan": True, "fail": "output/" + name}

    # Worksheet yang guru SETUJU → masukkan ke Bank Soalan.
    # Soalan baharu (tiada id) ditambah; soalan sedia ada dari bank ditanda diguna.
    if body.get("jenis") == "worksheet":
        kandungan = body.get("kandungan", {})
        soalan = kandungan.get("soalan", []) if isinstance(kandungan, dict) else []
        baharu = [q for q in soalan if not q.get("id")]
        diguna = [q.get("id") for q in soalan if q.get("id")]
        ditambah = bank.add_questions(baharu, status="diluluskan",
                                      topic=body.get("topic", ""),
                                      theme=body.get("theme", ""))
        bank.mark_used(diguna)
        hasil["bank"] = {"ditambah": ditambah, "diguna_semula": len(diguna)}
    return hasil


# --------------------------------------------------------------------------
# Pengendali HTTP
# --------------------------------------------------------------------------
def save_lesson_route(body):
    return {"id": lessons.save_lesson(body, owner_username=body.get("_actor_username"))}


def delete_lesson_route(body):
    return lessons.delete_lesson(body.get("id"), owner_username=body.get("_actor_username"))


def generate_reflection(inputs):
    """Agent 4: turn class results + the lesson into an RPH reflection + a teacher report."""
    plan = inputs.get("plan", {}) or {}
    results = (inputs.get("results", "") or "").strip()
    score = (inputs.get("score_avg", "") or "").strip()
    system_prompt = read_text(os.path.join(PROMPT_DIR, "agent4_reflection.md"))
    sp = "; ".join(plan.get("standard_pembelajaran", []) or [])
    obj = "; ".join(plan.get("objektif_pembelajaran", []) or [])
    user_prompt = (
        "== LESSON ==\n"
        "Class: {kelas}\nTopic: {tajuk}\nTheme: {tema}\n"
        "Learning Standards: {sp}\nObjectives: {obj}\n\n"
        "== CLASS RESULTS / TEACHER NOTES ==\n"
        "Average score: {score}\n{results}\n\n"
        "Write the reflection and report in JSON as instructed."
    ).format(
        kelas=plan.get("tingkatan_kelas", ""), tajuk=plan.get("tajuk", ""),
        tema=plan.get("tema_bidang", ""), sp=sp, obj=obj,
        score=score or "(not given)", results=results or "(no extra notes)",
    )
    return call_llm_json(system_prompt, user_prompt, max_tokens=2000)


def build_reflection_markdown(body):
    """Render a standalone, human-readable reflection report (Markdown) from a
    lesson plan + the AI/teacher reflection + class report + quiz results.
    Shared by the 'save report file' and 'email report' actions."""
    plan = body.get("plan", {}) or {}
    refleksi = (body.get("refleksi") or "").strip()
    report = (body.get("report") or "").strip()
    score = str(body.get("score") or "").strip()
    respondents = str(body.get("respondents") or "").strip()
    results = (body.get("results") or "").strip()
    weakest = body.get("weakest") or []
    per_student = body.get("per_student") or []
    school = (body.get("school") or "").strip()

    sp = plan.get("standard_pembelajaran") or []
    obj = plan.get("objektif_pembelajaran") or []

    lines = []
    if school:
        lines.append("**{}**".format(school))
    lines.append("# Reflection & Class Report — {}".format(
        plan.get("tajuk") or "English Lesson"))
    lines.append("")

    meta = []
    if plan.get("tingkatan_kelas"):
        meta.append("**Class:** " + plan["tingkatan_kelas"])
    if plan.get("tarikh"):
        meta.append("**Date:** " + plan["tarikh"])
    if plan.get("tema_bidang"):
        meta.append("**Theme:** " + plan["tema_bidang"])
    if meta:
        lines.append("  ·  ".join(meta))
    if sp:
        lines.append("**Learning Standards:** " + "; ".join(sp))
    if obj:
        lines.append("**Objectives:** " + "; ".join(obj))
    perf = []
    if score:
        perf.append("**Average score:** {}%".format(score))
    if respondents:
        perf.append(respondents + " pupils responded")
    if perf:
        lines.append("  ·  ".join(perf))
    lines.append("")

    lines.append("## Reflection (for the RPH)")
    lines.append(refleksi or "_(no reflection written yet)_")
    lines.append("")

    if report:
        lines.append("## Class report")
        lines.append(report)
        lines.append("")

    if weakest:
        lines.append("## Weakest questions")
        for w in weakest:
            lines.append("- Q{} — {}% correct".format(
                w.get("q", "?"), w.get("correct_percent", "?")))
        lines.append("")

    if per_student:
        lines.append("## Per-pupil results")
        lines.append("| Pupil | Score | % |")
        lines.append("| --- | ---: | ---: |")
        for s in per_student:
            lines.append("| {} | {}/{} | {}% |".format(
                s.get("email", "(anonymous)"), s.get("score", ""),
                s.get("max", ""), s.get("percent", "")))
        lines.append("")

    if results and not report:
        lines.append("## Notes")
        lines.append(results)
        lines.append("")

    lines.append("---")
    lines.append("_Generated by Niat on {}._".format(
        datetime.now().strftime("%Y-%m-%d %H:%M")))
    return "\n".join(lines).strip() + "\n"


def reflection_report(body):
    """Build a standalone Markdown reflection report, save a copy to output/,
    and return its text so the browser can download it too."""
    md = build_reflection_markdown(body)
    plan = body.get("plan", {}) or {}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    kelas = re.sub(r"[^A-Za-z0-9]+", "-",
                   plan.get("tingkatan_kelas", "")).strip("-")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "reflection_{}_{}.md".format(kelas or "class", stamp)
    with open(os.path.join(OUTPUT_DIR, filename), "w", encoding="utf-8") as f:
        f.write(md)
    return {"ok": True, "filename": filename, "markdown": md,
            "saved": "output/" + filename}


def email_reflection(body):
    """Email the reflection report to the teacher (via the Niat Hub's mail
    action — the same HTTPS path used for reminders). The recipient is supplied
    explicitly by the teacher; nothing is sent without an address."""
    to = (body.get("to") or "").strip()
    if "@" not in to or "." not in to.split("@")[-1]:
        return {"ok": False, "error": "Please enter a valid recipient email address."}
    md = build_reflection_markdown(body)
    plan = body.get("plan", {}) or {}
    subject = "Reflection & Class Report"
    bits = [plan.get("tingkatan_kelas"), plan.get("tajuk")]
    tail = " — ".join(b for b in bits if b)
    if tail:
        subject += " — " + tail
    res = _post_hub({"action": "mail", "to": to, "subject": subject, "body": md})
    if res.get("ok"):
        res["to"] = to
    return res


def lesson_reflection_route(body):
    return lessons.update_reflection(
        int(body.get("id")), body.get("refleksi", ""), body.get("score"),
        owner_username=body.get("_actor_username"))


def distribute_direct(body):
    """Path B (direct Google API) — dormant scaffold; inert until client_secret.json exists."""
    try:
        import niat_google
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "Path B module error: " + str(e)}
    if not niat_google.available():
        return {"ok": False, "error": "Path B is not set up yet — see PATH_B_SETUP.md "
                "(needs client_secret.json + the google libraries)."}
    return niat_google.distribute(
        body.get("worksheet", {}), body.get("class_name", ""),
        body.get("due_iso", ""), body.get("max_points"))


# ==========================================================================
# Agent 5 — Differentiated distribution
# Reads each pupil's cumulative performance, DECIDES a level per pupil, then
# generates one worksheet per level and (fully automatic) posts each level to
# its own pupils in the same Google Classroom.
# ==========================================================================
BAND_ORDER = ["remedial", "core", "extension"]

# CEFR ladder used to place each Form's differentiation bands relative to its
# own target level. "core" = the Form's CEFR target; "remedial" = one step down;
# "extension" = one step up. This keeps differentiation correct for Forms 1-5
# instead of assuming every class sits at Form 3's B1.
CEFR_LADDER = ["A1", "A2 Low", "A2 Mid", "A2 High",
               "B1 Low", "B1 Mid", "B1 High", "B2 Low", "B2 Mid"]


def _norm_cefr(c):
    """Normalise a cefr_target string ('A2 Mid (Revised)', 'B1+') to a ladder rung."""
    c = (c or "").strip()
    if c.endswith("+"):  # e.g. "B1+" -> next rung up from B1 (handled by caller)
        c = c[:-1].strip()
    for lvl in CEFR_LADDER:
        if c.upper().startswith(lvl.upper()):
            return lvl
    # fall back on the base band letter (A2 / B1) if the sub-level is unusual
    for lvl in CEFR_LADDER:
        if c[:2].upper() == lvl[:2].upper():
            return lvl
    return "B1 Low"


def band_cefr_for_form(form):
    """Return {remedial, core, extension} CEFR labels for a given Form (1-5)."""
    core = _norm_cefr(load_dskp(form).get("cefr_target", "B1 Low"))
    try:
        i = CEFR_LADDER.index(core)
    except ValueError:
        i = CEFR_LADDER.index("B1 Low")
    return {
        "remedial": CEFR_LADDER[max(0, i - 1)],
        "core": core,
        "extension": CEFR_LADDER[min(len(CEFR_LADDER) - 1, i + 1)],
    }

# Per-band cognitive split (LOTS/MOTS/HOTS %). The proficiency label and the
# worksheet-agent note are built per Form by band_shape() so the CEFR pitch
# matches the class's actual level (Form 1 A2 … Form 5 B1 High), not a fixed B1.
# Differentiation is by cognitive demand and scaffolding at the class's own
# vocabulary level — it does not break the project's word-level constraint.
_BAND_COG = {
    "remedial": {"lots": 70, "mots": 30, "hots": 0},
    "core": {"lots": 40, "mots": 40, "hots": 20},
    "extension": {"lots": 10, "mots": 40, "hots": 50},
}


def band_shape(band, form=3):
    """Full shaping for a band at a given Form: cognitive split + CEFR-aware
    proficiency label ('tahap') + differentiation note for the worksheet agent."""
    cog = _BAND_COG[band]
    cefrs = band_cefr_for_form(form)
    cefr, core = cefrs[band], cefrs["core"]
    if band == "remedial":
        tahap = "Lower — CEFR {}; pupils are struggling and need support".format(cefr)
        nota = ("DIFFERENTIATION — REMEDIAL ({c}): Use the simplest {core}-or-below "
                "vocabulary, short sentences, and clear scaffolding. Focus on recall "
                "and basic understanding. Keep stems short and add a small hint where "
                "helpful. Avoid inference-heavy or multi-step questions."
                ).format(c=cefr, core=core)
    elif band == "core":
        tahap = "On-level — CEFR {} (expected Form {} standard)".format(cefr, form)
        nota = ("DIFFERENTIATION — CORE ({c}): Standard Form {f} pitch. Balanced mix of "
                "recall, understanding and some application.").format(c=cefr, f=form)
    else:  # extension
        tahap = "Higher — CEFR {}; pupils are secure and ready for a challenge".format(cefr)
        nota = ("DIFFERENTIATION — EXTENSION ({c}): Keep within the class's core ({core}) "
                "vocabulary level but raise the cognitive demand — richer/longer texts, "
                "inference, analysis, and 'why/how' reasoning. More HOTS questions."
                ).format(c=cefr, core=core)
    return {"lots": cog["lots"], "mots": cog["mots"], "hots": cog["hots"],
            "tahap": tahap, "nota": nota, "cefr": cefr}


def _decide_bands(cumulative, form=3):
    """Agent 5: given cumulative per-pupil performance, return
    {emel: {band, cefr, sebab}} plus a summary. LLM first; if it fails or returns
    junk, fall back to a deterministic threshold rule so distribution still works.
    CEFR labels are pitched to the class's Form."""
    band_cefr = band_cefr_for_form(form)
    lines = []
    for s in cumulative:
        lines.append(
            "- {emel} | name: {nama} | average: {purata}% over {bil} quiz(zes) | "
            "recent: {terkini} | trend: {trend}".format(
                emel=s["emel"], nama=s["nama"], purata=s["purata"],
                bil=s["bil"], terkini=s["terkini"], trend=s["trend"]))
    roster = "\n".join(lines)
    decided, summary = {}, ""
    try:
        system_prompt = read_text(os.path.join(PROMPT_DIR, "agent5_differentiation.md"))
        user_prompt = ("Assign a differentiation band to every pupil below.\n\n"
                       "== CLASS PERFORMANCE ==\n" + roster +
                       "\n\nReturn JSON only.")
        data = call_llm_json(system_prompt, user_prompt, max_tokens=3000)
        if isinstance(data, dict):
            summary = (data.get("ringkasan") or "").strip()
            for a in data.get("assignments", []) or []:
                emel = (a.get("emel") or "").strip().lower()
                band = (a.get("band") or "").strip().lower()
                if emel and band in _BAND_COG:
                    decided[emel] = {"band": band,
                                     "cefr": band_cefr[band],
                                     "sebab": (a.get("sebab") or "").strip()}
    except Exception:  # noqa: BLE001 — any failure drops to the rule below
        decided = {}

    # Deterministic fallback / fill gaps for any pupil the agent skipped.
    for s in cumulative:
        if s["emel"] in decided:
            continue
        p = s["purata"]
        band = "remedial" if p < 50 else ("core" if p < 80 else "extension")
        decided[s["emel"]] = {"band": band, "cefr": band_cefr[band],
                              "sebab": "Average {}% (auto by threshold).".format(p)}
    if not summary:
        counts = {b: 0 for b in BAND_ORDER}
        for v in decided.values():
            counts[v["band"]] += 1
        summary = ", ".join("{} {}".format(counts[b], b) for b in BAND_ORDER)
    return decided, summary


def _worksheet_for_band(base_inputs, band):
    """Generate one worksheet pitched at `band` by reshaping the worksheet config
    and letting Agent 3 (generate_worksheet) do the work."""
    shape = band_shape(band, base_inputs.get("form", 3))
    inputs = dict(base_inputs)
    ws = dict(inputs.get("worksheet", {}) or {})
    ws["lots"], ws["mots"], ws["hots"] = shape["lots"], shape["mots"], shape["hots"]
    inputs["worksheet"] = ws
    inputs["tahap_murid"] = shape["tahap"]
    # Prepend the level instruction to any existing teacher note. A note also
    # tells generate_worksheet to generate fresh (not reuse the bank), which is
    # what we want so each level is genuinely different.
    nota = (base_inputs.get("nota_guru") or "").strip()
    inputs["nota_guru"] = shape["nota"] + (("\n\n" + nota) if nota else "")
    out = generate_worksheet(inputs)
    ws_out = out.get("worksheet", {}) or {}
    base_title = ws_out.get("tajuk") or "Worksheet"
    ws_out["tajuk"] = "{} — {} ({})".format(base_title, band.title(), shape["cefr"])
    return ws_out


def differentiate(body):
    """Fully-automatic differentiated distribution (Agent 5).

    Steps: read the class's cumulative performance → decide a band per pupil →
    generate one worksheet per band that has pupils → post each band to its own
    pupils in Google Classroom. If Google (Path B) is not set up, everything up
    to posting still runs and is returned as a preview (dry run)."""
    class_name = (body.get("class_name") or body.get("kelas") or "").strip()
    if not class_name:
        return {"ok": False, "error": "No class specified."}

    cumulative = prestasi_murid.cumulative_by_student(class_name)
    if not cumulative:
        return {"ok": False, "error": "No performance data yet for \"{}\". Read at "
                "least one quiz's results for this class first (Reflect step).".format(class_name)}

    form = body.get("form", 3)
    band_cefr = band_cefr_for_form(form)

    # Teacher override: if the caller supplies its own band per pupil (from the
    # editable preview table), honour it instead of re-running the agent. Any
    # pupil left out is filled from the agent/threshold decision.
    override = {}
    for a in body.get("assignments") or []:
        emel = (a.get("emel") or "").strip().lower()
        band = (a.get("band") or "").strip().lower()
        if emel and band in _BAND_COG:
            override[emel] = band
    if override:
        decided = {}
        for s in cumulative:
            band = override.get(s["emel"])
            if band:
                decided[s["emel"]] = {"band": band, "cefr": band_cefr[band],
                                      "sebab": "Teacher-set level."}
        # fill anyone the teacher didn't touch
        for emel, d in _decide_bands(cumulative, form)[0].items():
            decided.setdefault(emel, d)
        summary = "Teacher-adjusted differentiation plan."
    else:
        decided, summary = _decide_bands(cumulative, form)

    # Group pupils by band and attach the rationale for the teacher-facing table.
    by_band = {b: [] for b in BAND_ORDER}
    assignments = []
    perf = {s["emel"]: s for s in cumulative}
    for emel, d in decided.items():
        by_band[d["band"]].append(emel)
        assignments.append({
            "emel": emel, "nama": perf.get(emel, {}).get("nama", emel),
            "purata": perf.get(emel, {}).get("purata"),
            "band": d["band"], "cefr": d["cefr"], "sebab": d["sebab"],
        })
    assignments.sort(key=lambda a: (BAND_ORDER.index(a["band"]), a["emel"]))

    # Step 1 (preview): return the proposed levels so the teacher can adjust
    # before anything is generated or posted. Nothing irreversible happens here.
    if body.get("decide_only"):
        return {"ok": True, "class_name": class_name, "ringkasan": summary,
                "assignments": assignments, "decided_only": True}

    # Generate one worksheet per band that actually has pupils.
    bands_payload = []
    for band in BAND_ORDER:
        emails = by_band[band]
        if not emails:
            continue
        worksheet = _worksheet_for_band(body, band)
        bands_payload.append({"band": band, "cefr": band_cefr[band],
                              "emails": emails, "worksheet": worksheet})

    result = {"ok": True, "class_name": class_name, "ringkasan": summary,
              "assignments": assignments,
              "bands": [{"band": b["band"], "cefr": b["cefr"],
                         "bil_murid": len(b["emails"]),
                         "worksheet": b["worksheet"]} for b in bands_payload]}

    # Fully automatic: post to Google Classroom if Path B is ready.
    try:
        import niat_google
    except Exception as e:  # noqa: BLE001
        result["distribute"] = {"ok": False, "error": "Path B module error: " + str(e)}
        return result
    if not niat_google.available():
        result["distribute"] = {"ok": False, "dry_run": True,
                                 "error": "Google (Path B) not set up — levels decided "
                                 "and worksheets generated, but nothing was posted. "
                                 "See PATH_B_SETUP.md."}
        return result
    result["distribute"] = niat_google.distribute_differentiated(
        class_name, bands_payload,
        due_iso=body.get("due_iso", ""), max_points=body.get("max_points"))
    return result


def _read_reminder_cfg():
    """Reminder/integration settings: local file first, environment overrides.

    Cloud Run supplies these through Secret Manager-backed environment
    variables because reminder_config.txt is intentionally never deployed.
    """
    cfg = {}
    try:
        with open(os.path.join(ROOT, "reminder_config.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    for key in (
            "SENDER_EMAIL", "SENDER_APP_PASSWORD", "TEACHER_EMAIL",
            "REMINDER_HOST", "TEACHER_WHATSAPP", "CALLMEBOT_APIKEY",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "APPSCRIPT_MAIL_URL", "APPSCRIPT_MAIL_KEY",
            "APPSCRIPT_HUB_URL", "APPSCRIPT_HUB_KEY"):
        if os.environ.get(key) is not None:
            cfg[key] = os.environ.get(key, "").strip()
    return cfg


def _load_classrooms():
    """Load classrooms from Supabase (if configured) or local JSON file.
    Returns: {"lesson_plan": "...", "classes": {"3 Delima": "...", ...}}"""
    if sb.use_cloud():
        try:
            rows = sb.select("classrooms", params={"select": "*"})
            result = {"classes": {}}
            for row in rows:
                class_name = row.get("class_name", "")
                classroom_id = row.get("classroom_id", "")
                if class_name == "lesson_plan":
                    result["lesson_plan"] = classroom_id
                else:
                    result["classes"][class_name] = classroom_id
            return result
        except sb.SupabaseError:
            if sb.cloud_required():
                raise
            pass  # fall through to local file in desktop auto mode
    # Fallback to local JSON
    try:
        with open(os.path.join(ROOT, "classrooms.json"), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _post_hub(payload):
    """POST to the teacher's Niat Hub web app (Apps Script). Returns its JSON."""
    cfg = _read_reminder_cfg()
    url = cfg.get("APPSCRIPT_HUB_URL", "").strip()
    if not url:
        return {"ok": False, "error": "One-time setup needed: deploy niat_hub.gs "
                "(open the file for the 5 steps), then put APPSCRIPT_HUB_URL in "
                "reminder_config.txt."}
    payload["key"] = cfg.get("APPSCRIPT_HUB_KEY", "")
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"content-type": "application/json"})
    try:
        # Apps Script boleh ambil masa (cipta Doc/Form) — beri masa panjang.
        with urllib.request.urlopen(req, timeout=180) as r:
            text = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "Hub error {}: {}".format(
            e.code, e.read().decode("utf-8", "replace")[:200])}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "error": "Cannot reach the hub: {}".format(e)}
    try:
        return json.loads(text)
    except ValueError:
        return {"ok": False, "error": "Hub gave a non-JSON reply (check the "
                "deployment is 'Anyone' access): " + text[:200]}


def _plan_rows(plan):
    """RPH dict -> 2-column table rows for the Google Doc (plain Perlis format)."""
    plan = plan or {}
    g = lambda k: str(plan.get(k, "") or "")
    obj = "\n".join("{}. {}".format(i, o) for i, o in
                    enumerate(plan.get("objektif_pembelajaran", []) or [], 1))
    akt = "\n".join("{}. {}".format(i, a) for i, a in
                    enumerate(plan.get("aktiviti_pembelajaran", []) or [], 1))
    sp = "\n".join(plan.get("standard_pembelajaran", []) or [])
    return [
        ["MINGGU", g("minggu")], ["TARIKH", g("tarikh")], ["HARI", g("hari")],
        ["MASA", g("masa")], ["TINGKATAN / KELAS", g("tingkatan_kelas")],
        ["MINIMUM JAM SETAHUN", g("minimum_jam_setahun")],
        ["MATA PELAJARAN", g("mata_pelajaran")],
        ["TEMA / BIDANG", g("tema_bidang")], ["TAJUK", g("tajuk")],
        ["STANDARD KANDUNGAN", g("standard_kandungan")],
        ["STANDARD PEMBELAJARAN", sp],
        ["OBJEKTIF PEMBELAJARAN", "Pada akhir PdPc, murid boleh :\n" + obj],
        ["AKTIVITI PEMBELAJARAN", akt],
        ["REFLEKSI", g("refleksi")],
    ]


def classroom_lessonplan(body):
    """One click: RPH -> Doc+PDF -> the 'Lesson Plan' Classroom via the hub."""
    plan = body.get("plan") or {}
    course = (_load_classrooms() or {}).get("lesson_plan", "")
    title = "RPH — {} — {}".format(plan.get("tingkatan_kelas", "Class"),
                                   plan.get("tarikh", ""))
    return _post_hub({
        "action": "lessonplan", "courseId": course, "title": title,
        "school": body.get("school", ""), "rows": _plan_rows(plan),
    })


def classroom_materials(body):
    """One click: teaching slides -> Google Slides -> the chosen Classroom."""
    mat = body.get("materials") or {}
    slides = mat.get("slides") or []
    if not slides:
        return {"ok": False, "error": "No teaching materials yet - generate the slides first."}
    target = (body.get("target") or "").strip()
    cmap = _load_classrooms() or {}
    if target.lower().replace("_", " ") == "lesson plan":
        course = cmap.get("lesson_plan", "")
        target_label = "Lesson Plan - PRESTIJ Project"
    else:
        course = ""
        target_label = target
        for name, cid in (cmap.get("classes") or {}).items():
            if name.strip().lower() == target.lower() and cid:
                course = cid
                break
    if not course:
        return {"ok": False, "error": "No Classroom ID mapped for '{}'. Add it to "
                "classrooms.json.".format(target_label or "?")}
    plan = body.get("plan") or {}
    title = "Slides — " + (plan.get("tajuk") or "English Lesson")
    if plan.get("tingkatan_kelas"):
        title += " — " + plan["tingkatan_kelas"]
    return _post_hub({
        "action": "materials", "courseId": course, "title": title,
        "slides": [{"heading": s.get("tajuk", ""), "points": s.get("isi") or []}
                   for s in slides],
    })


def classroom_worksheet(body):
    """One click: worksheet -> Form quiz -> the pupils' Classroom + emails."""
    ws = body.get("worksheet") or {}
    class_name = (body.get("class_name") or "").strip()
    cls_map = (_load_classrooms() or {}).get("classes", {})
    course = ""
    for name, cid in cls_map.items():
        if name.strip().lower() == class_name.lower():
            course = cid
            break
    if not course:
        return {"ok": False, "error": "No Classroom ID mapped for '{}'. Add it to "
                "classrooms.json (current: {}).".format(class_name or "?",
                ", ".join(cls_map) or "none")}
    questions = [{
        "q": q.get("soalan", ""), "opts": q.get("pilihan", []),
        "answerIndex": "ABCD".find(str(q.get("jawapan_betul", "A"))[:1]),
        "points": int(q.get("markah", 1) or 1),
        "feedback": q.get("maklum_balas", ""),
    } for q in (ws.get("soalan") or [])]
    due_iso = ""
    if body.get("due_date") and body.get("due_time"):
        due_iso = "{}T{}:00+08:00".format(body["due_date"], body["due_time"])
    desc = (ws.get("arahan_murid") or "").strip() or \
        "Answer all questions and submit before the due date. Good luck!"
    if due_iso:
        desc += "\n\nDue: {} {}".format(body.get("due_date"), body.get("due_time"))
    return _post_hub({
        "action": "worksheet", "courseId": course, "dueIso": due_iso,
        "description": desc,
        "ws": {"title": ws.get("tajuk") or "English Quiz", "questions": questions,
               "points": ws.get("jumlah_markah") or len(questions)},
        "studentEmails": load_students().get("students", []),
    })


def quiz_results(body):
    """Read a distributed quiz's Google Form responses via the hub and return
    the class report (average %, weakest questions, per-student scores).

    Side effect: when the caller tells us which class this quiz belongs to, each
    pupil's score is banked in prestasi_murid.py so Agent 5 can later decide
    differentiated worksheet levels from the cumulative history."""
    res = _post_hub({
        "action": "results",
        "formId": (body.get("form_id") or "").strip(),
        "title": (body.get("title") or "").strip(),
    })
    class_name = (body.get("class_name") or body.get("kelas") or "").strip()
    if class_name and isinstance(res, dict) and res.get("per_student"):
        try:
            saved = prestasi_murid.record_scores(
                class_name, res.get("per_student"),
                topic=(body.get("topic") or "").strip(),
                sp=body.get("sp") or "",
                lesson_id=body.get("lesson_id") or "")
            res["prestasi_disimpan"] = saved
        except Exception as e:  # noqa: BLE001 — recording must never break results
            res["prestasi_ralat"] = str(e)
    return res


def _cloud_setting_get(key, default=None):
    """Read one durable JSON setting from Supabase."""
    rows = sb.select("app_settings", params={"select": "value", "key": "eq." + key})
    if not rows:
        return default
    value = rows[0].get("value")
    return value if value is not None else default


def _cloud_setting_set(key, value):
    """Upsert one durable JSON setting in Supabase."""
    sb.insert("app_settings", {
        "key": key,
        "value": value,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }, upsert_on="key")


def _timetable_setting_key(username):
    return "timetable:" + (username or "").strip().lower()


def _load_timetable(username):
    """Return one teacher's timetable without exposing another's data.

    Containers use the durable ``app_settings`` row ``timetable:<username>``.
    Desktop/offline mode retains the existing timetable.json layout.
    """
    if sb.use_cloud():
        try:
            return _cloud_setting_get(_timetable_setting_key(username), {}) or {}
        except sb.SupabaseError:
            if sb.cloud_required():
                raise
    try:
        with open(os.path.join(ROOT, "timetable.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return {}
    return (data.get("teachers") or {}).get(username, {})


def _enrich(c, pupils_map):
    """Attach the per-class pupil count to a timetable slot."""
    out = dict(c)
    out["pupils"] = pupils_map.get(c.get("class", ""), "")
    return out


def next_class(username):
    """Tomorrow's English class(es) + teacher/school profile — for one-tap auto-fill.
    Tallied against whoever is currently logged in — never someone else's classes."""
    tt = _load_timetable(username)
    pupils = tt.get("class_pupils", {}) or {}
    tomorrow = datetime.now() + timedelta(days=1)
    day = tomorrow.strftime("%A")
    classes = [_enrich(c, pupils) for c in tt.get("classes", [])
               if c.get("day", "").strip().lower() == day.lower()]
    return {
        "date": tomorrow.strftime("%Y-%m-%d"), "day": day,
        "teacher": tt.get("teacher_name", ""), "school": tt.get("school", ""),
        "classes": classes,
    }


def load_students():
    """Load students from Supabase (if configured) or 'Email Student Prototype.txt'.

    For local file: any line containing '@' is an email; the nearest non-empty
    line above it is the student's name. Teacher edits the txt file — no code change needed.
    """
    students = []
    if sb.use_cloud():
        try:
            # NOTE: the Supabase column is `label` ("Student A"), not `name`.
            rows = sb.select("students", params={"select": "label,email"})
            students = [{"name": row.get("label") or "Student",
                         "email": row.get("email") or ""} for row in rows]
            return {"students": students, "jumlah": len(students)}
        except sb.SupabaseError:
            if sb.cloud_required():
                raise
            pass  # fall through to local file in desktop auto mode
    # Fallback to local text file
    path = os.path.join(ROOT, "Email Student Prototype.txt")
    last_name = ""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "@" in line and "." in line.split("@")[-1]:
                    students.append({"name": last_name or "Student", "email": line})
                    last_name = ""
                else:
                    last_name = line
    except FileNotFoundError:
        pass
    return {"students": students, "jumlah": len(students)}


def class_lookup(body, username):
    """Return the timetable slot details for a given class name (any day) — for reminder-link prefill.
    Looked up against the CURRENT user's own timetable only."""
    tt = _load_timetable(username)
    pupils = tt.get("class_pupils", {}) or {}
    want = (body.get("class", "") if body else "").strip().lower()
    for c in tt.get("classes", []):
        if c.get("class", "").strip().lower() == want:
            return {"found": True, "slot": _enrich(c, pupils),
                    "teacher": tt.get("teacher_name", ""), "school": tt.get("school", "")}
    return {"found": False, "teacher": tt.get("teacher_name", ""), "school": tt.get("school", "")}


# --------------------------------------------------------------------------
# Admin: user management + oversight (all callers already role-checked in the
# handler via _require_admin, so these trust `actor_role` as verified).
# --------------------------------------------------------------------------
VALID_ROLES = ("teacher", "admin", "super_admin")
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")


# --------------------------------------------------------------------------
# Profile photos
#
# The photo belongs to the ACCOUNT, so Supabase Storage (private bucket
# "avatars") is the system of record and profiles.avatar_url remembers it.
# web/avatars/ is only a local cache — and the sole copy when Supabase is not
# configured (offline demo). It used to be the only home, which is why photos
# always vanished in the cloud: the folder is gitignored (so `gcloud run deploy
# --source .` never uploaded it) and Cloud Run wipes the disk on every restart.
#
# The bucket stays PRIVATE and the bytes are proxied back through
# GET /avatars/<user>.png, which sits behind the login gate — a public bucket
# would put teachers' faces on guessable, unauthenticated URLs.
# --------------------------------------------------------------------------
AVATAR_BUCKET = "avatars"
AVATAR_DIR = os.path.join(WEB_DIR, "avatars")


def _avatar_key(user):
    """Storage object name for a user, or None if the username could never be
    one — it lands in a URL path, so it is validated, not trusted."""
    return user + ".png" if USERNAME_RE.match(user or "") else None


def _avatar_cache_file(user):
    return os.path.join(AVATAR_DIR, user + ".png")


def _avatar_cache_write(user, png_bytes):
    """Best-effort: a read-only or full disk must never fail the upload."""
    try:
        os.makedirs(AVATAR_DIR, exist_ok=True)
        with open(_avatar_cache_file(user), "wb") as f:
            f.write(png_bytes)
    except OSError:
        pass


def avatar_save(user, png_bytes):
    """Store a new profile photo. Returns (app_url, warning) — warning is None
    on success, or a message to show the teacher when the photo could only be
    saved to this machine and so will not survive a cloud restart."""
    key = _avatar_key(user)
    if not key:
        raise ValueError("username cannot have a photo: " + repr(user))
    # ?v= busts the browser cache when the teacher replaces their photo; it is
    # a clock stamp, not the file mtime, because another Cloud Run instance
    # holds no file to read an mtime from.
    url = "/avatars/{}?v={}".format(key, int(time.time()))
    warning = None
    if sb.configured():
        try:
            sb.storage_create_bucket(AVATAR_BUCKET, public=False)
            sb.storage_upload(AVATAR_BUCKET, key, png_bytes, content_type="image/png")
            sb.update("profiles", {"username": "eq." + user}, {"avatar_url": url},
                      role="service")
        except sb.SupabaseError as e:
            if sb.cloud_required():
                raise
            # Keep the photo rather than lose it, but never let it look saved
            # when it is one restart away from disappearing — that silence is
            # exactly what made photos vanish before.
            warning = ("Saved on this computer only — Supabase could not be "
                       "reached, so the photo will not appear elsewhere or "
                       "survive a server restart. ({})".format(e))
    _avatar_cache_write(user, png_bytes)
    return url, warning


def avatar_url_for(user):
    """The URL to show for this user's photo, or None if they have none."""
    if not _avatar_key(user):
        return None
    if sb.configured():
        try:
            rows = sb.select("profiles", {"select": "avatar_url",
                                          "username": "eq." + user})
            if rows:
                return rows[0].get("avatar_url") or None
        except sb.SupabaseError:
            pass  # Supabase down — fall back to whatever is on this disk
    f = _avatar_cache_file(user)
    if os.path.isfile(f):
        return "/avatars/{}.png?v={}".format(user, int(os.path.getmtime(f)))
    return None


def avatar_bytes(user):
    """Raw PNG for this user — local cache first, then Supabase Storage.
    None if they have no photo."""
    key = _avatar_key(user)
    if not key:
        return None
    f = _avatar_cache_file(user)
    if os.path.isfile(f):
        with open(f, "rb") as fh:
            return fh.read()
    if sb.configured():
        try:
            data = sb.storage_download(AVATAR_BUCKET, key)
        except sb.SupabaseError:
            return None
        if data:
            _avatar_cache_write(user, data)  # warm the cache for the next hit
            return data
    return None


def avatar_delete(user):
    """Remove a photo everywhere. Called when an account is deleted; the
    profiles row (and its avatar_url) goes with the account by cascade."""
    key = _avatar_key(user)
    try:
        os.remove(_avatar_cache_file(user))
    except OSError:
        pass
    if key and sb.configured():
        try:
            sb.storage_delete(AVATAR_BUCKET, key)
        except sb.SupabaseError:
            pass  # already gone, or no bucket yet — nothing to tidy


def _teacher_school_map():
    """username -> school name, read from the (shared) timetable blocks. This is
    the authoritative teacher->school link the admin console groups data by."""
    data = _load_timetable_all()
    return {u.lower(): (blk.get("school") or "").strip()
            for u, blk in (data.get("teachers") or {}).items()}


def admin_list_all_users():
    """Every account: username, full_name, role, created_at, school. Supabase is
    the source of truth for accounts; local users.json is a fallback."""
    school_of = _teacher_school_map()
    out = []
    if sb.configured():
        try:
            profiles = {p["username"]: p for p in sb.select("profiles",
                        {"select": "username,full_name,role"})}
            for u in (sb.admin_list_users().get("users") or []):
                uname = (u.get("user_metadata") or {}).get("username", "")
                if not uname:
                    continue
                prof = profiles.get(uname, {})
                out.append({
                    "username": uname,
                    "full_name": prof.get("full_name") or (u.get("user_metadata") or {}).get("full_name") or uname,
                    "role": (prof.get("role") or "teacher").lower(),
                    "created_at": u.get("created_at", ""),
                    "active": not sb.is_banned(u),
                    "school": school_of.get(uname.lower(), ""),
                })
        except sb.SupabaseError as e:
            return {"users": [], "error": str(e)}
    else:
        for uname, rec in auth._load_users().items():
            out.append({"username": uname, "full_name": rec.get("full_name") or uname,
                        "role": (rec.get("role") or "teacher").lower(), "created_at": "",
                        "active": True, "school": school_of.get(uname.lower(), "")})
    order = {"super_admin": 0, "admin": 1, "teacher": 2}
    out.sort(key=lambda r: (order.get(r["role"], 3), r["full_name"].lower()))
    return {"users": out}


def admin_overview():
    """School-wide totals for the admin dashboard."""
    users = admin_list_all_users().get("users", [])
    try:
        bank_total = bank.stats().get("jumlah", 0)
    except Exception:  # noqa: BLE001
        bank_total = 0
    try:
        lesson_total = len(lessons.list_lessons(""))
    except Exception:  # noqa: BLE001
        lesson_total = 0
    active_teachers = sum(1 for u in users if u["role"] == "teacher" and u.get("active", True))
    try:
        schools_total = len(admin_get_schools().get("schools", []))
    except Exception:  # noqa: BLE001
        schools_total = 0
    try:
        tt_teachers = _load_timetable_all().get("teachers", {})
        timetables_filled = sum(1 for block in tt_teachers.values() if block.get("classes"))
        timetables_total = len(tt_teachers)
    except Exception:  # noqa: BLE001
        timetables_filled = 0
        timetables_total = 0
    try:
        classrooms_total = len(admin_get_classrooms().get("classes", {}))
    except Exception:  # noqa: BLE001
        classrooms_total = 0
    try:
        students_total = load_students().get("jumlah", 0)
    except Exception:  # noqa: BLE001
        students_total = 0
    try:
        announce_items = get_announcement().get("items", [])
    except Exception:  # noqa: BLE001
        announce_items = []
    return {
        "users_total": len(users),
        "teachers": sum(1 for u in users if u["role"] == "teacher"),
        "active_teachers": active_teachers,
        "admins": sum(1 for u in users if u["role"] in ("admin", "super_admin")),
        "lessons_total": lesson_total,
        "bank_total": bank_total,
        "schools_total": schools_total,
        "timetables_filled": timetables_filled,
        "timetables_total": timetables_total,
        "classrooms_total": classrooms_total,
        "students_total": students_total,
        "announcement_count": len(announce_items),
        "announcement_preview": announce_items[0] if announce_items else "",
    }


def admin_create_teacher(body, actor_role):
    if not sb.configured():
        return {"ok": False, "ralat": "Supabase is not configured."}
    username = (body.get("username") or "").strip().lower()
    full_name = (body.get("full_name") or "").strip()[:80]
    password = body.get("password") or ""
    role = (body.get("role") or "teacher").lower()
    if role not in VALID_ROLES:
        return {"ok": False, "ralat": "Invalid role."}
    # Only a super_admin may create another admin or super_admin.
    if role in ("admin", "super_admin") and actor_role != "super_admin":
        return {"ok": False, "ralat": "Only a super admin can create admin accounts."}
    if not USERNAME_RE.match(username):
        return {"ok": False, "ralat": "Username must be 3-32 chars: a-z 0-9 _ . -"}
    if len(password) < 6:
        return {"ok": False, "ralat": "Password must be at least 6 characters."}
    if not full_name:
        return {"ok": False, "ralat": "Please enter the teacher's full name."}
    try:
        sb.admin_create_user(username, password, full_name=full_name, role_name=role)
    except sb.SupabaseError as e:
        msg = "That username is already taken." if "already" in str(e).lower() or "exists" in str(e).lower() \
            else "Could not create the account."
        return {"ok": False, "ralat": msg}
    return {"ok": True}


def admin_set_role(body, actor, actor_role):
    if not sb.configured():
        return {"ok": False, "ralat": "Supabase is not configured."}
    target = (body.get("username") or "").strip().lower()
    new_role = (body.get("role") or "").lower()
    if new_role not in VALID_ROLES:
        return {"ok": False, "ralat": "Invalid role."}
    if target == actor:
        return {"ok": False, "ralat": "You can't change your own role."}
    try:
        rows = sb.select("profiles", {"select": "role", "username": "eq." + target})
        current = (rows[0].get("role") or "teacher").lower() if rows else None
    except sb.SupabaseError:
        current = None
    if current is None:
        return {"ok": False, "ralat": "User not found."}
    # Guard the super_admin tier: only a super_admin may grant it, or change
    # someone who currently holds it.
    if (new_role == "super_admin" or current == "super_admin") and actor_role != "super_admin":
        return {"ok": False, "ralat": "Only a super admin can manage super admin accounts."}
    try:
        sb.set_profile_role(target, new_role)
        u = sb.admin_find_user(target)
        if u:  # keep Auth metadata in sync with the profiles table
            meta = dict(u.get("user_metadata") or {})
            meta["role"] = new_role
            sb.admin_update_user(u["id"], user_metadata=meta)
    except sb.SupabaseError as e:
        return {"ok": False, "ralat": str(e)}
    return {"ok": True}


def admin_reset_password(body, actor, actor_role):
    if not sb.configured():
        return {"ok": False, "ralat": "Supabase is not configured."}
    target = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    if len(password) < 6:
        return {"ok": False, "ralat": "Password must be at least 6 characters."}
    u = sb.admin_find_user(target)
    if not u:
        return {"ok": False, "ralat": "User not found."}
    target_role = (u.get("user_metadata") or {}).get("role", "teacher").lower()
    if target_role == "super_admin" and actor_role != "super_admin":
        return {"ok": False, "ralat": "Only a super admin can reset a super admin's password."}
    try:
        sb.admin_update_user(u["id"], password=password)
    except sb.SupabaseError as e:
        return {"ok": False, "ralat": str(e)}
    return {"ok": True}


def admin_delete_teacher(body, actor, actor_role):
    if not sb.configured():
        return {"ok": False, "ralat": "Supabase is not configured."}
    target = (body.get("username") or "").strip().lower()
    if target == actor:
        return {"ok": False, "ralat": "You can't delete your own account."}
    u = sb.admin_find_user(target)
    if not u:
        return {"ok": False, "ralat": "User not found."}
    target_role = (u.get("user_metadata") or {}).get("role", "teacher").lower()
    if target_role == "super_admin" and actor_role != "super_admin":
        return {"ok": False, "ralat": "Only a super admin can delete a super admin."}
    try:
        sb.admin_delete_user(u["id"])  # cascade removes the profiles row
    except sb.SupabaseError as e:
        return {"ok": False, "ralat": str(e)}
    avatar_delete(target)  # cloud copy + local cache
    return {"ok": True}


def admin_set_active(body, actor, actor_role):
    """Deactivate (ban) or reactivate a teacher account."""
    if not sb.configured():
        return {"ok": False, "ralat": "Supabase is not configured."}
    target = (body.get("username") or "").strip().lower()
    active = bool(body.get("active"))
    if target == actor:
        return {"ok": False, "ralat": "You can't deactivate your own account."}
    u = sb.admin_find_user(target)
    if not u:
        return {"ok": False, "ralat": "User not found."}
    target_role = (u.get("user_metadata") or {}).get("role", "teacher").lower()
    if target_role == "super_admin" and actor_role != "super_admin":
        return {"ok": False, "ralat": "Only a super admin can change a super admin."}
    try:
        sb.admin_set_banned(u["id"], banned=not active)
    except sb.SupabaseError as e:
        return {"ok": False, "ralat": str(e)}
    return {"ok": True}


# ---- Timetable management (admin edits any teacher's block in timetable.json) ----
def _timetable_path():
    return os.path.join(ROOT, "timetable.json")


def _load_timetable_all():
    if sb.use_cloud():
        try:
            rows = sb.select("app_settings", params={
                "select": "key,value", "key": "like.timetable:*", "limit": "10000"})
            return {"teachers": {
                row["key"].split(":", 1)[1]: (row.get("value") or {})
                for row in rows if ":" in (row.get("key") or "")
            }}
        except sb.SupabaseError:
            if sb.cloud_required():
                raise
    try:
        with open(_timetable_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"teachers": {}}


def admin_get_timetables():
    return _load_timetable_all()


def admin_save_timetable(body):
    """Replace one teacher's timetable block. body = {username, block:{teacher_name,
    school, class_pupils, classes:[...]}}."""
    username = (body.get("username") or "").strip().lower()
    block = body.get("block") or {}
    if not username:
        return {"ok": False, "ralat": "Missing username."}
    if not isinstance(block.get("classes"), list):
        return {"ok": False, "ralat": "Invalid timetable data."}
    clean_block = {
        "teacher_name": str(block.get("teacher_name", ""))[:80],
        "school": str(block.get("school", ""))[:120],
        "class_pupils": block.get("class_pupils") or {},
        "classes": block.get("classes"),
    }
    if sb.use_cloud():
        _cloud_setting_set(_timetable_setting_key(username), clean_block)
        return {"ok": True}
    data = _load_timetable_all()
    data.setdefault("teachers", {})[username] = clean_block
    with open(_timetable_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"ok": True}


# ---- Timetable templates (admin: one uniform period structure per school,
# so a newly-registered teacher's timetable starts from a consistent shape
# instead of a blank ad-hoc grid) ----
def _template_setting_key(school):
    return "tt-template:" + (school or "").strip().lower()


def _load_templates_all():
    if sb.use_cloud():
        try:
            rows = sb.select("app_settings", params={
                "select": "key,value", "key": "like.tt-template:*", "limit": "10000"})
            return {"templates": {
                row["key"].split(":", 1)[1]: (row.get("value") or {})
                for row in rows if ":" in (row.get("key") or "")
            }}
        except sb.SupabaseError:
            if sb.cloud_required():
                raise
    try:
        with open(_timetable_path(), encoding="utf-8") as f:
            return {"templates": (json.load(f).get("templates") or {})}
    except (FileNotFoundError, ValueError):
        return {"templates": {}}


def admin_get_timetable_templates():
    return _load_templates_all()


PERIOD_MINUTES = 30  # every period slot is a fixed 30-minute block


def _add_minutes(hhmm, minutes):
    """'07:30' + 30 -> '08:00'. Returns '' for anything that isn't HH:MM."""
    try:
        h, m = (int(x) for x in hhmm.split(":", 1))
    except (ValueError, AttributeError):
        return ""
    total = (h * 60 + m + minutes) % (24 * 60)
    return "{:02d}:{:02d}".format(total // 60, total % 60)


def admin_save_timetable_template(body):
    """Replace one school's period template. body = {school, periods:[{start}]} —
    each period is a fixed PERIOD_MINUTES block; `end` is derived, not stored
    as free input, so every school's slots line up on the same grid."""
    school = (body.get("school") or "").strip()
    periods = body.get("periods")
    if not school:
        return {"ok": False, "ralat": "Missing school."}
    if not isinstance(periods, list):
        return {"ok": False, "ralat": "Invalid template data."}
    clean_periods = []
    for p in periods:
        start = str(p.get("start", ""))[:10] if isinstance(p, dict) else ""
        if start:
            clean_periods.append({"start": start, "end": _add_minutes(start, PERIOD_MINUTES)})
    if sb.use_cloud():
        _cloud_setting_set(_template_setting_key(school), {"school": school, "periods": clean_periods})
        return {"ok": True}
    data = _load_timetable_all()
    data.setdefault("templates", {})[school.lower()] = {"school": school, "periods": clean_periods}
    with open(_timetable_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"ok": True}


# ---- Schools registry (super admin: the AI Powered Classroom 1M schools) ----
# The program spans many schools; the super admin keeps the master list here so
# teachers and timetables can be tied to a real school. Stored in schools.json.
def _schools_path():
    return os.path.join(ROOT, "schools.json")


def admin_get_schools():
    if sb.use_cloud():
        try:
            data = _cloud_setting_get("schools", {"schools": []}) or {"schools": []}
            return data if isinstance(data.get("schools"), list) else {"schools": []}
        except sb.SupabaseError:
            if sb.cloud_required():
                raise
    try:
        with open(_schools_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return {"schools": []}
    if not isinstance(data.get("schools"), list):
        data = {"schools": []}
    return data


def admin_save_schools(body):
    """Replace the whole school list. body = {schools:[{code,name,district,state,
    principal}]}. Super-admin only (enforced in the handler)."""
    schools = body.get("schools")
    if not isinstance(schools, list):
        return {"ok": False, "ralat": "Invalid schools data."}
    clean = []
    seen_codes = set()
    for s in schools:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", "")).strip()[:160]
        if not name:
            continue
        code = str(s.get("code", "")).strip()[:40]
        # Keep codes unique (they key teachers/timetables to a school).
        if code and code.lower() in seen_codes:
            continue
        if code:
            seen_codes.add(code.lower())
        clean.append({
            "code": code,
            "name": name,
            "district": str(s.get("district", "")).strip()[:120],
            "state": str(s.get("state", "")).strip()[:80],
            "principal": str(s.get("principal", "")).strip()[:120],
        })
    if sb.use_cloud():
        _cloud_setting_set("schools", {"schools": clean})
        return {"ok": True, "count": len(clean)}
    with open(_schools_path(), "w", encoding="utf-8") as f:
        json.dump({"schools": clean}, f, indent=2, ensure_ascii=False)
    return {"ok": True, "count": len(clean)}


# ---- Shared resources: Classroom IDs + student list ----
def _classrooms_path():
    return os.path.join(ROOT, "classrooms.json")


def admin_get_classrooms():
    if sb.use_cloud():
        data = _load_classrooms() or {}
        return {"lesson_plan": data.get("lesson_plan", ""),
                "classes": data.get("classes") or {}}
    try:
        with open(_classrooms_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"lesson_plan": "", "classes": {}}


def admin_save_classrooms(body):
    lesson_plan = str(body.get("lesson_plan", "")).strip()
    classes = body.get("classes") or {}
    if not isinstance(classes, dict):
        return {"ok": False, "ralat": "Invalid classes data."}
    clean = {str(k).strip(): str(v).strip() for k, v in classes.items() if str(k).strip()}
    if sb.use_cloud():
        desired = {"lesson_plan": lesson_plan}
        desired.update(clean)
        rows = [{"class_name": name, "classroom_id": cid}
                for name, cid in desired.items()]
        sb.insert("classrooms", rows, upsert_on="class_name")
        existing = sb.select("classrooms", params={"select": "class_name"})
        for row in existing:
            name = row.get("class_name", "")
            if name not in desired:
                sb.delete("classrooms", {"class_name": "eq." + name})
        return {"ok": True}
    data = admin_get_classrooms()
    data["lesson_plan"] = lesson_plan
    data["classes"] = clean
    with open(_classrooms_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"ok": True}


def admin_save_students(body):
    """body = {students:[{name,email}]} -> rewrite Email Student Prototype.txt
    in the name-line / email-line format load_students() expects."""
    students = body.get("students") or []
    clean = []
    seen = set()
    for s in students:
        name = str(s.get("name", "")).strip()
        email = str(s.get("email", "")).strip().lower()
        if "@" not in email or email in seen:
            continue
        seen.add(email)
        clean.append({"label": name or "Student", "email": email})
    if sb.use_cloud():
        if clean:
            sb.insert("students", clean, upsert_on="email")
        existing = sb.select("students", params={"select": "email"})
        for row in existing:
            email = (row.get("email") or "").strip().lower()
            if email and email not in seen:
                sb.delete("students", {"email": "eq." + email})
        return {"ok": True, "count": len(clean)}
    lines = []
    for s in clean:
        name, email = s["label"], s["email"]
        lines.append(name or "Student")
        lines.append(email)
        lines.append("")
    path = os.path.join(ROOT, "Email Student Prototype.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    return {"ok": True}


# ---- Announcements (admin posts one notice; teachers see it on the dashboard) ----
def _announcement_path():
    return os.path.join(ROOT, "announcement.json")


def get_announcement():
    if sb.use_cloud():
        try:
            data = _cloud_setting_get("announcement", {"message": "", "items": [], "at": ""})
        except sb.SupabaseError:
            if sb.cloud_required():
                raise
            data = None
        if data is not None:
            items = data.get("items")
            if not isinstance(items, list):
                items = [ln.strip() for ln in str(data.get("message", "")).splitlines()
                         if ln.strip()]
            data["items"] = items
            data["message"] = "\n".join(items)
            return data
    try:
        with open(_announcement_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return {"message": "", "items": [], "at": ""}
    # Backward compatibility: derive an items list from a legacy single message,
    # and keep `message` populated from items for any old client still reading it.
    items = data.get("items")
    if not isinstance(items, list):
        items = [ln.strip() for ln in str(data.get("message", "")).splitlines() if ln.strip()]
    data["items"] = items
    data["message"] = "\n".join(items)
    return data


def admin_set_announcement(body):
    # Accept either an `items` list or a newline-separated `message`; each
    # non-empty line becomes one rotating announcement in the carousel.
    raw_items = body.get("items")
    if not isinstance(raw_items, list):
        raw_items = str(body.get("message", "")).splitlines()
    items = [str(ln).strip()[:500] for ln in raw_items if str(ln).strip()][:20]
    data = {
        "items": items,
        "message": "\n".join(items),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    if sb.use_cloud():
        _cloud_setting_set("announcement", data)
        return {"ok": True}
    with open(_announcement_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"ok": True}


def _days_overdue(due_iso):
    """Whole days past the due date/time (0 if not yet due or unknown)."""
    if not due_iso:
        return 0
    try:
        due = datetime.fromisoformat(due_iso)
    except ValueError:
        return 0
    delta = datetime.now() - due
    return max(0, delta.days)


def _fallback_nudge(nama, tugasan, kali, guru):
    """Plain, kind message used only if the LLM call fails — same escalation
    ladder and same never-shaming tone as agent6_reminder.md, just not
    personalised to the pupil's performance."""
    if kali >= 2:
        aras = "notify_teacher"
        subjek = "Let's sort out your English work together"
        badan = ("Hi {n}, I've reminded you about \"{t}\" a few times now, so I'll come and "
                 "find you after class. I'm not upset — I just want to know if something is "
                 "making this hard. Please open Google Classroom and turn in whatever you "
                 "have so far. Kalau susah, jumpa cikgu ya.").format(n=nama, t=tugasan)
    elif kali == 1:
        aras = "firm"
        subjek = "Your English work is still waiting: " + tugasan
        badan = ("Hi {n}, \"{t}\" is still not turned in and it is now late. Please open "
                 "Google Classroom, finish it and press Turn in by tomorrow. Tell me if "
                 "you're stuck — I'd rather help than chase.").format(n=nama, t=tugasan)
    else:
        aras = "gentle"
        subjek = "Your English work is waiting: " + tugasan
        badan = ("Hi {n}! I don't see \"{t}\" in Google Classroom yet — I think it may have "
                 "slipped your mind. Open Classroom, finish it and press Turn in when you're "
                 "done. Let me know if anything is unclear.").format(n=nama, t=tugasan)
    return {"hantar": True, "aras": aras, "subjek": subjek,
            "mesej": badan + "\n\n— " + (guru or "Cikgu")}


def _class_form(class_name):
    """Form (1-5) from a class name like '3 Delima' / 'Form 4 Bestari'. Defaults to 3."""
    m = re.search(r"\b([1-5])\b", class_name or "")
    return int(m.group(1)) if m else 3


def _hub_submission_states(class_name, tugasan):
    """Who has / hasn't submitted, read via the Apps Script hub (runs as the
    teacher). Used when Path B isn't set up — the hub needs no MOE OAuth
    approval, so this is what makes Agent 6 usable today."""
    course_id = (_load_classrooms().get("classes", {}) or {}).get(class_name, "")
    res = _post_hub({"action": "submissions", "courseId": course_id,
                     "courseName": class_name, "title": tugasan})
    if not res.get("ok"):
        return {"ok": False, "error": "Hub could not read Classroom: "
                + str(res.get("error", "unknown error"))}
    return res


def _submission_states(class_name, tugasan, body):
    """Non-submitter source, in order of preference:
    caller-supplied list -> Path B (Google API) -> Apps Script hub."""
    if body.get("students"):
        return {"ok": True, "course": class_name, "coursework": tugasan,
                "due_iso": body.get("due_iso", ""), "students": body["students"],
                "source": "supplied"}
    try:
        import niat_google
        if niat_google.available(interactive=False):
            states = niat_google.list_submission_states(class_name, tugasan)
            if states.get("ok"):
                states["source"] = "google"
            return states
    except Exception:  # noqa: BLE001 — no Path B libs/credentials; use the hub
        pass
    states = _hub_submission_states(class_name, tugasan)
    if states.get("ok"):
        states["source"] = "hub"
    return states


def remind_agent(body):
    """Agent 6 — remind pupils who have NOT submitted an assignment.

    Reads submission states from Google Classroom (who turned in, who didn't),
    then for each non-submitter the LLM decides tone + escalation from the pupil's
    performance and how many times they've already been reminded, writes a
    personalised message, and emails it via the hub. On the 3rd+ reminder it also
    emails the teacher to follow up.

    Pass "dry_run": true to get the drafted messages back WITHOUT emailing anyone
    and without counting a reminder — the teacher previews first, then sends.
    """
    class_name = (body.get("class_name") or body.get("kelas") or "").strip()
    tugasan = (body.get("coursework_title") or body.get("tugasan") or "").strip()
    dry_run = bool(body.get("dry_run"))
    if not class_name:
        return {"ok": False, "error": "No class specified."}

    states = _submission_states(class_name, tugasan, body)
    if not states.get("ok"):
        return states

    tugasan = tugasan or states.get("coursework", "") or "the assignment"
    due_iso = body.get("due_iso") or states.get("due_iso", "")
    overdue = _days_overdue(due_iso)
    # A title alone is not a unique assignment identifier: teachers may reuse
    # titles in another class or term. Include the class and Classroom due time
    # so the automatic one-reminder cap applies to this exact assignment.
    reminder_key = (body.get("reminder_key") or "").strip()
    if not reminder_key:
        reminder_key = " | ".join(
            part for part in (class_name, tugasan, due_iso) if part
        ) or tugasan

    missing = [s for s in states.get("students", [])
               if not s.get("submitted") and (s.get("email"))]
    if not missing:
        return {"ok": True, "class_name": class_name, "coursework": tugasan,
                "ringkasan": "Everyone has submitted — no reminders needed.",
                "reminders": [], "sent": 0}

    emails = [s["email"] for s in missing]
    # Past marks only colour the WORDING — if that table isn't reachable the
    # agent must still run, just with a less personalised tone.
    try:
        perf = {p["emel"]: p for p in prestasi_murid.cumulative_by_student(class_name)}
    except Exception as e:  # noqa: BLE001
        print("Agent 6: no performance data ({}) — tone will be generic.".format(e))
        perf = {}
    # The reminder counts drive the escalation ladder, so losing them is worse:
    # treat everyone as never-reminded (gentle) rather than skipping the class.
    try:
        reminded = peringatan.counts_for(reminder_key, emails)
    except Exception as e:  # noqa: BLE001
        print("Agent 6: reminder history unavailable ({}) — everyone treated as "
              "a first nudge. Run supabase/schema.sql to create the 'peringatan' "
              "table.".format(e))
        reminded = {}

    # Cap: once a pupil has had MAX_REMINDERS nudges, stop sending for this
    # exact assignment. The due-date watcher sets this to 1; supervised manual
    # runs keep the default escalation ladder and cap of 4.
    MAX_REMINDERS = int(body.get("max_reminders") or 4)
    capped = [s for s in missing if reminded.get(s["email"].strip().lower(), 0) >= MAX_REMINDERS]
    missing = [s for s in missing if reminded.get(s["email"].strip().lower(), 0) < MAX_REMINDERS]
    if not missing:
        return {"ok": True, "class_name": class_name, "coursework": tugasan,
                "ringkasan": "All non-submitters have reached the reminder cap ({}); "
                "teacher already notified.".format(MAX_REMINDERS),
                "reminders": [], "sent": 0, "capped": len(capped)}

    # Build the per-pupil roster for Agent 6.
    lines = []
    for s in missing:
        e = s["email"].strip().lower()
        p = perf.get(e, {})
        lines.append(
            "- {emel} | name: {nama} | average: {avg} | reminded so far: {kali} | "
            "days overdue: {od} | assignment: {tug}".format(
                emel=e, nama=s.get("name") or e.split("@")[0],
                avg=(str(p.get("purata")) + "%") if p.get("purata") is not None else "unknown",
                kali=reminded.get(e, 0), od=overdue, tug=tugasan))

    # Context the tone depends on: how old the pupils are (Form) and whose
    # voice to write in — a Form 1 nudge should not read like a Form 5 one.
    form = _class_form(class_name)
    teacher_name = (body.get("teacher_name") or "").strip() or "Cikgu"
    system_prompt = read_text(os.path.join(PROMPT_DIR, "agent6_reminder.md"))
    user_prompt = (
        "Class: {kelas} (Form {form}, KSSM English)\n"
        "Teacher (sign off as this name): {guru}\n"
        "Assignment in Google Classroom: \"{tug}\"\n"
        "Days overdue: {od}\n\n"
        "Decide and write reminders for these pupils who have NOT submitted:\n\n{roster}\n\n"
        "Return JSON only.".format(kelas=class_name, form=form, guru=teacher_name,
                                   tug=tugasan, od=overdue, roster="\n".join(lines)))
    decided, summary = {}, ""
    try:
        data = call_llm_json(system_prompt, user_prompt, max_tokens=3000)
        if isinstance(data, dict):
            summary = (data.get("ringkasan") or "").strip()
            for r in data.get("reminders", []) or []:
                em = (r.get("emel") or "").strip().lower()
                if em:
                    decided[em] = r
    except Exception:  # noqa: BLE001 — fall back to a plain nudge below
        decided = {}

    teacher_email = (body.get("teacher_email") or "").strip()
    work_url = states.get("classroom_url", "")
    results, sent = [], 0
    for s in missing:
        e = s["email"].strip().lower()
        d = decided.get(e) or _fallback_nudge(
            s.get("name") or e.split("@")[0], tugasan, reminded.get(e, 0), teacher_name)
        aras = d.get("aras", "gentle")
        if not d.get("hantar", True) or not (d.get("mesej") or "").strip():
            results.append({"emel": e, "nama": s.get("name"), "hantar": False, "aras": aras})
            continue

        subject = d.get("subjek") or ("Your English work: " + tugasan)
        message = d.get("mesej", "")
        if work_url:  # one-tap straight to the assignment
            message += "\n\nOpen it here: " + work_url

        if dry_run:  # preview only — nothing sent, nothing counted
            results.append({"emel": e, "nama": s.get("name"), "hantar": True, "aras": aras,
                            "subjek": subject, "mesej": message, "sent": False,
                            "preview": True})
            continue

        mail = _post_hub({"action": "mail", "to": e, "subject": subject, "body": message})
        ok = bool(mail.get("ok"))
        if ok:
            sent += 1
            try:
                peringatan.record(e, class_name, reminder_key, aras)
            except Exception as rec_err:  # noqa: BLE001 — mail already went out;
                # losing the count must not abort the rest of the class.
                print("Agent 6: could not record the reminder for {} ({}).".format(e, rec_err))
            # Escalation: on notify_teacher, also alert the teacher — only when
            # the pupil's own email actually went out, so the counts stay honest.
            if aras == "notify_teacher" and teacher_email:
                _post_hub({"action": "mail", "to": teacher_email,
                           "subject": "Pupil not submitting — {} ({})".format(tugasan, class_name),
                           "body": "{} ({}) still hasn't submitted \"{}\" after {} reminder(s). "
                                   "Agent 6 has sent a final, gentle message and will stop "
                                   "escalating — please follow up in person.".format(
                                       s.get("name") or e, e, tugasan, reminded.get(e, 0))})
        results.append({"emel": e, "nama": s.get("name"), "hantar": True, "aras": aras,
                        "subjek": subject, "mesej": message,
                        "sent": ok, "error": None if ok else mail.get("error", "mail failed")})

    if dry_run:
        summary = summary or "{} pupil(s) have not submitted — preview only, nothing sent yet.".format(
            len(missing))
    elif not summary:
        summary = "{} pupil(s) not submitted; {} reminder email(s) sent.".format(len(missing), sent)
    return {"ok": True, "class_name": class_name, "coursework": tugasan,
            "overdue_days": overdue, "ringkasan": summary, "sent": sent,
            "dry_run": dry_run, "source": states.get("source", ""),
            "classroom_url": work_url, "reminders": results}


ROUTES = {
    "/api/generate-rph": generate_rph,
    "/api/generate-materials": generate_materials,
    "/api/gamma-generate": generate_gamma,
    "/api/classroom-lessonplan": classroom_lessonplan,
    "/api/classroom-worksheet": classroom_worksheet,
    "/api/classroom-materials": classroom_materials,
    "/api/generate-worksheet": generate_worksheet,
    "/api/save-lesson": save_lesson_route,
    "/api/delete-lesson": delete_lesson_route,
    "/api/reflect": generate_reflection,
    "/api/reflection-report": reflection_report,
    "/api/email-reflection": email_reflection,
    "/api/quiz-results": quiz_results,
    "/api/lesson-reflection": lesson_reflection_route,
    "/api/distribute-direct": distribute_direct,
    "/api/differentiate": differentiate,
    "/api/remind": remind_agent,
}


def runtime_readiness(check_database=False):
    """Secret-free readiness details for operators and deployment probes."""
    errors = runtime_configuration_errors()
    database_reachable = None
    if check_database and sb.configured() and not errors:
        try:
            sb.select("app_settings", params={"select": "key", "limit": "1"})
            database_reachable = True
        except sb.SupabaseError:
            database_reachable = False
            errors.append("Supabase is unreachable or schema.sql has not been applied")
    cfg = _read_reminder_cfg()
    try:
        import niat_google
        google_oauth_ready = niat_google.available(interactive=False)
    except Exception:
        google_oauth_ready = False
    return {
        "ready": not errors,
        "container": CONTAINER_MODE,
        "storage": "supabase" if sb.use_cloud() else "local",
        "database_reachable": database_reachable,
        "configuration_errors": errors,
        "integrations": {
            "apps_script_hub": bool(cfg.get("APPSCRIPT_HUB_URL") and cfg.get("APPSCRIPT_HUB_KEY")),
            "google_oauth": google_oauth_ready,
            "cloud_scheduler_endpoint": bool(os.environ.get("NIAT_CRON_SECRET", "").strip()),
        },
    }

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PenjanaRPH/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location, headers=None):
        self.send_response(302)
        self.send_header("Location", location)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # Paths reachable WITHOUT logging in (login page + its logo + health probe
    # + PWA manifest/service worker, which browsers fetch outside the session).
    PUBLIC_GET = ("/login.html", "/signup.html", "/niat-logo.png", "/api/health", "/api/ready", "/favicon.ico",
                  "/manifest.json", "/sw.js", "/icon-192.png", "/icon-512.png")

    def _current_user(self):
        return auth.user_from_cookie(self.headers.get("Cookie", ""))

    def _role_of(self, username):
        """Return the lowercase role ('teacher' | 'admin' | 'super_admin') for a
        username, read from Supabase profiles (authoritative), falling back to
        local users.json. Unknown users are treated as plain 'teacher'."""
        if not username:
            return "teacher"
        if sb.configured():
            try:
                rows = sb.select("profiles", {"select": "role", "username": "eq." + username})
                if rows:
                    return (rows[0].get("role") or "teacher").lower()
            except sb.SupabaseError:
                pass
        return (auth._load_users().get(username, {}).get("role") or "teacher").lower()

    def _require_admin(self):
        """Return (username, role) if the caller is admin/super_admin, else send
        a 403 and return (None, None). The role is ALWAYS checked server-side —
        the client cannot claim to be an admin."""
        user = self._current_user()
        role = self._role_of(user)
        if role not in ("admin", "super_admin"):
            self._send(403, {"ralat": "Admins only."})
            return None, None
        return user, role

    def _require_super_admin(self):
        """Like _require_admin, but only a super_admin passes. Used for
        program-wide management (schools) that a plain admin may only view."""
        user = self._current_user()
        role = self._role_of(user)
        if role != "super_admin":
            self._send(403, {"ralat": "Super admins only."})
            return None, None
        return user, role

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        # ---- Login gate: everything except PUBLIC_GET needs a valid session ----
        if path not in self.PUBLIC_GET and not self._current_user():
            if path.startswith("/api/"):
                self._send(401, {"ralat": "not logged in"})
            else:
                # keep the original link (e.g. ?class=3%20Delima) for after login
                nxt = self.path if self.path not in ("/", "/index.html") else ""
                self._redirect("/login.html" + (("?next=" + urllib.parse.quote(nxt)) if nxt else ""))
            return
        if path == "/dskp_english_f3.json":
            self._send(200, read_text(DSKP_FILE, "{}"), CONTENT_TYPES[".json"])
            return
        # Per-form DSKP: /dskp_english_f1.json ... /dskp_english_f5.json
        m = re.fullmatch(r"/dskp_english_f([1-5])\.json", path)
        if m:
            self._send(200, read_text(dskp_file_for(m.group(1)), "{}"),
                       CONTENT_TYPES[".json"])
            return
        # Which forms actually have a data file available (for the Form selector).
        if path == "/api/dskp-forms":
            avail = [n for n in DSKP_FORMS
                     if os.path.exists(os.path.join(ROOT, "dskp_english_f{}.json".format(n)))]
            self._send(200, {"forms": avail}, CONTENT_TYPES[".json"])
            return
        if path == "/api/health":
            # Liveness only proves that this process can answer HTTP. Supabase
            # reachability is reported separately by /api/ready.
            bank_total = None
            if not CONTAINER_MODE:
                try:
                    bank_total = bank.stats().get("jumlah", 0)
                except Exception:  # noqa: BLE001
                    pass
            status = runtime_readiness(check_database=False)
            self._send(200, {
                "ok": True,
                "configuration_ready": status["ready"],
                "model": MODEL,
                "api_key_set": bool(GOOGLE_API_KEY),
                "bank_total": bank_total,
                "engine_mode": ENGINE_MODE,
                "local_fallback": {
                    "available": ollama_available(),
                    "model": OLLAMA_MODEL,
                },
                "time": datetime.now().isoformat(timespec="seconds"),
            })
            return
        if path == "/api/ready":
            status = runtime_readiness(check_database=True)
            self._send(200 if status["ready"] else 503, status)
            return
        if path == "/api/bank-stats":
            try:
                self._send(200, bank.stats())
            except Exception as e:  # noqa: BLE001
                self._send(500, {"ralat": str(e)})
            return
        if path == "/api/bank-list":
            # Read-only browse for any logged-in teacher (the sidebar "Question
            # bank" item) — unlike /api/admin/bank this has no delete affordance
            # and no admin gate, since viewing past questions isn't sensitive.
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            try:
                self._send(200, {"questions": bank.list_questions(q, limit=200), "stats": bank.stats()})
            except Exception as e:  # noqa: BLE001
                self._send(500, {"ralat": str(e)})
            return
        if path == "/api/lessons":
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._send(200, lessons.list_lessons(q, owner_username=self._current_user()))
            return
        if path == "/api/lesson":
            lid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            rec = (lessons.get_lesson(int(lid), owner_username=self._current_user())
                   if lid.isdigit() else None)
            self._send(200 if rec else 404, rec or {"ralat": "lesson not found"})
            return
        if path == "/api/progress":
            self._send(200, {"items": lessons.progress(owner_username=self._current_user())})
            return
        if path == "/api/next-class":
            self._send(200, next_class(self._current_user()))
            return
        if path == "/api/students":
            self._send(200, load_students())
            return
        if path == "/api/class-info":
            q = parse_qs(urlparse(self.path).query).get("class", [""])[0]
            self._send(200, class_lookup({"class": q}, self._current_user()))
            return
        if path == "/api/profile":
            # User profile (name, role, avatar). Supabase `profiles` table is
            # authoritative for accounts created there (signup / migrated);
            # local users.json is the fallback for not-yet-migrated accounts.
            user = self._current_user()
            full_name, role, from_supabase = user, "Teacher", False
            if sb.configured():
                try:
                    rows = sb.select("profiles", {"select": "full_name,role",
                                                   "username": "eq." + user})
                    if rows:
                        full_name = rows[0].get("full_name") or user
                        role = (rows[0].get("role") or "teacher").replace("_", " ").title()
                        from_supabase = True
                except sb.SupabaseError:
                    pass
            if not from_supabase:
                rec = auth._load_users().get(user, {})
                full_name = rec.get("full_name") or user
                role = rec.get("role") or "Teacher"
            avatar = avatar_url_for(user)
            self._send(200, {
                "username": user,
                "full_name": full_name,
                "role": role,
                "avatar": avatar,
            })
            return
        if path == "/api/admin/users":
            user, role = self._require_admin()
            if not user:
                return
            self._send(200, admin_list_all_users())
            return
        if path == "/api/admin/overview":
            user, role = self._require_admin()
            if not user:
                return
            self._send(200, admin_overview())
            return
        if path == "/api/admin/lessons":
            if not self._require_admin()[0]:
                return
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._send(200, {"lessons": lessons.list_lessons(q)})
            return
        if path == "/api/admin/lesson":
            if not self._require_admin()[0]:
                return
            lid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            rec = lessons.get_lesson(int(lid)) if lid.isdigit() else None
            self._send(200 if rec else 404, rec or {"ralat": "lesson not found"})
            return
        if path == "/api/admin/timetables":
            if not self._require_admin()[0]:
                return
            self._send(200, admin_get_timetables())
            return
        if path == "/api/admin/timetable-templates":
            if not self._require_admin()[0]:
                return
            self._send(200, admin_get_timetable_templates())
            return
        if path == "/api/admin/schools":
            if not self._require_admin()[0]:
                return
            self._send(200, admin_get_schools())
            return
        if path == "/api/admin/classrooms":
            if not self._require_admin()[0]:
                return
            self._send(200, admin_get_classrooms())
            return
        if path == "/api/admin/students":
            if not self._require_admin()[0]:
                return
            self._send(200, load_students())
            return
        if path == "/api/admin/bank":
            if not self._require_admin()[0]:
                return
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._send(200, {"questions": bank.list_questions(q), "stats": bank.stats()})
            return
        if path == "/api/announcement":
            # Readable by any logged-in user — teachers see it as a dashboard banner.
            self._send(200, get_announcement())
            return
        # Profile photos are NOT plain static files — they come from Supabase
        # Storage (cached on disk), so this must run before the web/ handler
        # below would serve a stale or missing local copy. Readable by any
        # logged-in user; the login gate at the top of do_GET already ran.
        m = re.fullmatch(r"/avatars/([a-z0-9_.-]{3,32})\.png", path)
        if m:
            data = avatar_bytes(m.group(1))
            if data:
                # Safe to cache hard: the URL carries a ?v= stamp that changes
                # every time the teacher uploads a new photo.
                self._send(200, data, CONTENT_TYPES[".png"],
                           headers={"Cache-Control": "private, max-age=31536000"})
            else:
                self._send(404, {"ralat": "no photo for " + m.group(1)})
            return
        # Sajikan fail statik dari web/
        safe = os.path.normpath(path.lstrip("/")).replace("\\", "/")
        if safe.startswith(".."):
            self._send(403, {"ralat": "dilarang"})
            return
        full = os.path.join(WEB_DIR, safe)
        if os.path.isfile(full):
            ext = os.path.splitext(full)[1].lower()
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, CONTENT_TYPES.get(ext, "application/octet-stream"))
        else:
            self._send(404, {"ralat": "tidak dijumpai: " + path})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"ralat": "JSON permintaan tidak sah"})
            return
        # ---- Login / signup / logout (no session needed) ----
        if path == "/api/internal/reminders":
            expected = os.environ.get("NIAT_CRON_SECRET", "").strip()
            supplied = self.headers.get("X-Niat-Cron-Secret", "").strip()
            if not expected:
                self._send(503, {"ok": False, "ralat": "Scheduled reminders are not configured."})
            elif not hmac.compare_digest(expected, supplied):
                self._send(403, {"ok": False, "ralat": "Forbidden."})
            else:
                try:
                    import remind_cron
                    result = remind_cron.run()
                    self._send(200 if result.get("ok") else 502, result)
                except Exception as exc:  # keep scheduler failures visible
                    self._send(500, {"ok": False, "ralat": str(exc)})
            return
        if path == "/api/login":
            time.sleep(0.4)  # slow down password guessing
            user = (body.get("username") or "").strip().lower()
            password = body.get("password") or ""
            locked_for = _login_locked_seconds(user)
            if locked_for:
                self._send(429, {"ok": False, "ralat":
                           "Too many failed attempts. Try again in {} minute(s).".format(
                               max(1, (locked_for + 59) // 60))})
                return
            ok = False
            if sb.configured():
                try:
                    sb.sign_in(user, password)
                    ok = True
                except sb.SupabaseError:
                    ok = False
            if not ok:
                ok = auth.verify(user, password)  # legacy accounts not yet migrated
            if ok:
                _login_note_success(user)
                token = auth.make_token(user)
                self._send(200, {"ok": True, "user": user},
                           headers={"Set-Cookie": auth.session_cookie(token)})
            else:
                _login_note_failure(user)
                self._send(401, {"ok": False, "ralat": "Wrong username or password."})
            return
        if path == "/api/signup":
            if not sb.configured():
                self._send(503, {"ok": False, "ralat": "Account creation is not available yet."})
                return
            full_name = (body.get("full_name") or "").strip()[:80]
            username = (body.get("username") or "").strip().lower()
            password = body.get("password") or ""
            if not re.match(r"^[a-z0-9_.-]{3,32}$", username):
                self._send(400, {"ok": False, "ralat": "Username must be 3-32 chars: a-z 0-9 _ . -"})
                return
            if len(password) < 6:
                self._send(400, {"ok": False, "ralat": "Password must be at least 6 characters."})
                return
            if not full_name:
                self._send(400, {"ok": False, "ralat": "Please enter your full name."})
                return
            try:
                # role is ALWAYS "teacher" here — never taken from the request,
                # so a signup request can't grant itself admin/super_admin.
                sb.admin_create_user(username, password, full_name=full_name, role_name="teacher")
            except sb.SupabaseError as e:
                msg = "That username is already taken." if "already" in str(e).lower() or "exists" in str(e).lower() \
                    else "Could not create the account. Please try again."
                self._send(400, {"ok": False, "ralat": msg})
                return
            token = auth.make_token(username)
            self._send(200, {"ok": True, "user": username},
                       headers={"Set-Cookie": auth.session_cookie(token)})
            return
        if path == "/api/logout":
            self._send(200, {"ok": True}, headers={"Set-Cookie": auth.clear_cookie()})
            return
        # ---- Everything else needs a valid session ----
        if not self._current_user():
            self._send(401, {"ralat": "not logged in"})
            return
        try:
            if path == "/api/export-docx":
                data = export_docx.plan_to_docx(body.get("plan", {}), body.get("school", ""))
                self._send(200, data,
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            elif path == "/api/export-pptx":
                data = export_pptx.slides_to_pptx(body.get("materials", {}),
                                                  body.get("footer", ""))
                self._send(200, data,
                           "application/vnd.openxmlformats-officedocument.presentationml.presentation")
            elif path == "/api/profile":
                # Note: role is intentionally NOT settable here (never trust
                # a role value from the request body — that would let any
                # logged-in user grant themselves admin/super_admin).
                # Role changes are an admin-only action, not yet built.
                user = self._current_user()
                name = (body.get("full_name") or "").strip()[:80]
                updated_supabase = False
                if name and sb.configured():
                    try:
                        sb.update("profiles", {"username": "eq." + user}, {"full_name": name})
                        updated_supabase = True
                    except sb.SupabaseError:
                        if sb.cloud_required():
                            raise
                if name and not updated_supabase:
                    users = auth._load_users()
                    rec = users.setdefault(user, {})
                    rec["full_name"] = name
                    auth._save_users(users)
                self._send(200, {"ok": True})
            elif path == "/api/profile-photo":
                # Body: {"image": "data:image/png;base64,..."} — the UI resizes the
                # picture to a small square PNG on the client before sending.
                user = self._current_user()
                m = re.match(r"^data:image/png;base64,([A-Za-z0-9+/=]+)$",
                             body.get("image") or "")
                if not m:
                    self._send(400, {"ralat": "expected a data:image/png;base64 image"})
                else:
                    img = base64.b64decode(m.group(1))
                    if len(img) > 1_500_000:
                        self._send(400, {"ralat": "image too large (max 1.5 MB)"})
                    else:
                        try:
                            url, warning = avatar_save(user, img)
                        except ValueError:
                            self._send(400, {"ralat": "this account cannot have a photo"})
                        else:
                            self._send(200, {"ok": True, "avatar": url,
                                             "amaran": warning})
            elif path == "/api/admin/create-user":
                user, role = self._require_admin()
                if user:
                    self._send(200, admin_create_teacher(body, actor_role=role))
            elif path == "/api/admin/set-role":
                user, role = self._require_admin()
                if user:
                    self._send(200, admin_set_role(body, actor=user, actor_role=role))
            elif path == "/api/admin/reset-password":
                user, role = self._require_admin()
                if user:
                    self._send(200, admin_reset_password(body, actor=user, actor_role=role))
            elif path == "/api/admin/delete-user":
                user, role = self._require_admin()
                if user:
                    self._send(200, admin_delete_teacher(body, actor=user, actor_role=role))
            elif path == "/api/admin/set-active":
                user, role = self._require_admin()
                if user:
                    self._send(200, admin_set_active(body, actor=user, actor_role=role))
            elif path == "/api/admin/timetable":
                if self._require_admin()[0]:
                    self._send(200, admin_save_timetable(body))
            elif path == "/api/admin/timetable-template":
                if self._require_admin()[0]:
                    self._send(200, admin_save_timetable_template(body))
            elif path == "/api/admin/schools":
                if self._require_super_admin()[0]:
                    self._send(200, admin_save_schools(body))
            elif path == "/api/admin/classrooms":
                if self._require_admin()[0]:
                    self._send(200, admin_save_classrooms(body))
            elif path == "/api/admin/students":
                if self._require_admin()[0]:
                    self._send(200, admin_save_students(body))
            elif path == "/api/admin/bank-delete":
                if self._require_admin()[0]:
                    self._send(200, bank.delete_question(body.get("id")))
            elif path == "/api/admin/announcement":
                if self._require_admin()[0]:
                    self._send(200, admin_set_announcement(body))
            elif path == "/api/save":
                self._send(200, save_artifact(body))
            elif path in ROUTES:
                routed_body = dict(body)
                routed_body["_actor_username"] = self._current_user()
                self._send(200, ROUTES[path](routed_body))
            else:
                self._send(404, {"ralat": "laluan tidak dikenali: " + path})
        except Exception as e:  # noqa: BLE001 — pulangkan ralat ke UI
            self._send(500, {"ralat": str(e)})


def main():
    config_errors = runtime_configuration_errors()
    if config_errors:
        print("FATAL: unsafe container configuration:")
        for problem in config_errors:
            print("  - " + problem)
        raise SystemExit(2)
    if not GOOGLE_API_KEY:
        print("WARNING: GOOGLE_API_KEY not set — generation will fail.")
        print('  PowerShell:  $env:GOOGLE_API_KEY="AIza..."\n')
    print("Niat — English Form 3 Lesson Plan & Worksheet Generator (Phase 1 MVP)")
    print("  Model : {}".format(MODEL))
    print("  Open  : http://{}:{}".format(HOST if HOST != "0.0.0.0" else "localhost", PORT))
    print("  (Ctrl+C to stop)\n")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
