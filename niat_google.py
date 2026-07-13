#!/usr/bin/env python3
"""
Niat — Path B (direct Google API) integration SCAFFOLD.

⚠️ STATUS: ready but UNTESTED. It does nothing until you complete the Google
Cloud setup in PATH_B_SETUP.md and drop `client_secret.json` in this folder.
It is imported LAZILY (only when the /api/distribute-direct endpoint is called),
so it never affects the normal stdlib server.

When activated it removes the copy-paste-script step: Niat itself creates the
Google Form quiz and posts it to Google Classroom with a due date.

Requires (one-time):
    pip install google-api-python-client google-auth google-auth-oauthlib

Scopes used (must be approved for your moe-dl domain):
    forms.body · drive.file · classroom.courses.readonly · classroom.coursework.me
"""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(ROOT, "client_secret.json")
TOKEN = os.path.join(ROOT, "token.json")
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me",
]


def available():
    """True only if the Google libraries AND credentials are present."""
    if not os.path.exists(CLIENT_SECRET):
        return False
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        return True
    except ImportError:
        return False


def _services():
    """Authenticate (browser consent on first run) and return (forms, classroom)."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    forms = build("forms", "v1", credentials=creds)
    classroom = build("classroom", "v1", credentials=creds)
    return forms, classroom


def create_quiz(forms, worksheet):
    """Create a Google Form quiz from a worksheet dict. Returns (formId, responderUri)."""
    title = worksheet.get("tajuk") or "English Quiz"
    form = forms.forms().create(body={"info": {"title": title, "documentTitle": title}}).execute()
    form_id = form["formId"]
    # Turn it into a quiz
    forms.forms().batchUpdate(formId=form_id, body={"requests": [
        {"updateSettings": {"settings": {"quizSettings": {"isQuiz": True}},
                            "updateMask": "quizSettings.isQuiz"}}
    ]}).execute()
    # Add the MCQ items with grading
    reqs = []
    for i, q in enumerate(worksheet.get("soalan", [])):
        opts = q.get("pilihan", [])
        letter = q.get("jawapan_betul", "A")
        idx = "ABCD".find(letter)
        correct = opts[idx] if 0 <= idx < len(opts) else (opts[0] if opts else "")
        reqs.append({"createItem": {
            "item": {
                "title": q.get("soalan", ""),
                "questionItem": {"question": {
                    "required": True,
                    "grading": {"pointValue": int(q.get("markah", 1) or 1),
                                "correctAnswers": {"answers": [{"value": correct}]}},
                    "choiceQuestion": {"type": "RADIO",
                                       "options": [{"value": o} for o in opts]}}}},
            "location": {"index": i}}})
    if reqs:
        forms.forms().batchUpdate(formId=form_id, body={"requests": reqs}).execute()
    return form_id, form.get("responderUri", "")


def post_to_classroom(classroom, class_name, title, description, form_url, due_iso, max_points):
    """Find the course by name and create coursework with the form link + due date."""
    from datetime import datetime
    courses = classroom.courses().list(courseStates=["ACTIVE"]).execute().get("courses", [])
    target = None
    want = (class_name or "").lower()
    for c in courses:
        nm = (c.get("name") or "").lower()
        if want and (nm == want or want in nm):
            target = c
            break
    if not target:
        return {"ok": False, "error": 'No active Classroom matching "%s"' % class_name}
    work = {
        "title": title, "description": description,
        "materials": [{"link": {"url": form_url, "title": title}}],
        "workType": "ASSIGNMENT", "state": "PUBLISHED",
        "maxPoints": max_points or 100,
    }
    if due_iso:
        d = datetime.fromisoformat(due_iso)  # local; convert to UTC for the API
        import time
        u = datetime.utcfromtimestamp(d.timestamp())
        work["dueDate"] = {"year": u.year, "month": u.month, "day": u.day}
        work["dueTime"] = {"hours": u.hour, "minutes": u.minute}
    cw = classroom.courses().courseWork().create(courseId=target["id"], body=work).execute()
    return {"ok": True, "course": target["name"], "link": cw.get("alternateLink", "")}


def distribute(worksheet, class_name, due_iso="", max_points=None):
    """End-to-end: create the quiz + post to Classroom. Raises if not available()."""
    if not available():
        return {"ok": False, "error": "Path B not set up: missing client_secret.json or google libraries."}
    forms, classroom = _services()
    form_id, form_url = create_quiz(forms, worksheet)
    res = post_to_classroom(classroom, class_name,
                            worksheet.get("tajuk", "English Quiz"),
                            worksheet.get("arahan_murid", "Complete this quiz."),
                            form_url, due_iso, max_points)
    res["form_url"] = form_url
    return res
