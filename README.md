# Niat — AI-Powered Classroom (Phase 1 MVP)

A web app for teachers to automatically generate a **Daily Lesson Plan (DLP/RPH)** and a
**multiple-choice worksheet** for **English Language (KSSM Form 3, CEFR B1 Low)**, powered by Google Gemini.

Flow: **Setup** (teacher fills the form — not an agent) → **Agent 1** (lesson plan) → teacher
approves → **Agent 2** (materials/slides) → **Agent 3** (worksheet) → teacher approves →
save & distribute → **Agent 4** (reflection & report) → **Agent 5** (differentiation) →
**Agent 6** (reminds pupils who haven't submitted).

## How to run (EASY — recommended for teachers)

1. Install Python 3.10+ (already present: 3.12).
2. Open **`apikey.txt`**, paste your Google API key, save (Ctrl+S).
   Get a key at <https://aistudio.google.com/apikey>.
3. **Double-click `mula.bat`** — the server starts and the browser opens automatically.
4. To stop: close the black window.

> ⚠️ The key in `apikey.txt` is secret. Do not share this folder with anyone while the key is inside it.

## How to run (alternative — env var)

```powershell
cd "C:\Users\HP\Desktop\PRESTIJ KAK AIMI"
$env:GOOGLE_API_KEY = "AIza..."
python server.py
```
(Optional) change the model — default `gemini-2.5-flash`:
```powershell
$env:GEMINI_MODEL = "gemini-2.5-pro"
```
Then open <http://localhost:8000>

No `pip install` needed — the server uses the Python standard library only.

## File structure

| File / folder | Role |
|---------------|------|
| `server.py` | Lightweight server: serves the app, proxies the Gemini API, saves output |
| `web/` | Single-page app (setup form + lesson plan / materials / worksheet views) |
| `prompts/agent1_rph.md` | Agent 1 system prompt (lesson plan) — **edit the format here** |
| `prompts/agent2_materials.md` | Agent 2 system prompt (materials / slides) |
| `prompts/agent3_worksheet.md` | Agent 3 system prompt (worksheet) |
| `prompts/agent4_reflection.md` | Agent 4 system prompt (reflection & report) |
| `prompts/agent5_differentiation.md` | Agent 5 system prompt (differentiated levels) |
| `prompts/agent6_reminder.md` | Agent 6 system prompt (reminds non-submitters) |
| `dskp_english_f3.json` | English Form 3 curriculum data (source of the dropdowns) |
| `bank_soalan.py` | **Question Bank** — SQLite store of approved questions (reuse) |
| `lessons.py` | **Lesson Library** — stores approved lessons (search/reopen/duplicate) |
| `bank_soalan.db` | Project database (Question Bank + Lesson Library tables; auto-created) |
| `output/` | Teacher-approved lesson plans & worksheets (auto-created) |
| `apikey.txt` | Your Google API key (kept out of the code) |
| `mula.bat` | One-click launcher |
| `backup_niat.py` | Backup script — zips `bank_soalan.db` + `output/` to `Documents\Niat Backups` |
| `supabase/` | Supabase schema (see `PATH_B_SETUP.md`) |
| `n8n/` | n8n reminder workflow (see `n8n/README.md`) |
| `Dockerfile`, `requirements.txt`, `.gcloudignore` | Cloud deployment files — see `DEPLOY_GCLOUD.md` |
| `private/` | **Local only, never committed/deployed**: personal documents (`dokumen-peribadi/`), copyrighted reference PDFs (`rujukan/`), school data with student PII (`data-sekolah/`) |

## Production container

The production image runs as a non-root user, listens on `$PORT`, stores only
temporary exports on its local filesystem, and requires Supabase for all durable
state. Its deny-by-default build context excludes credentials, local databases,
student files, generated outputs and development projects. Run the complete
preflight, local Docker commands and Cloud Run procedure in `DEPLOY_GCLOUD.md`.

## Backups

A Windows scheduled task **"Niat Backup"** runs `backup_niat.py` **daily at 5:00 PM**,
zipping the question bank and saved lessons to `Documents\Niat Backups` (keeps the last 14).
Run a backup manually any time with `python backup_niat.py`.

- Change the time / remove it: open **Task Scheduler** (search it in Start) → find **Niat Backup**.
- Or via PowerShell: `Unregister-ScheduledTask -TaskName "Niat Backup"` to remove it.

## Agent 6 auto-reminders (scheduled)

Windows desktop runs `remind_cron.py` every five minutes. In Cloud Run, Cloud Scheduler calls the
secret-protected `/api/internal/reminders` endpoint on the same interval. The watcher reads the due
date and time set by the teacher
in Google Classroom and does nothing before that time. As soon as an assignment is overdue, Agent 6
re-checks the submission list and sends one personalised nudge only to pupils who still have not
submitted. Automatic runs are capped at one reminder per pupil per assignment, so frequent checks
cannot create repeat emails; any later follow-up is supervised from the Niat app.

**What Agent 6 needs to run** (in order of preference for reading Classroom):

1. **The Apps Script hub** — `APPSCRIPT_HUB_URL` in `reminder_config.txt`. This is enough on its own.
   The hub runs as the teacher's own Google account, so it can read her classes' submissions
   (`submissions` / `overdue` actions in `niat_hub.gs`) **without** the MOE admin approving an OAuth
   app. If you re-deploy the hub for these actions, run **Deploy → Manage deployments → New version**
   and re-authorise so the new Classroom scopes take effect.
2. **Path B** (`client_secret.json`) — used instead for the Classroom reads when it's set up, but it
   is not required. See `PATH_B_SETUP.md`.

The hub also sends the mail either way. On Supabase, run **`supabase/migration_agent6.sql`** once — it
creates the `peringatan` (escalation counts) and `prestasi_murid` (performance → tone) tables, which
were missing from the original schema run. Without Supabase it falls back to a local `peringatan.db`
automatically. Agent 6 no longer crashes if either table is missing, but escalation and tone are
generic until they exist.

Register it as a **five-minute due-date watcher**:

```powershell
$py = (Get-Command python).Source
$dir = "C:\Users\HP\Desktop\PRESTIJ KAK AIMI"
$action = New-ScheduledTaskAction -Execute $py -Argument "remind_cron.py" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Niat Agent 6" -Action $action -Trigger $trigger -Settings $settings `
  -Description "Check Classroom due times and remind current non-submitters"
```

Run it manually any time with `python remind_cron.py`. Set `WITHIN_DAYS` (default 14) to change how far
back overdue assignments are checked. The automatic watcher sends at most one reminder per pupil for
each distinct class + assignment + due time.

## Curriculum data

`dskp_english_f3.json` holds the KSSM English Form 3 structure: 5 skills
(Listening, Speaking, Reading, Writing, Literature in Action), each with Content
Standards → Learning Standards, plus the 4 themes and the textbook (**Close-Up**).

> ✅ **Verified** against the official **DSKP KSSM English Form 3.pdf** — all Content &
> Learning Standard codes and wording match the KPM document (14 Content Standards,
> 36 Learning Standards across the 5 skills).

## Status & next steps

- ✅ Agent 1 (lesson plan), 2 (materials), 3 (worksheet) + teacher checkpoints + save + `.doc`/JSON export.
- ✅ **Daily Lesson Plan** in the **official JPN Perlis RPH format** (MINGGU, TARIKH, HARI, MASA,
  TINGKATAN/KELAS, MINIMUM JAM SETAHUN, MATA PELAJARAN, TEMA/BIDANG, TAJUK, STANDARD KANDUNGAN,
  STANDARD PEMBELAJARAN, OBJEKTIF PEMBELAJARAN, AKTIVITI PEMBELAJARAN, REFLEKSI) — BM field
  labels per the standard template, English lesson content. Source template: `erphperlis.pdf`.
  To change the format, edit `prompts/agent1_rph.md` and `planTableHTML` in `web/app.js`.
- ✅ **Question Bank** (`bank_soalan.py`): on "Approve", questions are stored (status
  `approved`, de-duplicated). New worksheets use **"bank first, AI fills the rest"** — approved
  questions for the same Learning Standard are taken first (least-used first), and AI only
  generates the remainder. Saves cost & avoids repetition. Stats at `GET /api/bank-stats`.
- ✅ **Distribute via Google** (Apps Script, run under the teacher's own moe-dl account): one script
  that (a) saves the lesson plan as a Google **Doc + PDF** in Drive and emails it to the teacher,
  (b) builds the worksheet as a Google **Form quiz**, (c) **posts it to Google Classroom** as an
  assignment with a teacher-set **due date & time**, (d) builds a **Google Slides** teaching deck,
  and (e) emails a **QR code** of the quiz. Only the Classroom service needs enabling.
- ✅ **Lesson Library** (`lessons.py`): every approved lesson saved to SQLite — search, reopen,
  re-download, duplicate, delete (📚 My Lessons).
- ✅ **Agent 4 — Reflect & Report** (`prompts/agent4_reflection.md`, `/api/reflect`): enter the class
  score/notes → Gemini writes the RPH **reflection** + a **class report**; reflection saves into the
  lesson. One click then generates an **adaptive remedial worksheet** for the weak areas.
- ✅ **CEFR Progress dashboard** (📊 Progress, `/api/progress`): per-class score charts + CEFR estimate.
- ✅ **Day-before reminder** (`reminder.py`, Windows task) + **one-tap prepare** (reminder link / in-app
  banner pre-fills the class & date from `timetable.json`).
- ✅ **Agent 6 — reminds non-submitters** (`prompts/agent6_reminder.md`, `/api/remind`, ⏰ Remind): reads
  Google Classroom submission states, the LLM writes a **personalised** nudge per pupil and **escalates**
  by how many times each was reminded (gentle → firm → email the teacher on the 3rd), then emails them.
  Tone is pitched to the pupil: their Form, their usual marks (strong → "don't let this one slip";
  struggling → gentlest wording plus one Malay line), first names, plain text, never shaming, and
  always with a way to ask for help. Escalation counts live in `peringatan.py`; a cap (default 4)
  stops the daily cron from spamming. The teacher **previews the drafted messages first** and then
  presses Send — nothing reaches a pupil unread. Runs automatically after the due date via
  **`remind_cron.py`** (see below); the cron only triggers — Agent 6 does the deciding.
- ⏸ **Offline model fallback** (TinyLlama/Ollama) — deferred pending the local model check.
- ✅ Direct Google Forms/Classroom API distribution is implemented for Agent 5. It becomes active after
  one-time OAuth consent and may still require MOE domain-admin approval; containers receive the token
  through `GOOGLE_OAUTH_TOKEN_JSON`, never as a copied credential file.
