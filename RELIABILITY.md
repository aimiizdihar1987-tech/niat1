# Niat — Reliability, Orchestration & Deployment Evidence

This document exists so that the three questions an assessor asks can be
answered by *pointing at something running*, not by describing intentions:

1. Is it really deployed and executing in the cloud? → [§1](#1-live-deployment)
2. Is the multi-agent workflow real, or is it one prompt in a trench coat? → [§2](#2-multi-agent-orchestration)
3. What happens when something fails? → [§3](#3-error-handling--robustness)

---

## 1. Live deployment

| Surface | URL | Auth | What it proves |
|---|---|---|---|
| Application | <https://niat-1094321285675.asia-southeast1.run.app> | login | The product itself |
| **Public status page** | <https://niat-1094321285675.asia-southeast1.run.app/status.html> | **none** | Live uptime, build sha, dependency health |
| Liveness probe | `https://niat-1094321285675.asia-southeast1.run.app/api/health` | none | The process answers HTTP |
| Readiness probe | `https://niat-1094321285675.asia-southeast1.run.app/api/ready` | none | Config + database reachable (503 when not) |
| Deep status | `https://niat-1094321285675.asia-southeast1.run.app/api/status` | none | Deployment identity, dependency latency, breaker state, metrics |
| Call metrics | `https://niat-1094321285675.asia-southeast1.run.app/api/metrics` | none | Per-dependency call counts, success rate, recent errors |
| Agent graph | `https://niat-1094321285675.asia-southeast1.run.app/api/workflow` | none | The machine-readable workflow definition |

`/api/status` reports where the instance is actually running — Cloud Run
(`K_SERVICE`/`K_REVISION`), Render (`RENDER_*`), a plain container, or a
self-hosted host — together with the build sha baked in at deploy time, so a
live instance can be matched to an exact commit:

```json
{
  "service": "niat",
  "status": "healthy",
  "deployment": {
    "platform": "google-cloud-run",
    "instance": "niat-00042-abc",
    "region": "asia-southeast1",
    "build_sha": "19636b8",
    "uptime_seconds": 51840
  },
  "dependencies": [
    {"name": "supabase", "status": "up", "latency_ms": 84},
    {"name": "gemini",   "status": "configured", "breaker": "closed"}
  ]
}
```

### Deployment pipeline

* `Dockerfile` + `.dockerignore` — the container image.
* `cloudbuild.yaml` — build → Artifact Registry → Cloud Run deploy, triggered
  on every push to `main`. Secrets come from Secret Manager, never the image.
* `.github/workflows/ci.yml` — on every push and PR: the unit suite on Python
  3.11 and 3.12, a full `compileall`, then a **container boot probe** that
  starts the built image and curls `/api/health`, `/api/status` and
  `/api/workflow`. A build that compiles but cannot serve traffic fails CI.
* `.github/workflows/uptime.yml` — every 30 minutes GitHub (an *external*
  observer, not the server itself) probes the live deployment and fails loudly
  if it is down. Set the repo variable `NIAT_PUBLIC_URL` to enable it.
* `container_check.py` — refuses to boot a container with an unsafe
  configuration (local storage, short auth secret) rather than starting up
  quietly insecure.

---

## 2. Multi-agent orchestration

Six agents, declared in `orchestrator.py` and served at `/api/workflow`:

| # | Agent | Depends on | Teacher checkpoint | Autonomous |
|---|---|---|---|---|
| 1 | Lesson Plan (RPH) | — | approves RPH | no |
| 2 | Materials & Slides | 1 | approves materials | no |
| 3 | Worksheet | 1 | approves worksheet | no |
| 4 | **Differentiation** | 3 | — | **yes** |
| 5 | Reflection & Report | 1 | — | no (optional) |
| 6 | **Submission Reminder** | — | — | **yes** (scheduled) |

What makes this orchestration rather than a sequence of buttons:

* **A declared graph.** Dependencies, human checkpoints and the external
  services each agent touches are data, not comments — see `/api/workflow`.
* **A state machine per run.** `pending → running → awaiting_approval → done`
  (or `failed`/`skipped`). `Run.execute()` refuses to run an agent whose
  dependency has not finished, and refuses to cross a checkpoint the teacher
  has not approved. Both refusals are tested.
* **Agentic, not just generative.** Agent 4 reads cumulative pupil performance,
  *decides* each pupil's level for the next lesson, and posts the matching
  worksheet to Google Classroom per pupil. Agent 6 runs on a schedule with no
  human present, watches due dates, and escalates its tone.
* **A durable trace.** Every transition, retry and handoff is appended to the
  run record under `data/runs/<run_id>.json` with a correlation id, so a run
  can be replayed after the fact. `GET /api/orchestrator/run?id=...`.
* **Recovery.** A failed step does not kill the run: `Run.retry_step()` resets
  just that step and re-executes it; optional steps can be skipped.

```
POST /api/orchestrator/start     {kelas, form, tajuk}    -> run_id + step list
GET  /api/orchestrator/runs                              -> this teacher's runs
GET  /api/orchestrator/run?id=   run_id                  -> full record + trace
POST /api/orchestrator/approve   {run_id, agent_id}      -> clears a checkpoint
POST /api/orchestrator/skip      {run_id, agent_id}      -> skips an optional step
```

---

## 3. Error handling & robustness

All of it lives in `resilience.py` (standard library only, so it behaves
identically on the teacher's laptop, in the container and on Cloud Run).

### Error taxonomy

Every deliberate failure is a `NiatError` carrying a stable `code`, an
`http_status`, a `retryable` flag and a Malay `user_message`. `classify()` maps
any stray exception onto that taxonomy, so an unexpected `KeyError` still comes
back as structured JSON instead of a traceback. Codes: `configuration_error`,
`upstream_error`, `upstream_timeout`, `rate_limited`, `circuit_open`,
`validation_error`, `agent_error`.

### One error boundary for every request

`_dispatch()` wraps both `do_GET` and `do_POST`. Any exception is classified,
logged, and returned in the shape the front end already understands, with a
correlation id in the `X-Correlation-Id` header — a teacher's screenshot is
enough to find the matching log line. Client disconnects are handled
separately so they never appear as server errors.

### Retry with exponential backoff and jitter

`resilience.retry()` replaces the hand-rolled retry loops. Delays grow
1s → 2s → 4s with up to 25% jitter, because without jitter thirty teachers
hitting a rate-limited Gemini all retry in the same instant. **Non-retryable
errors are raised immediately** — retrying a missing API key only makes the
teacher wait longer for the same failure.

### Circuit breakers

`CircuitBreaker` (closed → open → half-open → closed). After 5 consecutive
failures the dependency is marked open and calls fail in milliseconds with a
clear message instead of each teacher waiting out a 120-second timeout; after
60 seconds one trial call tests recovery. Live state is on `/status.html`.

### Structured logging and metrics

One JSON object per line on stdout (what Cloud Logging expects), each carrying
the correlation id of the request or agent run. Per-dependency counters — call
count, success rate, average and max latency, last error — are exposed at
`/api/metrics`, and the last 300 log records stay in memory so recent failures
are visible without shell access to the instance.

### Graceful degradation

| Failure | Behaviour instead of crashing |
|---|---|
| Gemini unreachable | Retry with backoff → circuit opens → local Ollama fallback where configured (`engine_mode`) |
| Gemini returns non-JSON | `call_llm_json` re-asks once before failing |
| Supabase unreachable | `/api/ready` returns 503; local file storage keeps the desktop build usable |
| Supabase table missing | Agent 6 continues without escalation history rather than crashing |
| Classroom API not yet approved | Apps Script hub path reads Classroom as the teacher |
| Run trace cannot be written to disk | Logged as a warning; the lesson continues |

### Tests

`python -m unittest discover -s tests -v` — 47 tests, including 18 for
`resilience.py` (backoff growth, permanent-error short-circuiting, breaker
state transitions, correlation-id scoping) and 16 for `orchestrator.py`
(dependency gating, checkpoint gating, failure recording, step retry,
persistence across restart, trace completeness).
