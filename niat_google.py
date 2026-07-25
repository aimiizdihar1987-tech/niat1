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
    # Differentiated distribution (Agent 5): create coursework for pupils in
    # courses the teacher owns, and read the roster to map email -> Classroom userId.
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
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


def _find_course(classroom, class_name):
    """Return the ACTIVE course whose name matches class_name, or None."""
    courses = classroom.courses().list(courseStates=["ACTIVE"]).execute().get("courses", [])
    want = (class_name or "").lower()
    for c in courses:
        nm = (c.get("name") or "").lower()
        if want and (nm == want or want in nm):
            return c
    return None


def _find_coursework(classroom, course_id, title):
    """Find a coursework item in a course by (partial, case-insensitive) title.
    If title is blank, return the most recently created coursework."""
    items, page = [], None
    while True:
        resp = classroom.courses().courseWork().list(
            courseId=course_id, pageSize=100, pageToken=page).execute()
        items.extend(resp.get("courseWork", []))
        page = resp.get("nextPageToken")
        if not page:
            break
    if not items:
        return None
    want = (title or "").strip().lower()
    if not want:
        # newest first by creationTime
        items.sort(key=lambda w: w.get("creationTime", ""), reverse=True)
        return items[0]
    for w in items:
        nm = (w.get("title") or "").lower()
        if nm == want or want in nm:
            return w
    return None


def list_overdue_coursework(within_days=14):
    """Every assignment across the teacher's ACTIVE courses whose due date has
    PASSED but is no older than `within_days` — the work list for the reminder
    cron. Returns [{class_name, coursework_title, due_iso}] (newest due first).
    """
    if not available():
        return []
    from datetime import datetime, timedelta
    forms, classroom = _services()
    now = datetime.utcnow()
    floor = now - timedelta(days=within_days)
    out = []
    courses = classroom.courses().list(courseStates=["ACTIVE"]).execute().get("courses", [])
    for course in courses:
        page = None
        while True:
            resp = classroom.courses().courseWork().list(
                courseId=course["id"], pageSize=100, pageToken=page).execute()
            for w in resp.get("courseWork", []):
                dd, dt = w.get("dueDate"), w.get("dueTime")
                if not dd:
                    continue
                try:
                    due = datetime(dd.get("year"), dd.get("month"), dd.get("day"),
                                   (dt or {}).get("hours", 23), (dt or {}).get("minutes", 59))
                except (TypeError, ValueError):
                    continue
                if floor <= due < now:  # overdue, but within the window
                    out.append({"class_name": course.get("name", ""),
                                "coursework_title": w.get("title", ""),
                                "due_iso": due.strftime("%Y-%m-%dT%H:%M")})
            page = resp.get("nextPageToken")
            if not page:
                break
    out.sort(key=lambda x: x["due_iso"], reverse=True)
    return out


def list_submission_states(class_name, coursework_title=""):
    """Who has / hasn't turned in a given assignment.

    Returns {"ok", "course", "coursework", "due_iso", "students":[{email, name,
    userId, state, submitted, late}]}. `submitted` is True only when the pupil
    turned the work in (TURNED_IN / RETURNED). Reading submissions needs the
    classroom.coursework.students scope; emails need rosters.readonly.
    """
    if not available():
        return {"ok": False, "error": "Path B not set up: missing client_secret.json or google libraries."}
    forms, classroom = _services()
    course = _find_course(classroom, class_name)
    if not course:
        return {"ok": False, "error": 'No active Classroom matching "%s"' % class_name}
    work = _find_coursework(classroom, course["id"], coursework_title)
    if not work:
        return {"ok": False, "error": 'No assignment matching "%s" in %s'
                % (coursework_title or "(latest)", course["name"])}

    # Due date (Classroom stores UTC date + time) -> ISO string, if any.
    due_iso = ""
    dd, dt = work.get("dueDate"), work.get("dueTime")
    if dd:
        due_iso = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}".format(
            dd.get("year", 0), dd.get("month", 0), dd.get("day", 0),
            (dt or {}).get("hours", 23), (dt or {}).get("minutes", 59))

    roster = {r["userId"]: r for r in list_course_students(classroom, course["id"])}
    subs, page = [], None
    while True:
        resp = classroom.courses().courseWork().studentSubmissions().list(
            courseId=course["id"], courseWorkId=work["id"],
            pageSize=100, pageToken=page).execute()
        subs.extend(resp.get("studentSubmissions", []))
        page = resp.get("nextPageToken")
        if not page:
            break

    students = []
    for s in subs:
        uid = s.get("userId", "")
        state = s.get("state", "NEW")
        submitted = state in ("TURNED_IN", "RETURNED")
        r = roster.get(uid, {})
        students.append({
            "userId": uid, "email": r.get("email", ""), "name": r.get("name", ""),
            "state": state, "submitted": submitted, "late": bool(s.get("late", False)),
        })
    return {"ok": True, "course": course["name"], "coursework": work.get("title", ""),
            "due_iso": due_iso, "students": students}


def list_course_students(classroom, course_id):
    """Return the roster as [{userId, email, name}] so we can target individuals.
    Reading emails needs the classroom.rosters.readonly scope."""
    out = []
    page = None
    while True:
        resp = classroom.courses().students().list(
            courseId=course_id, pageSize=100, pageToken=page).execute()
        for s in resp.get("students", []):
            prof = s.get("profile", {}) or {}
            name = (prof.get("name", {}) or {}).get("fullName", "")
            out.append({
                "userId": s.get("userId", ""),
                "email": (prof.get("emailAddress") or "").strip().lower(),
                "name": name,
            })
        page = resp.get("nextPageToken")
        if not page:
            break
    return out


def _due(work, due_iso):
    if not due_iso:
        return
    from datetime import datetime
    d = datetime.fromisoformat(due_iso)  # local; convert to UTC for the API
    u = datetime.utcfromtimestamp(d.timestamp())
    work["dueDate"] = {"year": u.year, "month": u.month, "day": u.day}
    work["dueTime"] = {"hours": u.hour, "minutes": u.minute}


def post_to_classroom(classroom, class_name, title, description, form_url, due_iso,
                      max_points, student_ids=None, course=None):
    """Create coursework with the form link + due date.

    student_ids: if given (list of Classroom userIds), the assignment is posted
    ONLY to those pupils (assigneeMode INDIVIDUAL_STUDENTS) — this is how one
    class gets several worksheet levels at once. If None, the whole class gets it.
    """
    target = course or _find_course(classroom, class_name)
    if not target:
        return {"ok": False, "error": 'No active Classroom matching "%s"' % class_name}
    work = {
        "title": title, "description": description,
        "materials": [{"link": {"url": form_url, "title": title}}],
        "workType": "ASSIGNMENT", "state": "PUBLISHED",
        "maxPoints": max_points or 100,
    }
    if student_ids:
        work["assigneeMode"] = "INDIVIDUAL_STUDENTS"
        work["individualStudentsOptions"] = {"studentIds": student_ids}
    _due(work, due_iso)
    cw = classroom.courses().courseWork().create(courseId=target["id"], body=work).execute()
    return {"ok": True, "course": target["name"], "link": cw.get("alternateLink", ""),
            "assigned": len(student_ids) if student_ids else "all"}


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


def distribute_differentiated(class_name, bands, due_iso="", max_points=None):
    """Post several worksheet LEVELS to ONE class, each to its own pupils.

    bands: list of {band, cefr, worksheet, emails:[...]} — one entry per level
    that has at least one pupil. Emails are matched (case-insensitive) against
    the Classroom roster to find each pupil's userId. Raises if not available().

    Returns {"ok", "course", "bands":[{band, cefr, count, link, form_url,
    unmatched:[emails]}], "unmatched":[emails not on the roster]}.
    """
    if not available():
        return {"ok": False, "error": "Path B not set up: missing client_secret.json or google libraries."}
    forms, classroom = _services()
    course = _find_course(classroom, class_name)
    if not course:
        return {"ok": False, "error": 'No active Classroom matching "%s"' % class_name}

    roster = list_course_students(classroom, course["id"])
    email_to_id = {r["email"]: r["userId"] for r in roster if r["email"]}

    posted, all_unmatched = [], []
    for b in bands:
        emails = [e.strip().lower() for e in (b.get("emails") or []) if e]
        ids = [email_to_id[e] for e in emails if e in email_to_id]
        unmatched = [e for e in emails if e not in email_to_id]
        all_unmatched.extend(unmatched)
        if not ids:
            posted.append({"band": b.get("band"), "cefr": b.get("cefr"),
                           "count": 0, "skipped": "no matching pupils on roster",
                           "unmatched": unmatched})
            continue
        ws = b.get("worksheet", {}) or {}
        form_id, form_url = create_quiz(forms, ws)
        title = ws.get("tajuk") or ("English Quiz — " + str(b.get("cefr", "")))
        res = post_to_classroom(
            classroom, class_name, title,
            ws.get("arahan_murid", "Complete this quiz."),
            form_url, due_iso, max_points, student_ids=ids, course=course)
        posted.append({"band": b.get("band"), "cefr": b.get("cefr"),
                       "count": len(ids), "link": res.get("link", ""),
                       "form_url": form_url, "unmatched": unmatched})
    return {"ok": True, "course": course["name"], "bands": posted,
            "unmatched": all_unmatched}
