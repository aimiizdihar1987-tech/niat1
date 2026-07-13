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
- **Google Drive API**
- **Google Docs API**
- **Gmail API** (to send the emails)

## Step 3 — OAuth consent screen
**APIs & Services → OAuth consent screen**
- User type: **Internal** (if owned by `moe-dl` and the admin allows) — otherwise **External** + add the teacher emails as **Test users**.
- App name: `Niat`, support email: a teacher email.
- **Scopes** to add:
  - `https://www.googleapis.com/auth/forms.body`
  - `https://www.googleapis.com/auth/documents`
  - `https://www.googleapis.com/auth/drive.file`
  - `https://www.googleapis.com/auth/gmail.send`

## Step 4 — Create credentials
**APIs & Services → Credentials → Create credentials → OAuth client ID**
- Application type: **Desktop app** → Create.
- **Download JSON** → save it in this project folder as **`client_secret.json`**.
- ⚠️ Keep `client_secret.json` private (do not share the folder with it inside).

## Step 5 — Tell me
Once `client_secret.json` is in the folder **and** the scopes are approved, tell me. I will then:
- Add a small Python helper using Google's libraries (one-time `pip install google-api-python-client google-auth google-auth-oauthlib`).
- On first run you sign in **once** in the browser; a `token.json` is saved for reuse.
- Replace the "Distribute (Prototype)" paste-step with a real **one-click Distribute** button that calls the APIs directly.

> Note: this is the one place Niat will need `pip install` — it's unavoidable for Google's official APIs.

---

## Ready-to-send email to your IT admin

> **Subject:** Request: approve an OAuth app ("Niat") for moe-dl accounts
>
> Salam / Hi,
>
> I am piloting a teaching tool ("Niat") that automatically creates Google Form quizzes,
> saves lesson plans to Google Drive, and emails them, using the Google Forms, Docs, Drive and
> Gmail APIs. To use it with our `moe-dl.edu.my` accounts I need:
>
> 1. Permission to **create a Google Cloud project**, and
> 2. Approval for an **OAuth app** with these scopes for our domain users:
>    `forms.body`, `documents`, `drive.file`, `gmail.send`.
>
> It will be used by these accounts for now: `g-76208854@moe-dl.edu.my`,
> `jpn-perlis-cm16@moe-dl.edu.my`. Could you advise whether this can be approved, or whether
> there is a school/JPN process for it?
>
> Thank you.

---

*Status: guide only — no Path B code is built yet. Build begins once `client_secret.json` exists and scopes are approved.*
