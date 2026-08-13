#!/usr/bin/env python3
"""
Niat Reminder — a day-before reminder for the teacher's English classes.

Reads timetable.json (the teacher's weekly classes); for any class scheduled
TOMORROW it composes a short English reminder and:
  - emails it (if reminder_config.txt has a Gmail sender + app password), and
  - writes it to reminders_log.txt together with a one-tap WhatsApp (wa.me) link.

Runs daily via the Windows scheduled task "Niat Reminder". Python stdlib only.
Run manually any time:  python reminder.py
"""

import json
import os
import smtplib
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.abspath(__file__))
TIMETABLE = os.path.join(ROOT, "timetable.json")
CONFIG = os.path.join(ROOT, "reminder_config.txt")
LOG = os.path.join(ROOT, "reminders_log.txt")
# Written when a reminder reaches nobody; niat_watchdog.py delivers the alert
# once a channel works again and deletes this file.
ALERT = os.path.join(ROOT, "reminder_alert.json")
NIAT_URL = "http://localhost:8050"


def get_lan_ip():
    """Best-effort local network IP so email links work on other devices
    on the same WiFi (not just on this PC). Falls back to localhost."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def read_config():
    cfg = {}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg


def load_timetable():
    """This reminder script is Cikgu Aimi's own (Gmail/Telegram/WhatsApp
    numbers in reminder_config.txt are hers) — timetable.json now holds
    every teacher's schedule keyed by username, so pick her branch here."""
    try:
        with open(TIMETABLE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    return (data.get("teachers") or {}).get("aimiizdihar", {})


def compose(teacher, date_str, day, classes, iso_date=""):
    lines = []
    for c in classes:
        t = c.get("time", "")
        klass = c.get("class", "")
        link = NIAT_URL
        if klass:
            link += "?class=" + urllib.parse.quote(klass)
            if iso_date:
                link += "&date=" + iso_date
        where = "{} at {}".format(klass, t) if t else klass
        lines.append("- {}\n  Prepare lesson plan -> {}".format(where, link))
    return (
        "Hi {}!\n\n".format(teacher or "Teacher")
        + "Tomorrow ({}, {}) you have an English class with:\n".format(day, date_str)
        + "\n".join(lines)
        + "\n\nWould you like to prepare the lesson plan? Tap a link above to open Niat."
    )


def compose_email(teacher, date_str, day, classes, iso_date=""):
    """Concise, proper English body for the email reminder."""
    link_lines = []
    for c in classes:
        t = c.get("time", "")
        klass = c.get("class", "")
        label = "{} ({})".format(klass, t) if t else klass
        link = NIAT_URL
        if klass:
            link += "?class=" + urllib.parse.quote(klass)
            if iso_date:
                link += "&date=" + iso_date
        link_lines.append("  - {} -> {}".format(label, link))
    return (
        "Dear {},\n\n".format(teacher or "Teacher")
        + "You have English class(es) tomorrow, {}, {}:\n\n".format(day, date_str)
        + "\n".join(link_lines)
        + "\n\nWould you like to prepare tomorrow's lesson? Click a class above "
        "to auto-generate the lesson plan (RPH) and worksheet in Niat.\n\n"
        "If your lessons are ready, please ignore this email.\n\n"
        "Thank you,\nNiat - your AI teaching assistant"
    )


def send_email(cfg, subject, body):
    sender = cfg.get("SENDER_EMAIL", "")
    pw = cfg.get("SENDER_APP_PASSWORD", "")
    to_raw = cfg.get("TEACHER_EMAIL", "")
    recipients = [a.strip() for a in to_raw.replace(";", ",").split(",") if a.strip()]
    if not recipients:
        return "dry-run (recipient email not configured)"
    if not (sender and pw):
        hook = send_email_webhook(cfg, subject, body, recipients)
        return hook or "dry-run (SMTP and email webhook not configured)"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    ctx = ssl.create_default_context()
    last = ""
    # Try up to 3 times, alternating port 465 (SSL) and 587 (STARTTLS) —
    # school networks are flaky and occasionally drop one of them.
    for attempt in range(3):
        try:
            if attempt % 2 == 0:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=30) as s:
                    s.login(sender, pw)
                    s.send_message(msg)
            else:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
                    s.starttls(context=ctx)
                    s.login(sender, pw)
                    s.send_message(msg)
            return "emailed to " + ", ".join(recipients)
        except Exception as e:  # noqa: BLE001
            last = str(e)[:160]
            time.sleep(5)
    # SMTP blocked (common on school WiFi) -> fall back to the HTTPS
    # Apps Script mail webhook, which no firewall blocks.
    hook = send_email_webhook(cfg, subject, body, recipients)
    if hook:
        return hook
    return "email FAILED after 3 tries: " + last


def send_email_webhook(cfg, subject, body, recipients):
    """Send mail over HTTPS via the teacher's own Apps Script Web App.
    Needs APPSCRIPT_MAIL_URL in reminder_config.txt (one-time deploy of
    niat_mail_webhook.gs). Returns a status string, or '' if not configured."""
    url = cfg.get("APPSCRIPT_MAIL_URL", "").strip()
    if not url:
        return ""
    payload = json.dumps({
        "to": ", ".join(recipients),
        "subject": subject,
        "body": body,
        "key": cfg.get("APPSCRIPT_MAIL_KEY", ""),
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"content-type": "application/json"})
    # Retry like send_email does — school WiFi drops DNS for a few seconds at
    # a time, and a single attempt turns that into a missed reminder.
    last = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                resp = r.read().decode("utf-8", "ignore")
            if "ok" in resp.lower():
                return "emailed via webhook to " + ", ".join(recipients)
            return "webhook response: " + resp.strip()[:160]
        except Exception as e:  # noqa: BLE001
            last = str(e)[:160]
            if attempt < 2:
                time.sleep(15)
    return "webhook FAILED after 3 tries: " + last


def wa_link(cfg, body):
    num = cfg.get("TEACHER_WHATSAPP", "").replace("+", "").replace(" ", "")
    if not num:
        return ""
    return "https://wa.me/{}?text={}".format(num, urllib.parse.quote(body))


def send_whatsapp(cfg, body):
    """Auto-send the reminder to the teacher's own WhatsApp via the free
    CallMeBot relay. Needs a one-time activation to get CALLMEBOT_APIKEY
    (see reminder_config.txt). Returns a short status string."""
    num = cfg.get("TEACHER_WHATSAPP", "").replace("+", "").replace(" ", "")
    key = cfg.get("CALLMEBOT_APIKEY", "").strip()
    if not num:
        return "WhatsApp skipped (no TEACHER_WHATSAPP set)"
    if not key:
        return "WhatsApp NOT sent (no CALLMEBOT_APIKEY - do the 1-time setup in reminder_config.txt)"
    url = "https://api.callmebot.com/whatsapp.php?phone={}&text={}&apikey={}".format(
        urllib.parse.quote(num),
        urllib.parse.quote(body),
        urllib.parse.quote(key),
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            resp = r.read().decode("utf-8", "ignore")
        low = resp.lower()
        if "queued" in low or "sent" in low or "message to" in low:
            return "WhatsApp sent to " + num
        return "WhatsApp response: " + resp.strip()[:180]
    except Exception as e:  # noqa: BLE001
        return "WhatsApp FAILED: " + str(e)[:180]


def send_telegram(cfg, body):
    """Auto-send the reminder to the teacher's Telegram (official Bot API, free).
    Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in reminder_config.txt."""
    token = cfg.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = cfg.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        return "Telegram skipped (no TELEGRAM_BOT_TOKEN set)"
    if not chat:
        return "Telegram NOT sent (no TELEGRAM_CHAT_ID - open the bot and press START first)"
    url = "https://api.telegram.org/bot{}/sendMessage".format(token)
    data = urllib.parse.urlencode({"chat_id": chat, "text": body}).encode("utf-8")
    # Telegram is the most reliable channel in practice, so give it the same
    # 3 tries as the others rather than losing the whole reminder to a blip.
    last = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, data=data, timeout=30) as r:
                resp = json.loads(r.read().decode("utf-8"))
            if resp.get("ok"):
                return "Telegram sent (chat {})".format(chat)
            return "Telegram response: " + json.dumps(resp)[:180]
        except Exception as e:  # noqa: BLE001
            last = str(e)[:180]
            if attempt < 2:
                time.sleep(15)
    return "Telegram FAILED after 3 tries: " + last


# The exact status fragments that mean a channel really delivered. Every
# sender catches its own errors and returns a string, so without this main()
# would always exit 0 and the scheduled task's "Last Result" could never tell
# a delivered reminder from a total failure.
DELIVERED_MARKERS = ("emailed to ", "emailed via webhook to ",
                     "Telegram sent (", "WhatsApp sent to ")


def delivered(*statuses):
    """How many of the given channel statuses mean the reminder got out."""
    return sum(1 for s in statuses
               if any(m in (s or "") for m in DELIVERED_MARKERS))


def log(text):
    stamp = datetime.now().isoformat(timespec="seconds")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[{}] {}\n".format(stamp, text))


def record_failure(day, date_str, statuses):
    """Leave a marker saying this reminder reached nobody.

    Alerting from here is pointless — "every channel failed" almost always
    means the network itself was down, so the alert would fail too. Instead
    niat_watchdog.py (every 30 min) picks this up and tells the teacher as
    soon as a channel works again, then deletes the file."""
    missed = []
    try:
        with open(ALERT, encoding="utf-8") as f:
            missed = json.load(f).get("missed", [])
    except (OSError, ValueError):
        pass
    label = "{} {}".format(day, date_str)
    if not any(m.get("for") == label for m in missed):
        missed.append({
            "for": label,
            "at": datetime.now().isoformat(timespec="seconds"),
            "statuses": [s for s in statuses if s],
        })
    try:
        with open(ALERT, "w", encoding="utf-8") as f:
            json.dump({"missed": missed}, f, indent=2)
    except OSError:
        pass


def main():
    cfg = read_config()
    tt = load_timetable()
    teacher = tt.get("teacher_name") or "Teacher"

    global NIAT_URL
    host = cfg.get("REMINDER_HOST", "").strip() or get_lan_ip()
    NIAT_URL = "http://{}:8050".format(host)

    tomorrow = datetime.now() + timedelta(days=1)
    day = tomorrow.strftime("%A")            # e.g. Monday
    date_str = tomorrow.strftime("%d %b %Y")  # e.g. 06 Jul 2026

    classes = [c for c in tt.get("classes", [])
               if c.get("day", "").strip().lower() == day.lower()]

    if not classes:
        log("No English classes tomorrow ({} {}).".format(day, date_str))
        print("No classes tomorrow ({}).".format(day))
        return

    iso = tomorrow.strftime("%Y-%m-%d")
    body = compose(teacher, date_str, day, classes, iso)
    email_body = compose_email(teacher, date_str, day, classes, iso)
    subject = "Niat: prepare tomorrow's English lesson? ({}, {})".format(day, date_str)
    email_status = send_email(cfg, subject, email_body)
    tg_status = send_telegram(cfg, body)
    wa_status = send_whatsapp(cfg, body)
    link = wa_link(cfg, body)

    log("REMINDER {} {} | {} | {} | {} | link: {}\n{}\n---".format(
        day, date_str, email_status, tg_status, wa_status, link or "(no number set)", body))
    print(subject)
    print(body)
    print("\nEmail:", email_status)
    print("Telegram:", tg_status)
    print("WhatsApp:", wa_status)
    print("WhatsApp click-to-send:", link or "(set TEACHER_WHATSAPP in reminder_config.txt)")

    # Exit non-zero when nothing got through, so Task Scheduler's "Last Result"
    # is a delivery signal. 0 = the teacher was reached on some channel.
    if not delivered(email_status, tg_status, wa_status):
        log("ALL CHANNELS FAILED for {} {} - the reminder reached nobody.".format(
            day, date_str))
        record_failure(day, date_str, (email_status, tg_status, wa_status))
        print("\nALL CHANNELS FAILED - the reminder reached nobody.")
        print("Recorded in reminder_alert.json; the watchdog will alert you "
              "once a channel works again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
