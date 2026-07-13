# Niat — Security & PDPA Notes

Niat is a **local, single-teacher** tool. Most risk is low because nothing is exposed online.
This file lists what's safe, what to watch, and quick hardening steps.

## ✅ Already safe
- **Localhost only.** The server binds to `127.0.0.1` (see `HOST` in `server.py`), so it is **not reachable from the network/internet** — only from this PC's browser.
- **API key never reaches the browser.** Lesson/worksheet generation is proxied through the server; the Gemini key stays server-side.
- **Student data stays local.** The DELIMa ID list and outputs live only on this PC (and your own Google Drive when you choose to distribute).
- **You approve everything.** Human-in-the-loop before any distribution.

## ⚠️ Watch these (sensitive files on disk, in plain text)
| File | Contains | Advice |
|------|----------|--------|
| `apikey.txt` | Your Gemini API key | Don't share the folder with this inside. Rotate the key if it leaks. |
| `reminder_config.txt` | Email app-password / WhatsApp no. | Same — keep private. |
| `ID DELIMA MOE MURID SMKKPs 2026.pdf` | Student IDs (PII) | Personal data — keep on this PC only; don't email/upload it. |
| `bank_soalan.db`, `output/`, `Documents\Niat Backups` | Lessons, questions, scores | Local only; fine, but they're unencrypted. |

## 🔒 Quick hardening (optional)
1. **Don't run on `0.0.0.0`.** Keep `HOST=127.0.0.1` (default). Only change it if you deliberately want other devices to reach it — then add a password.
2. **Lock your PC** when away (these files are readable by anyone on this Windows account).
3. **Rotate the API key** periodically at <https://aistudio.google.com/apikey> (especially the one shared in chat earlier).
4. **PDPA:** only collect what you need. The Google Form's "collect email" gathers pupil emails — that's within your school's Google Workspace, which is appropriate; don't export it elsewhere.
5. **Parents are not contacted** by design (student reminders only) — keeps the data footprint smaller.

## If you ever host it online (see HOSTING.md)
Going beyond localhost changes the risk a lot — you'd need authentication, HTTPS, and to keep the API key in a server secret (never in the page). Treat that as a separate, deliberate project.
