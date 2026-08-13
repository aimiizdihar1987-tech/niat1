#!/usr/bin/env python3
"""Agent 6 due-date watcher for Windows Task Scheduler or Cloud Scheduler.

The trigger may run frequently, but Agent 6 sends at most one automatic
reminder per pupil for each exact class + assignment + due time. Later
follow-ups remain supervised in the Niat UI.
"""

import os
import sys
from datetime import datetime

import server  # importing does not start the web server

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTAINER_MODE = os.environ.get("NIAT_CONTAINER", "").strip().lower() in ("1", "true", "yes")
LOG = (os.environ.get("NIAT_REMINDER_LOG", "").strip()
       or ("/tmp/niat-reminders.log" if CONTAINER_MODE
           else os.path.join(ROOT, "reminders_log.txt")))


def _teacher_email():
    cfg = server._read_reminder_cfg()
    return (cfg.get("TEACHER_EMAIL", "") or "").split(",")[0].strip()


def log(message):
    stamp = datetime.now().isoformat(timespec="seconds")
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write("[{}] AGENT6 {}\n".format(stamp, message))
    except OSError:
        pass
    print(message)


def _overdue_assignments(within):
    """Return (assignments, source); assignments=None means lookup failure."""
    try:
        import niat_google
        if niat_google.available(interactive=False):
            return niat_google.list_overdue_coursework(within_days=within), "google"
    except Exception as exc:  # fall back to the Apps Script hub
        log("Path B unavailable ({}); using the Apps Script hub.".format(exc))
    result = server._post_hub({"action": "overdue", "withinDays": within})
    if not result.get("ok"):
        log("Hub could not list overdue work: {}".format(result.get("error", "?")))
        return None, "hub"
    return result.get("assignments", []), "hub"


def run():
    """Run one due-date scan and return a JSON-safe summary."""
    within = int(os.environ.get("WITHIN_DAYS", "14"))
    teacher_email = _teacher_email()
    overdue, source = _overdue_assignments(within)
    log("Source: {}".format(source))
    if overdue is None:
        log("Could not check overdue work; no reminders were sent.")
        return {"ok": False, "source": source, "checked": 0, "sent": 0,
                "error": "Could not list overdue assignments."}
    if not overdue:
        log("No overdue assignments in the last {} days.".format(within))
        return {"ok": True, "source": source, "checked": 0, "sent": 0}

    total_sent = 0
    for assignment in overdue:
        result = server.remind_agent({
            "class_name": assignment["class_name"],
            "coursework_title": assignment["coursework_title"],
            "due_iso": assignment["due_iso"],
            "teacher_email": teacher_email,
            "teacher_name": os.environ.get("TEACHER_NAME", "").strip(),
            "max_reminders": 1,
        })
        if not result.get("ok"):
            log("{} / {} - skipped: {}".format(
                assignment["class_name"], assignment["coursework_title"],
                result.get("error", "?")))
            continue
        sent = int(result.get("sent", 0) or 0)
        total_sent += sent
        log("{} / {} - sent {}".format(
            assignment["class_name"], assignment["coursework_title"], sent))

    log("Done - checked {}, sent {}.".format(len(overdue), total_sent))
    return {"ok": True, "source": source, "checked": len(overdue),
            "sent": total_sent}


def main():
    if not run().get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
