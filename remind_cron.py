#!/usr/bin/env python3
"""
Niat — Agent 6 cron layer. Runs Agent 6 automatically for every assignment
whose DUE DATE has passed.

The cron is only the TRIGGER (a scheduled job) — the decision-making is still
Agent 6 in server.py: for each overdue assignment it finds who hasn't submitted,
the LLM writes a personalised nudge per pupil, escalates by how many times each
has been reminded, and emails them (and the teacher after the 3rd reminder).

Scheduled daily via a Windows scheduled task "Niat Agent 6" (see README).
Run manually any time:  python remind_cron.py
Env: WITHIN_DAYS (how far back to look, default 14), NIAT_STORAGE, NIAT_ENGINE.

Nothing is sent unless Google (Path B) is set up (client_secret.json) AND the
Apps Script mail hub is configured (APPSCRIPT_HUB_URL in reminder_config.txt).
"""

import os
from datetime import datetime

import server  # importing does NOT start the web server (guarded by __main__)

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "reminders_log.txt")


def _teacher_email():
    """Teacher address for escalation follow-ups — from reminder_config.txt."""
    cfg = server._read_reminder_cfg()
    return (cfg.get("TEACHER_EMAIL", "") or "").split(",")[0].strip()


def log(text):
    stamp = datetime.now().isoformat(timespec="seconds")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[{}] AGENT6 {}\n".format(stamp, text))
    print(text)


def main():
    try:
        import niat_google
    except Exception as e:  # noqa: BLE001
        log("Path B module error: {}".format(e))
        return
    if not niat_google.available():
        log("Google (Path B) not set up — cron idle (no client_secret.json).")
        return

    within = int(os.environ.get("WITHIN_DAYS", "14"))
    teacher_email = _teacher_email()
    overdue = niat_google.list_overdue_coursework(within_days=within)
    if not overdue:
        log("No overdue assignments in the last {} days — nothing to remind.".format(within))
        return

    total_sent = 0
    for a in overdue:
        res = server.remind_agent({
            "class_name": a["class_name"],
            "coursework_title": a["coursework_title"],
            "due_iso": a["due_iso"],
            "teacher_email": teacher_email,
        })
        if not res.get("ok"):
            log("{} / {} — SKIPPED: {}".format(
                a["class_name"], a["coursework_title"], res.get("error", "?")))
            continue
        sent = res.get("sent", 0)
        total_sent += sent
        log("{} / {} — {} (sent {}{})".format(
            a["class_name"], a["coursework_title"], res.get("ringkasan", ""),
            sent, ", capped {}".format(res["capped"]) if res.get("capped") else ""))
    log("Done — {} assignment(s) checked, {} reminder email(s) sent.".format(
        len(overdue), total_sent))


if __name__ == "__main__":
    main()
