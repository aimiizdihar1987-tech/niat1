# Niat — Running it reliably ("always-on")

## Current setup (done) — auto-start on this PC
A launcher was added to your Windows **Startup folder**:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Niat Server.bat`

- It runs the server **windowless** (via `pythonw`) on **port 8050** every time you log in.
- So Niat is **always available** at **http://localhost:8050/** — no need to double-click anything.
- **To stop auto-start:** delete that `Niat Server.bat` from the Startup folder.
- **To start it now without rebooting:** double-click that file (or `mula.bat`).
- Only **one** server can use 8050 — if you also run `mula.bat`, close one.

> This fixes the "link can't be reached" problem: the server is now your own background
> process, independent of any chat/assistant session.

## Later option — true cloud hosting (multi-device, always-on anywhere)
Only needed if other people/devices must reach it (not just this PC). It's a bigger, deliberate step:
- Host the Python app on a service like **Render**, **Railway**, or **PythonAnywhere** (free tiers exist).
- Put the Gemini key in the host's **secret/ENV settings** (never in the page).
- Add **login/authentication** and serve over **HTTPS** (see SECURITY.md).
- The Question Bank/Lesson Library SQLite would move to the host (or a managed DB) for multi-user.

For a single teacher, the local auto-start above is the simplest and most private choice.
