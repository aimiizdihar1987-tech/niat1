# Niat — Command Cheat-Sheet

All commands are for **Windows PowerShell**, run from the project folder
(`C:\Users\HP\Desktop\PRESTIJ KAK AIMI`) unless noted.

---

## 🟢 Everyday use
| Action | How |
|--------|-----|
| **Start Niat** | Double-click **`mula.bat`** (starts the server + opens the browser) |
| **Stop it** | Close the black window, or press **Ctrl+C** in it |

That's all you need day-to-day. Everything below is for setup / maintenance.

---

## ⚙️ Run manually (instead of mula.bat)
```powershell
cd "C:\Users\HP\Desktop\PRESTIJ KAK AIMI"
python server.py
```
The Gemini key is read automatically from `apikey.txt`.
To override for one session only:
```powershell
$env:GOOGLE_API_KEY = "your-key-here"
$env:GEMINI_MODEL  = "gemini-2.5-pro"   # optional: higher quality, slower
```
Then open <http://localhost:8000>

---

## 💾 Backups
```powershell
python backup_niat.py                              # back up right now
Get-ScheduledTask        -TaskName "Niat Backup"   # check the daily task
Start-ScheduledTask      -TaskName "Niat Backup"   # force a backup now
Disable-ScheduledTask    -TaskName "Niat Backup"   # pause it
Enable-ScheduledTask     -TaskName "Niat Backup"   # resume it
Unregister-ScheduledTask -TaskName "Niat Backup"   # remove it
```
Backups are saved to: `C:\Users\HP\Documents\Niat Backups` (last 14 kept).

---

## 🔧 Maintenance / sanity checks
```powershell
python --version                                      # confirm Python is installed
python -m py_compile server.py bank_soalan.py backup_niat.py   # validate code after edits
```
- Question Bank stats (in browser, while the server runs): <http://localhost:8000/api/bank-stats>

---

## 🔜 Path B — full Google automation (only when you have credentials)
See `PATH_B_SETUP.md` first. Once `client_secret.json` is in the folder:
```powershell
pip install google-api-python-client google-auth google-auth-oauthlib
```

---

## 🧩 Claude Code plugins (inside the Claude Code app, not PowerShell)
- Open the **plugin manager** (the `/plugin` command in an interactive Claude Code terminal)
  to install **context7**, **playwright**, **code-review**.
- Then invoke them as slash commands, e.g. **`/code-review`**.
- Note: some panels (`/permissions`, `/config`) only open in a full interactive `claude` terminal.

---

## 📤 Distribute a lesson (current / Path A)
No command — in the app: **Generate → Approve → Distribute (Prototype) → Copy script**,
then paste & **Run** it at <https://script.google.com>.
