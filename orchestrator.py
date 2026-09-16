"""Explicit multi-agent orchestration for Niat's six agents.

Before this module the pipeline existed only implicitly: the browser called
`/api/generate-rph`, then `/api/generate-materials`, and so on, and the order
lived in the UI. That works, but nothing could answer "which agent ran, in
what order, with what inputs, and where did it fail?" — and a crashed step
left no record at all.

This module makes the workflow a first-class object:

* a **registry** (`AGENTS`) declaring each agent, its dependencies, the
  teacher checkpoint it waits behind, and whether it acts autonomously;
* a **run** — a persisted state machine (`pending -> running -> awaiting_approval
  -> done | failed`) with one record per step;
* a **trace** — every state transition, retry and handoff, timestamped and
  tied to a correlation id, so a run can be replayed after the fact.

Storage is a JSON file per run under `data/runs/`, which keeps the module
dependency-free and works the same on the desktop and in the container.
Supabase mirroring is optional and best-effort: a logging failure must never
fail a lesson.
"""

import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import resilience

ROOT = os.path.dirname(os.path.abspath(__file__))
# On Cloud Run only /tmp is reliably writable, and NIAT_OUTPUT_DIR already
# points there; on the desktop the traces live beside the rest of the data.
RUNS_DIR = os.path.join(
    os.environ.get("NIAT_OUTPUT_DIR") or os.path.join(ROOT, "data"), "runs"
)
MAX_RUNS_KEPT = 200

# --------------------------------------------------------------------------
# Agent registry
# --------------------------------------------------------------------------


class AgentSpec:
    def __init__(
        self,
        agent_id,
        number,
        name,
        purpose,
        endpoint,
        prompt_file,
        depends_on=(),
        checkpoint=None,
        autonomous=False,
        optional=False,
        upstreams=(),
    ):
        self.agent_id = agent_id
        self.number = number
        self.name = name
        self.purpose = purpose
        self.endpoint = endpoint
        self.prompt_file = prompt_file
        self.depends_on = list(depends_on)
        self.checkpoint = checkpoint      # what the teacher must approve after this step
        self.autonomous = autonomous      # decides/acts without a teacher in the loop
        self.optional = optional
        self.upstreams = list(upstreams)  # external services this agent touches

    def to_dict(self):
        return {
            "id": self.agent_id,
            "number": self.number,
            "name": self.name,
            "purpose": self.purpose,
            "endpoint": self.endpoint,
            "prompt_file": self.prompt_file,
            "depends_on": self.depends_on,
            "checkpoint": self.checkpoint,
            "autonomous": self.autonomous,
            "optional": self.optional,
            "upstreams": self.upstreams,
        }


# Order here is the canonical workflow order (see README "Agent lineup").
AGENTS = [
    AgentSpec(
        "agent1_lesson_plan", 1, "Lesson Plan (RPH)",
        "Turns the teacher's setup form + DSKP standards into a full RPH.",
        "/api/generate-rph", "prompts/agent1_rph.md",
        depends_on=[], checkpoint="teacher_approves_rph",
        upstreams=["gemini", "dskp"],
    ),
    AgentSpec(
        "agent2_materials", 2, "Materials & Slides",
        "Builds teaching materials/slides from the approved lesson plan.",
        "/api/generate-materials", "prompts/agent2_materials.md",
        depends_on=["agent1_lesson_plan"], checkpoint="teacher_approves_materials",
        upstreams=["gemini", "gamma"],
    ),
    AgentSpec(
        "agent3_worksheet", 3, "Worksheet",
        "Writes the pupil worksheet, constrained to Cambridge B1 vocabulary.",
        "/api/generate-worksheet", "prompts/agent3_worksheet.md",
        depends_on=["agent1_lesson_plan"], checkpoint="teacher_approves_worksheet",
        upstreams=["gemini", "wordlist"],
    ),
    AgentSpec(
        "agent4_differentiation", 4, "Differentiation",
        "Reads cumulative pupil performance, decides each pupil's level for the "
        "next lesson, and posts the matching worksheet to Google Classroom.",
        "/api/differentiate", "prompts/agent4_differentiation.md",
        depends_on=["agent3_worksheet"], autonomous=True,
        upstreams=["gemini", "supabase", "classroom", "apps_script_hub"],
    ),
    AgentSpec(
        "agent5_reflection", 5, "Reflection & Report",
        "Writes up the lesson that just happened and emails the report.",
        "/api/reflect", "prompts/agent5_reflection.md",
        depends_on=["agent1_lesson_plan"], optional=True,
        upstreams=["gemini", "gmail"],
    ),
    AgentSpec(
        "agent6_reminder", 6, "Submission Reminder",
        "Watches due dates, finds pupils who have not submitted, and escalates "
        "the reminder tone. Runs on a schedule with no teacher present.",
        "/api/remind", "prompts/agent6_reminder.md",
        depends_on=[], autonomous=True, optional=True,
        upstreams=["classroom", "apps_script_hub", "supabase", "gemini"],
    ),
]

BY_ID = {a.agent_id: a for a in AGENTS}


def registry():
    """Machine-readable description of the whole workflow."""
    return {
        "workflow": "niat.lesson_cycle",
        "version": 2,
        "agents": [a.to_dict() for a in AGENTS],
        "edges": [
            {"from": dep, "to": a.agent_id}
            for a in AGENTS
            for dep in a.depends_on
        ],
        "human_checkpoints": [a.checkpoint for a in AGENTS if a.checkpoint],
        "autonomous_agents": [a.agent_id for a in AGENTS if a.autonomous],
    }


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------

_lock = threading.Lock()

PENDING = "pending"
RUNNING = "running"
AWAITING = "awaiting_approval"
DONE = "done"
FAILED = "failed"
SKIPPED = "skipped"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_dir():
    os.makedirs(RUNS_DIR, exist_ok=True)


def _path(run_id):
    return os.path.join(RUNS_DIR, "{}.json".format(run_id))


class Run:
    """One pass through the lesson cycle for one class."""

    def __init__(self, data):
        self.data = data

    # -- lifecycle ------------------------------------------------------
    @classmethod
    def start(cls, *, context=None, owner=None, agents=None):
        run_id = "run_{}_{}".format(time.strftime("%Y%m%d"), uuid.uuid4().hex[:8])
        chosen = agents or [a.agent_id for a in AGENTS]
        data = {
            "run_id": run_id,
            "correlation_id": run_id,
            "owner": owner,
            "context": context or {},
            "status": RUNNING,
            "started_at": _now(),
            "finished_at": None,
            "steps": [
                {
                    "agent_id": aid,
                    "number": BY_ID[aid].number,
                    "name": BY_ID[aid].name,
                    "status": PENDING,
                    "attempts": 0,
                    "started_at": None,
                    "finished_at": None,
                    "duration_ms": None,
                    "error": None,
                    "output_summary": None,
                }
                for aid in chosen
                if aid in BY_ID
            ],
            "trace": [],
        }
        run = cls(data)
        run._trace("run.started", context_keys=sorted((context or {}).keys()))
        run.save()
        resilience.info("orchestrator.run_started", run_id=run_id, owner=owner)
        return run

    @classmethod
    def start_or_resume(cls, key, *, context=None, owner=None, agents=None):
        """Like `start`, but addressed by a stable key instead of a random id,
        so separate HTTP calls that belong to the same lesson (RPH, then
        materials, then worksheet — three independent requests with no
        run_id passed between them) land in the SAME run instead of each
        becoming its own untracked, one-step run.

        `key` should be something that is genuinely stable across those
        calls and genuinely different across lessons — e.g. teacher +
        class + date + topic. The run_id is a hash of it, so calling this
        twice with the same key resumes the same run; a different key (a
        different lesson) always gets its own.
        """
        run_id = "run_ctx_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        existing = cls.load(run_id)
        if existing is not None:
            return existing
        chosen = agents or [a.agent_id for a in AGENTS]
        data = {
            "run_id": run_id,
            "correlation_id": run_id,
            "owner": owner,
            "context": context or {},
            "status": RUNNING,
            "started_at": _now(),
            "finished_at": None,
            "steps": [
                {
                    "agent_id": aid,
                    "number": BY_ID[aid].number,
                    "name": BY_ID[aid].name,
                    "status": PENDING,
                    "attempts": 0,
                    "started_at": None,
                    "finished_at": None,
                    "duration_ms": None,
                    "error": None,
                    "output_summary": None,
                }
                for aid in chosen
                if aid in BY_ID
            ],
            "trace": [],
        }
        run = cls(data)
        run._trace("run.started", context_keys=sorted((context or {}).keys()))
        run.save()
        resilience.info("orchestrator.run_started", run_id=run_id, owner=owner)
        return run

    @classmethod
    def load(cls, run_id):
        try:
            with open(_path(run_id), encoding="utf-8") as f:
                return cls(json.load(f))
        except (OSError, ValueError):
            return None

    def save(self):
        _ensure_dir()
        tmp = _path(self.data["run_id"]) + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _path(self.data["run_id"]))
        except OSError as e:
            # Persisting a trace must never break the lesson the teacher is running.
            resilience.warn("orchestrator.persist_failed", run_id=self.run_id, message=str(e))

    # -- helpers --------------------------------------------------------
    @property
    def run_id(self):
        return self.data["run_id"]

    @property
    def status(self):
        return self.data["status"]

    def step(self, agent_id):
        for s in self.data["steps"]:
            if s["agent_id"] == agent_id:
                return s
        return None

    def _trace(self, event, **fields):
        self.data["trace"].append(dict(ts=_now(), event=event, **fields))
        # Keep traces bounded; a long-lived run shouldn't grow without limit.
        if len(self.data["trace"]) > 400:
            del self.data["trace"][:-400]

    def dependencies_met(self, agent_id):
        """A step may only run once every dependency has completed."""
        spec = BY_ID[agent_id]
        for dep in spec.depends_on:
            s = self.step(dep)
            if s is None:
                continue  # dependency not part of this run — caller opted out
            if s["status"] not in (DONE, SKIPPED):
                return False, dep
        return True, None

    def next_runnable(self):
        for s in self.data["steps"]:
            if s["status"] != PENDING:
                continue
            ok, _ = self.dependencies_met(s["agent_id"])
            if ok:
                return s["agent_id"]
        return None

    # -- execution ------------------------------------------------------
    def execute(self, agent_id, fn, *, attempts=2, summarize=None):
        """Run one agent step under retry + circuit breaker, recording everything.

        `fn` does the actual work (call the model, post to Classroom, ...).
        Its return value is handed back to the caller untouched; `summarize`
        turns it into a short string for the trace so we never persist a whole
        lesson plan into the run file.
        """
        spec = BY_ID.get(agent_id)
        if spec is None:
            raise resilience.ValidationError("unknown agent '{}'".format(agent_id))
        step = self.step(agent_id)
        if step is None:
            raise resilience.ValidationError(
                "agent '{}' is not part of run {}".format(agent_id, self.run_id)
            )

        ok, missing = self.dependencies_met(agent_id)
        if not ok:
            self._trace("step.blocked", agent_id=agent_id, missing=missing)
            self.save()
            raise resilience.ValidationError(
                "{} cannot run before {} finishes".format(spec.name, BY_ID[missing].name),
                user_message="Langkah ini perlu menunggu {} selesai dahulu.".format(
                    BY_ID[missing].name
                ),
            )

        step["status"] = RUNNING
        step["started_at"] = _now()
        self._trace("step.started", agent_id=agent_id, upstreams=spec.upstreams)
        self.save()

        started = time.time()
        with resilience.log_context(cid=self.data["correlation_id"]):
            try:
                def attempt():
                    step["attempts"] += 1
                    return fn()

                result = resilience.guard(
                    "agent:{}".format(agent_id), attempt, attempts=attempts
                )
            except Exception as exc:  # noqa: BLE001
                err = resilience.classify(exc)
                step["status"] = FAILED
                step["finished_at"] = _now()
                step["duration_ms"] = int((time.time() - started) * 1000)
                step["error"] = {"code": err.code, "message": str(err)[:400],
                                 "retryable": err.retryable}
                self._trace("step.failed", agent_id=agent_id, code=err.code,
                            attempts=step["attempts"])
                self.data["status"] = FAILED
                self.save()
                resilience.error("orchestrator.step_failed", run_id=self.run_id,
                                 agent_id=agent_id, code=err.code)
                raise err

        step["status"] = AWAITING if spec.checkpoint else DONE
        step["finished_at"] = _now()
        step["duration_ms"] = int((time.time() - started) * 1000)
        step["output_summary"] = (summarize(result) if summarize else None)
        self._trace(
            "step.finished", agent_id=agent_id, attempts=step["attempts"],
            duration_ms=step["duration_ms"],
            awaiting=spec.checkpoint or None,
        )
        self._refresh_status()
        self.save()
        resilience.info("orchestrator.step_finished", run_id=self.run_id,
                        agent_id=agent_id, duration_ms=step["duration_ms"])
        return result

    def auto_execute(self, agent_id, fn, *, attempts=2, summarize=None, actor=None):
        """Transparent instrumentation for a real HTTP call, used where the
        caller (today's UI) has no explicit "approve" gesture between agents
        — a teacher moving from the RPH panel to the Materials panel IS the
        approval, there's just no button that says so yet.

        Unlike `execute`, this never blocks the real request over
        orchestration bookkeeping: if a dependency wasn't tracked in this
        run (e.g. the teacher opened a saved lesson and only ever
        regenerated the worksheet), it's marked skipped — honestly, not
        silently — rather than raising, then the step runs. A genuine
        failure from `fn` itself still raises exactly as `execute` would;
        only the dependency gate is softened.
        """
        ok, missing = self.dependencies_met(agent_id)
        if not ok:
            self._trace("step.dependency_soft_skip", agent_id=agent_id, missing=missing)
            dep_step = self.step(missing)
            if dep_step is not None and dep_step["status"] not in (DONE, SKIPPED):
                dep_step["status"] = SKIPPED
                dep_step["output_summary"] = "not run in this session"
            self.save()
        result = self.execute(agent_id, fn, attempts=attempts, summarize=summarize)
        step = self.step(agent_id)
        if step is not None and step["status"] == AWAITING:
            self.approve(agent_id, by=actor or self.data.get("owner"))
        return result

    def approve(self, agent_id, *, by=None):
        """Teacher checkpoint: unblocks the agents that depend on this step."""
        step = self.step(agent_id)
        if step is None:
            raise resilience.ValidationError("unknown step '{}'".format(agent_id))
        if step["status"] != AWAITING:
            raise resilience.ValidationError(
                "step '{}' is {}, not awaiting approval".format(agent_id, step["status"])
            )
        step["status"] = DONE
        self._trace("step.approved", agent_id=agent_id, by=by)
        self._refresh_status()
        self.save()
        return step

    def skip(self, agent_id, *, reason=""):
        step = self.step(agent_id)
        if step is None:
            raise resilience.ValidationError("unknown step '{}'".format(agent_id))
        step["status"] = SKIPPED
        self._trace("step.skipped", agent_id=agent_id, reason=reason)
        self._refresh_status()
        self.save()
        return step

    def retry_step(self, agent_id, fn, **kwargs):
        """Reset a failed step and run it again — the recovery path a reviewer
        looks for: a failure is not terminal for the whole workflow."""
        step = self.step(agent_id)
        if step is None:
            raise resilience.ValidationError("unknown step '{}'".format(agent_id))
        step["status"] = PENDING
        step["error"] = None
        self.data["status"] = RUNNING
        self._trace("step.retry_requested", agent_id=agent_id)
        self.save()
        return self.execute(agent_id, fn, **kwargs)

    def _refresh_status(self):
        statuses = [s["status"] for s in self.data["steps"]]
        if any(s == FAILED for s in statuses):
            self.data["status"] = FAILED
        elif all(s in (DONE, SKIPPED) for s in statuses):
            self.data["status"] = DONE
            self.data["finished_at"] = _now()
            self._trace("run.finished")
        elif any(s == AWAITING for s in statuses):
            self.data["status"] = AWAITING
        else:
            self.data["status"] = RUNNING

    def to_dict(self):
        d = dict(self.data)
        d["next_runnable"] = self.next_runnable()
        return d

    def summary(self):
        return {
            "run_id": self.run_id,
            "status": self.data["status"],
            "owner": self.data.get("owner"),
            "started_at": self.data.get("started_at"),
            "finished_at": self.data.get("finished_at"),
            "context": self.data.get("context", {}),
            "steps": [
                {"agent_id": s["agent_id"], "number": s["number"],
                 "status": s["status"], "attempts": s["attempts"],
                 "duration_ms": s["duration_ms"]}
                for s in self.data["steps"]
            ],
        }


# --------------------------------------------------------------------------
# Listing / housekeeping
# --------------------------------------------------------------------------


def list_runs(limit=25, owner=None):
    _ensure_dir()
    try:
        names = [n for n in os.listdir(RUNS_DIR) if n.endswith(".json")]
    except OSError:
        return []
    names.sort(reverse=True)
    out = []
    for name in names:
        run = Run.load(name[:-5])
        if run is None:
            continue
        if owner and run.data.get("owner") != owner:
            continue
        out.append(run.summary())
        if len(out) >= limit:
            break
    return out


def prune(keep=MAX_RUNS_KEPT):
    _ensure_dir()
    try:
        names = sorted(n for n in os.listdir(RUNS_DIR) if n.endswith(".json"))
    except OSError:
        return 0
    removed = 0
    for name in names[:-keep] if len(names) > keep else []:
        try:
            os.remove(os.path.join(RUNS_DIR, name))
            removed += 1
        except OSError:
            pass
    return removed


def health():
    """Aggregate orchestration health for /api/status."""
    runs = list_runs(limit=50)
    total = len(runs)
    failed = sum(1 for r in runs if r["status"] == FAILED)
    return {
        "agents_registered": len(AGENTS),
        "autonomous_agents": sum(1 for a in AGENTS if a.autonomous),
        "human_checkpoints": sum(1 for a in AGENTS if a.checkpoint),
        "recent_runs": total,
        "recent_failed_runs": failed,
        "recent_success_rate": round(100.0 * (total - failed) / total, 1) if total else None,
        "last_run": runs[0] if runs else None,
    }
