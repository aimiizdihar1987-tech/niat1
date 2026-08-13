#!/usr/bin/env python3
"""
Niat Watchdog — keeps the Niat server alive.

Runs every 30 minutes via the Windows scheduled task "Niat Watchdog":
checks http://127.0.0.1:8050/api/health and silently restarts the server
(windowless pythonw) if it is not responding. Python stdlib only.
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "watchdog_log.txt")
ALERT = os.path.join(ROOT, "reminder_alert.json")
DETACHED_PROCESS = 0x00000008
# Don't retry a failed alert on every 30-minute pass — the network is usually
# still down, and it would fill the log with identical lines.
ALERT_RETRY_HOURS = 2


def log(msg):
    stamp = datetime.now().isoformat(timespec="seconds")
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("[{}] {}\n".format(stamp, msg))
    except OSError:
        pass


def healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8050/api/health", timeout=6) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def flush_reminder_alerts():
    """Tell the teacher about any reminder that reached nobody.

    reminder.py cannot alert on its own failure — when every channel fails the
    network is usually down, so the alert would fail too. It records the miss in
    reminder_alert.json instead and this runs every 30 min, delivering the alert
    shortly after connectivity returns rather than a day later."""
    if not os.path.isfile(ALERT):
        return
    try:
        with open(ALERT, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return
    missed = state.get("missed") or []
    if not missed:
        return
    last = state.get("last_try")
    if last:
        try:
            if datetime.fromisoformat(last) > \
                    datetime.now() - timedelta(hours=ALERT_RETRY_HOURS):
                return  # tried recently - wait for the next window
        except ValueError:
            pass

    lines = ["Niat could not deliver these class reminders:", ""]
    for m in missed:
        lines.append("- {} (tried {})".format(m.get("for", "?"), m.get("at", "?")))
    lines += ["", "Those lessons still need preparing. Open Niat: http://127.0.0.1:8050"]
    body = "\n".join(lines)

    try:
        import reminder  # reuse its senders + config rather than duplicating them
        cfg = reminder.read_config()
        email_st = reminder.send_email(
            cfg, "Niat: a class reminder did not reach you", body)
        tg_st = reminder.send_telegram(cfg, body)
        ok = reminder.delivered(email_st, tg_st)
    except Exception as e:  # noqa: BLE001 - watchdog must never crash
        log("missed-reminder alert errored: {}".format(str(e)[:160]))
        return

    if ok:
        try:
            os.remove(ALERT)
        except OSError:
            pass
        log("alerted teacher to {} missed reminder(s) | {} | {}".format(
            len(missed), email_st, tg_st))
        return
    state["last_try"] = datetime.now().isoformat(timespec="seconds")
    try:
        with open(ALERT, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass
    log("still cannot alert about {} missed reminder(s) | {} | {}".format(
        len(missed), email_st, tg_st))


def main():
    flush_reminder_alerts()  # before the health check - runs even when all is well
    if healthy():
        return  # all good - stay quiet
    env = dict(os.environ, PORT="8050", HOST="0.0.0.0")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = "pythonw"
    subprocess.Popen([pythonw, os.path.join(ROOT, "server.py")],
                     cwd=ROOT, env=env, creationflags=DETACHED_PROCESS,
                     close_fds=True)
    log("server was DOWN - restarted")


if __name__ == "__main__":
    main()
