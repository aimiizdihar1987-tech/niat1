# Path B — Full Google Automation (Setup Guide)

**Goal:** true one-click distribution from inside Niat — it creates the Google Form quiz,
saves the lesson plan to Drive, and emails both **automatically** (no copy-paste of a script).

---

## ⚠️ Read this first — the gate

`moe-dl.edu.my` is a **Google Workspace for Education** domain. By default such domains can
**block third-party apps** from accessing accounts. So before writing any code, settle this:

> Can your **JPN Perlis / MOE IT admin** approve an OAuth app (the scopes below) for use by
> `moe-dl.edu.my` accounts — and can you create a Google Cloud project?

- ✅ If **yes** → continue with Steps 1–5 below.
- ❌ If **no** → Path B is not possible; **Path A (the current "Distribute (Prototype)" script) stays the way**, and it already works.

**This is the single biggest risk. Confirm it before investing time.** A ready-to-send email to your admin is at the bottom of this file.

---

## Step 1 — Create a Google Cloud project
1. Go to <https://console.cloud.google.com> and sign in (the account that will *own* the app — ideally a teacher `moe-dl` account, or a personal Google account if the domain blocks project creation).
2. Top bar → **New Project** → name it `Niat` → Create.

## Step 2 — Enable the APIs
In the project: **APIs & Services → Library**, enable:
- **Google Forms API**
- **Google Classroom API**
- **Google Drive API**

## Step 3 — OAuth consent screen
**APIs & Services → OAuth consent screen**
- User type: **Internal** (if owned by `moe-dl` and the admin allows) — otherwise **External** + add the teacher emails as **Test users**.
- App name: `Niat`, support email: a teacher email.
- **Scopes** to add — these must match `SCOPES` in `niat_google.py` exactly:
  - `https://www.googleapis.com/auth/forms.body`
  - `https://www.googleapis.com/auth/drive.file`
  - `https://www.googleapis.com/auth/classroom.courses.readonly`
  - `https://www.googleapis.com/auth/classroom.coursework.me`
  - `https://www.googleapis.com/auth/classroom.coursework.students` — Agent 5: post a different worksheet to different pupils
  - `https://www.googleapis.com/auth/classroom.rosters.readonly` — Agent 5: map pupil email → Classroom user id

> The last two exist only for Agent 5 (differentiated distribution). Without them
> the ordinary one-worksheet-for-everyone distribution still works, but Agent 5
> cannot post per-pupil and will stay in dry-run preview.

## Step 4 — Create credentials
**APIs & Services → Credentials → Create credentials → OAuth client ID**
- Application type: **Desktop app** → Create.
- **Download JSON** → save it in this project folder as **`client_secret.json`**.
- ⚠️ Keep `client_secret.json` private (do not share the folder with it inside).

## Step 5 — Install the libraries and sign in once
The code (`niat_google.py`) is already written and wired up. Two things remain:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib
```

Then, with `client_secret.json` in this folder, use Distribute (or Agent 5) once.
A browser window opens for consent, and a `token.json` is saved for reuse.

> Note: this is the one place Niat needs `pip install` — it's unavoidable for
> Google's official APIs. The server itself stays stdlib-only; `niat_google` is
> imported lazily, so a missing library never breaks the rest of the app.

**If you re-run after adding the two Agent 5 scopes, delete `token.json` first.**
An existing token was granted the old, narrower scope set and will not gain the
new permissions on refresh — Agent 5 would keep failing until you re-consent.

---

## Ready-to-send email to your IT admin

> **Subject:** Request: approve an OAuth app ("Niat") for moe-dl accounts
>
> Salam / Hi,
>
> I am piloting a teaching tool ("Niat") that automatically creates Google Form quizzes and
> posts them as assignments in Google Classroom, using the Google Forms, Classroom and Drive
> APIs. To use it with our `moe-dl.edu.my` accounts I need:
>
> 1. Permission to **create a Google Cloud project**, and
> 2. Approval for an **OAuth app** with these scopes for our domain users:
>    - `forms.body` — create the quiz
>    - `drive.file` — save only the files the app itself creates
>    - `classroom.courses.readonly` — find the teacher's own class
>    - `classroom.coursework.me` — post the assignment
>    - `classroom.coursework.students` — assign different work to different pupils
>    - `classroom.rosters.readonly` — match a pupil's email to their Classroom account
>
> The last two support differentiated learning: the tool assigns an easier or harder
> version of the same worksheet to each pupil based on their past quiz results. It reads
> class rosters and creates coursework only in classes the signed-in teacher already owns;
> it does not read pupil email or Drive content.
>
> It will be used by these accounts for now: `g-76208854@moe-dl.edu.my`,
> `jpn-perlis-cm16@moe-dl.edu.my`. Could you advise whether this can be approved, or whether
> there is a school/JPN process for it?
>
> Thank you.

---

*Status: the code is built (`niat_google.py`, wired to `/api/distribute-direct` and to Agent 5
via `/api/differentiate`) but **untested against the real Google APIs**. It stays inert — Agent 5
runs in dry-run preview — until `client_secret.json` exists, the libraries are installed, and the
scopes above are approved.*
