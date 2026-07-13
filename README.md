# Niat — AI-Powered Classroom (Phase 1 MVP)

A web app for teachers to automatically generate a **Daily Lesson Plan (DLP/RPH)** and a
**multiple-choice worksheet** for **English Language (KSSM Form 3, CEFR B1 Low)**, powered by Google Gemini.

Phase 1 flow: **Agent 1** (setup) → **Agent 2** (lesson plan) → teacher approves →
**Agent 3** (worksheet) → teacher approves → save & download.

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
| `web/` | Single-page app (Agent 1 UI + lesson plan / worksheet views) |
| `prompts/agent2_rph.md` | Agent 2 system prompt (lesson plan) — **edit the format here** |
| `prompts/agent3_worksheet.md` | Agent 3 system prompt (worksheet) |
| `dskp_english_f3.json` | English Form 3 curriculum data (source of the dropdowns) |
| `bank_soalan.py` | **Question Bank** — SQLite store of approved questions (reuse) |
| `lessons.py` | **Lesson Library** — stores approved lessons (search/reopen/duplicate) |
| `bank_soalan.db` | Project database (Question Bank + Lesson Library tables; auto-created) |
| `output/` | Teacher-approved lesson plans & worksheets (auto-created) |
| `apikey.txt` | Your Google API key (kept out of the code) |
| `mula.bat` | One-click launcher |
| `backup_niat.py` | Backup script — zips `bank_soalan.db` + `output/` to `Documents\Niat Backups` |

## Backups

A Windows scheduled task **"Niat Backup"** runs `backup_niat.py` **daily at 5:00 PM**,
zipping the question bank and saved lessons to `Documents\Niat Backups` (keeps the last 14).
Run a backup manually any time with `python backup_niat.py`.

- Change the time / remove it: open **Task Scheduler** (search it in Start) → find **Niat Backup**.
- Or via PowerShell: `Unregister-ScheduledTask -TaskName "Niat Backup"` to remove it.

## Curriculum data

`dskp_english_f3.json` holds the KSSM English Form 3 structure: 5 skills
(Listening, Speaking, Reading, Writing, Literature in Action), each with Content
Standards → Learning Standards, plus the 4 themes and the textbook (**Close-Up**).

> ✅ **Verified** against the official **DSKP KSSM English Form 3.pdf** — all Content &
> Learning Standard codes and wording match the KPM document (14 Content Standards,
> 36 Learning Standards across the 5 skills).

## Status & next steps

- ✅ Agent 1, 2, 3 + teacher checkpoints + save + `.doc`/JSON export.
- ✅ **Daily Lesson Plan** in the **official JPN Perlis RPH format** (MINGGU, TARIKH, HARI, MASA,
  TINGKATAN/KELAS, MINIMUM JAM SETAHUN, MATA PELAJARAN, TEMA/BIDANG, TAJUK, STANDARD KANDUNGAN,
  STANDARD PEMBELAJARAN, OBJEKTIF PEMBELAJARAN, AKTIVITI PEMBELAJARAN, REFLEKSI) — BM field
  labels per the standard template, English lesson content. Source template: `erphperlis.pdf`.
  To change the format, edit `prompts/agent2_rph.md` and `planTableHTML` in `web/app.js`.
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
- ✅ **Reflect & Report agent** (`prompts/agent_reflection.md`, `/api/reflect`): enter the class
  score/notes → Gemini writes the RPH **reflection** + a **class report**; reflection saves into the
  lesson. One click then generates an **adaptive remedial worksheet** for the weak areas.
- ✅ **CEFR Progress dashboard** (📊 Progress, `/api/progress`): per-class score charts + CEFR estimate.
- ✅ **Writing/Speaking grader** (✍️ Grade, `prompts/agent_rubric.md`, `/api/grade`): paste a pupil's
  response → CEFR band + 4-criteria scores + feedback.
- ✅ **Day-before reminder** (`reminder.py`, Windows task) + **one-tap prepare** (reminder link / in-app
  banner pre-fills the class & date from `timetable.json`).
- ⏸ **Offline model fallback** (TinyLlama/Ollama) — deferred pending the local model check.
- 🔜 Phase 2+ (full hands-off automation): direct Google Forms/Classroom **API** distribution without the
  paste step — needs a Google Cloud project, OAuth, and likely MOE domain-admin approval.
