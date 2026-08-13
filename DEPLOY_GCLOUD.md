# Niat: container and Cloud Run deployment

The repository is prepared for a production container. The image contains only
runtime code and public curriculum assets; local credentials, student files,
databases, generated outputs, prototypes and tests are excluded.

## 1. Verify locally

```powershell
python container_check.py
python -m unittest discover -s tests -v
docker build -t niat:local .
Copy-Item .env.example .env
# Fill .env with your own secret values, then:
docker run --rm --env-file .env -p 8080:8080 niat:local
```

Check `http://localhost:8080/api/health` for process liveness and
`http://localhost:8080/api/ready` for Supabase readiness. Delete `.env` after
testing; it is ignored by Git, Docker and gcloud.

## 2. Prepare durable Supabase storage

1. For a new project, run `supabase/schema.sql` in Supabase SQL Editor.
2. For an existing project, also run
   `supabase/migration_container_readiness.sql`.
3. Verify and migrate from this PC:

```powershell
python migrate_to_supabase.py --check
python migrate_to_supabase.py --users
python migrate_to_supabase.py --data --owner YOUR_USERNAME
```

The container deliberately refuses to start with local storage. Question bank,
lessons, teacher-owned timetables, classroom mappings, student records, schools,
announcements, Agent 5 performance and Agent 6 reminder history are therefore
not lost when an instance restarts.

## 3. Prepare Google integrations

Agent 6 can read submissions and send mail through the Apps Script hub. Deploy
the hub using the operational account `jpn-perlis-cm16@moe-dl.edu.my`, then keep
its URL and key as secrets named `apps-script-hub-url` and
`apps-script-hub-key`.

Agent 5 automatic Google Forms/Classroom posting needs one-time OAuth consent.
On this PC, use the same operational account:

```powershell
python -m pip install -r requirements.txt
python niat_google.py --authorize
gcloud secrets create google-oauth-token --data-file=token.json
```

Never add `client_secret.json` or `token.json` to the image. Re-authorize after
changing Google scopes. The domain administrator may still need to approve the
requested Classroom/Forms scopes.

## 4. Create Cloud secrets

Use Secret Manager to create these secret names and pin a concrete version when
deploying:

| Secret name | Runtime variable |
|---|---|
| `gemini-api-key` | `GOOGLE_API_KEY` |
| `supabase-url` | `SUPABASE_URL` |
| `supabase-anon-key` | `SUPABASE_ANON_KEY` |
| `supabase-service-key` | `SUPABASE_SERVICE_ROLE_KEY` |
| `niat-auth-secret` | `NIAT_AUTH_SECRET` (at least 32 random characters) |
| `apps-script-hub-url` | `APPSCRIPT_HUB_URL` |
| `apps-script-hub-key` | `APPSCRIPT_HUB_KEY` |
| `google-oauth-token` | `GOOGLE_OAUTH_TOKEN_JSON` |
| `niat-cron-secret` | `NIAT_CRON_SECRET` |

Google recommends Secret Manager for Cloud Run secrets and recommends pinning
environment-variable secrets to a specific version. See the official
[Cloud Run secrets guide](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

## 5. Deploy from source

Install and initialize gcloud, select your project, then run from this folder:

```powershell
gcloud config set run/region asia-southeast1
gcloud run deploy niat --source . --allow-unauthenticated `
  --set-env-vars "NIAT_REQUIRE_HUB=1,NIAT_REQUIRE_GOOGLE_OAUTH=1,TEACHER_EMAIL=jpn-perlis-cm16@moe-dl.edu.my" `
  --set-secrets "GOOGLE_API_KEY=gemini-api-key:1,SUPABASE_URL=supabase-url:1,SUPABASE_ANON_KEY=supabase-anon-key:1,SUPABASE_SERVICE_ROLE_KEY=supabase-service-key:1,NIAT_AUTH_SECRET=niat-auth-secret:1,APPSCRIPT_HUB_URL=apps-script-hub-url:1,APPSCRIPT_HUB_KEY=apps-script-hub-key:1,GOOGLE_OAUTH_TOKEN_JSON=google-oauth-token:1,NIAT_CRON_SECRET=niat-cron-secret:1"
```

Cloud Run uses the repository Dockerfile when deploying with `--source .`; see
the official [source deployment guide](https://docs.cloud.google.com/run/docs/deploying-source-code).
Public access is needed for the browser UI, while Niat itself still requires a
valid signed-in application session.

After deployment, open `SERVICE_URL/api/ready`. Do not proceed to production if
it returns HTTP 503.

## 6. Schedule Agent 6

Create a five-minute HTTP job. Replace the placeholders with the deployed URL
and load the same cron secret value stored in Secret Manager into a temporary
PowerShell environment variable (so it does not appear literally in history):

```powershell
gcloud services enable cloudscheduler.googleapis.com
$env:NIAT_CRON_SECRET = Read-Host "Cron secret"
gcloud scheduler jobs create http niat-agent6 `
  --location=asia-southeast1 `
  --schedule="*/5 * * * *" `
  --time-zone="Asia/Kuala_Lumpur" `
  --uri="SERVICE_URL/api/internal/reminders" `
  --http-method=POST `
  --headers="X-Niat-Cron-Secret=$env:NIAT_CRON_SECRET"
Remove-Item Env:\NIAT_CRON_SECRET
```

The endpoint rejects calls without the shared secret, and reminder history is
stored in Supabase to make retries safe. The flags above follow the official
[Cloud Scheduler HTTP job reference](https://docs.cloud.google.com/sdk/gcloud/reference/scheduler/jobs/create/http).

## Go-live gate

- `/api/health` returns HTTP 200.
- `/api/ready` returns HTTP 200 and `database_reachable: true`.
- A Supabase teacher account can sign in.
- Agent 5 completes one controlled Classroom post.
- Agent 6 completes one controlled overdue-submission check.
- No local data or credential file appears in the Docker build context.
