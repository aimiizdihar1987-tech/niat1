# Niat + n8n (visual workflow pilot)

n8n is a free, open-source visual workflow tool. It runs **entirely on this
laptop** — no student or teacher data leaves the machine except the messages
it sends (same as the Python reminder).

The first pilot workflow is **"Niat Reminder"** — a visual copy of
`reminder.py`. It reads the SAME `timetable.json` and `reminder_config.txt`
as the Python version, so there is one source of truth. Every day at 5:00 PM
(Malaysia time) it checks tomorrow's timetable and, if there are English
classes, sends the teacher:

- a **Telegram** message (bot already configured)
- an **email** via the Apps Script webhook (works on school WiFi)
- a **WhatsApp** message via CallMeBot (only after the one-time
  `CALLMEBOT_APIKEY` activation in `reminder_config.txt`)

## One-time setup

1. Double-click `START_N8N.bat` (in this folder). Wait for
   "Editor is now accessible".
2. Open http://localhost:5678 in your browser.
3. First visit only: create the owner account (any email + password —
   it is stored locally on this laptop, nothing is sent to n8n.io).
4. Open the **Niat Reminder** workflow (already imported).
5. Click **Execute workflow** once to test — you should receive the
   Telegram message and email within a few seconds.
6. Flip the **Active** toggle (top right) to ON.

## Daily use

- n8n must be running for the 5 PM trigger to fire — keep `START_N8N.bat`
  running, or add it to Windows Startup (shell:startup) next to Niat.
- Every run (success or failure) is recorded under **Executions** in the
  n8n sidebar — this replaces reading `reminders_log.txt`.
- To change the message, times, or add channels: edit the workflow visually,
  no Python needed.

## Safety net

The original Python reminder ("Niat Reminder" Windows scheduled task) is
still active. While piloting, you will get the reminder TWICE (once from
each system). Once you trust the n8n version, disable one of them:

- keep n8n → disable the Windows task: Task Scheduler → "Niat Reminder" → Disable
- keep Python → in n8n, flip the workflow's Active toggle off

The watchdog and backup agents stay in Task Scheduler on purpose — the
watchdog must survive when other services crash, so it should not live
inside n8n.

## Re-import after editing the JSON

If `niat_reminder_workflow.json` is edited by hand, re-import with:

    %APPDATA%\npm\n8n.cmd import:workflow --input="C:\Users\HP\Desktop\PRESTIJ KAK AIMI\n8n\niat_reminder_workflow.json"

(Exports made from the n8n editor UI can be saved back over this file to
keep the project folder as the single source of truth.)
