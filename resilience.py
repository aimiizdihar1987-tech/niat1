"""Cross-cutting reliability layer for Niat.

Everything in here is dependency-free (standard library only) so it works
identically on the Windows desktop, in the container and on Cloud Run.

Four things live here:

1. **Error taxonomy** — `NiatError` and friends, so a failure carries a stable
   machine-readable `code`, whether a retry could help, and a message that is
   safe to show a teacher (no stack traces, no secrets).
2. **Structured logging** — one JSON object per line on stdout, which is what
   Cloud Logging and `docker logs` both expect. Every log line carries the
   correlation id of the request or agent run that produced it.
3. **Retry with exponential backoff + jitter** — replaces the hand-rolled
   `for attempt in range(3)` loops that were scattered across the codebase.
4. **Circuit breaker + metrics** — after repeated failures a dependency is
   marked open, so Niat fails fast with a clear message instead of making
   every teacher wait 120s for the same timeout. Counters feed `/api/status`.
"""

import json
import os
import random
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# 1. Error taxonomy
# --------------------------------------------------------------------------


class NiatError(Exception):
    """Base class for every failure Niat raises deliberately.

    `code`      stable identifier, safe to branch on and to show in the UI.
    `retryable` whether trying the same call again could plausibly succeed.
    `user_message` Malay-first text a teacher can act on.
    """

    code = "niat_error"
    retryable = False
    http_status = 500
    user_message = "Sistem menghadapi masalah. Sila cuba sebentar lagi."

    def __init__(self, message="", *, detail=None, cause=None, user_message=None):
        super().__init__(message or self.user_message)
        self.detail = detail
        self.cause = cause
        if user_message:
            self.user_message = user_message

    def to_dict(self):
        return {
            "error": self.code,
            "retryable": self.retryable,
            "ralat": self.user_message,
            "message": str(self),
            "detail": self.detail,
        }


class ConfigurationError(NiatError):
    code = "configuration_error"
    retryable = False
    http_status = 503
    user_message = "Sistem belum dikonfigurasi sepenuhnya. Hubungi pentadbir."


class UpstreamError(NiatError):
    """A third party (Gemini, Supabase, Apps Script, Classroom) misbehaved."""

    code = "upstream_error"
    retryable = True
    http_status = 502
    user_message = "Perkhidmatan luar tidak dapat dihubungi. Cuba lagi sebentar."


class UpstreamTimeout(UpstreamError):
    code = "upstream_timeout"
    http_status = 504
    user_message = "Perkhidmatan luar terlalu lambat menjawab. Cuba lagi."


class RateLimited(UpstreamError):
    code = "rate_limited"
    http_status = 429
    user_message = "Kuota API penuh buat sementara. Cuba lagi dalam seminit."


class CircuitOpen(NiatError):
    """Fail fast: this dependency has been failing, don't pile on."""

    code = "circuit_open"
    retryable = True
    http_status = 503
    user_message = "Perkhidmatan ini sedang dipulihkan. Cuba lagi dalam seminit."


class ValidationError(NiatError):
    code = "validation_error"
    retryable = False
    http_status = 400
    user_message = "Maklumat yang dihantar tidak lengkap atau tidak sah."


class AgentError(NiatError):
    """An agent ran but could not produce a usable result."""

    code = "agent_error"
    retryable = True
    http_status = 502
    user_message = "Ejen gagal menyiapkan hasil. Cuba jana semula."


def classify(exc):
    """Map an arbitrary exception onto the taxonomy.

    Used at the HTTP boundary so that *every* unhandled error still produces a
    structured, non-leaking response rather than a bare 500 with a traceback.
    """
    if isinstance(exc, NiatError):
        return exc
    name = type(exc).__name__
    text = str(exc)
    if name in ("TimeoutError", "socket.timeout") or "timed out" in text.lower():
        return UpstreamTimeout(text, cause=exc)
    if "429" in text or "quota" in text.lower() or "rate limit" in text.lower():
        return RateLimited(text, cause=exc)
    if name in ("URLError", "HTTPError", "OSError", "ConnectionError", "SupabaseError"):
        return UpstreamError(text, cause=exc)
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return ValidationError(text, cause=exc)
    return NiatError(text, cause=exc)


# --------------------------------------------------------------------------
# 2. Structured logging with correlation ids
# --------------------------------------------------------------------------

_local = threading.local()
LOG_LEVEL = os.environ.get("NIAT_LOG_LEVEL", "info").lower()
_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
# Human-readable logs are friendlier on the teacher's own laptop; JSON is what
# Cloud Logging wants. Default to JSON only when we look containerised.
JSON_LOGS = os.environ.get(
    "NIAT_JSON_LOGS", "1" if os.environ.get("NIAT_CONTAINER") or os.environ.get("K_SERVICE") else "0"
) == "1"


def correlation_id():
    """Id shared by every log line and trace event of the current request/run."""
    cid = getattr(_local, "cid", None)
    if not cid:
        cid = new_correlation_id()
    return cid


def new_correlation_id(prefix="req"):
    cid = "{}_{}".format(prefix, uuid.uuid4().hex[:12])
    _local.cid = cid
    return cid


def set_correlation_id(cid):
    _local.cid = cid


class log_context:
    """`with log_context("run", run_id):` — scopes a correlation id."""

    def __init__(self, prefix="req", cid=None):
        self.cid = cid or "{}_{}".format(prefix, uuid.uuid4().hex[:12])
        self._previous = None

    def __enter__(self):
        self._previous = getattr(_local, "cid", None)
        _local.cid = self.cid
        return self.cid

    def __exit__(self, *exc):
        _local.cid = self._previous
        return False


# Keep the last few hundred lines in memory so /api/status can show recent
# failures without anyone needing shell access to the Cloud Run instance.
_RECENT = deque(maxlen=300)
_recent_lock = threading.Lock()


def log(level, event, **fields):
    if _LEVELS.get(level, 20) < _LEVELS.get(LOG_LEVEL, 20):
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": level,
        "event": event,
        "cid": correlation_id(),
    }
    record.update(fields)
    with _recent_lock:
        _RECENT.append(record)
    if JSON_LOGS:
        line = json.dumps(record, ensure_ascii=False, default=str)
    else:
        extra = " ".join(
            "{}={}".format(k, v) for k, v in fields.items() if k not in ("ts", "level", "event")
        )
        line = "[{}] {} {} {}".format(level.upper(), record["ts"], event, extra).rstrip()
    stream = sys.stderr if level in ("warn", "error") else sys.stdout
    try:
        print(line, file=stream, flush=True)
    except Exception:  # noqa: BLE001 - logging must never break the caller
        pass


def debug(event, **f):
    log("debug", event, **f)


def info(event, **f):
    log("info", event, **f)


def warn(event, **f):
    log("warn", event, **f)


def error(event, **f):
    log("error", event, **f)


def recent_logs(limit=50, level=None):
    with _recent_lock:
        items = list(_RECENT)
    if level:
        items = [r for r in items if r.get("level") == level]
    return items[-limit:]


# --------------------------------------------------------------------------
# 3. Metrics
# --------------------------------------------------------------------------

_metrics = {}
_metrics_lock = threading.Lock()
STARTED_AT = time.time()


def record(name, *, ok=True, duration_ms=None):
    with _metrics_lock:
        m = _metrics.setdefault(
            name, {"calls": 0, "failures": 0, "total_ms": 0.0, "max_ms": 0.0, "last_error_ts": None}
        )
        m["calls"] += 1
        if not ok:
            m["failures"] += 1
            m["last_error_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if duration_ms is not None:
            m["total_ms"] += duration_ms
            m["max_ms"] = max(m["max_ms"], duration_ms)


def metrics_snapshot():
    with _metrics_lock:
        out = {}
        for name, m in _metrics.items():
            calls = m["calls"] or 1
            out[name] = {
                "calls": m["calls"],
                "failures": m["failures"],
                "success_rate": round(100.0 * (m["calls"] - m["failures"]) / calls, 2),
                "avg_ms": round(m["total_ms"] / calls, 1),
                "max_ms": round(m["max_ms"], 1),
                "last_error_ts": m["last_error_ts"],
            }
    return out


def uptime_seconds():
    return int(time.time() - STARTED_AT)


# --------------------------------------------------------------------------
# 4. Retry and circuit breaker
# --------------------------------------------------------------------------


def retry(
    fn,
    *,
    attempts=3,
    base_delay=1.0,
    max_delay=20.0,
    name="call",
    retry_on=(UpstreamError, CircuitOpen),
    should_retry=None,
    sleep=time.sleep,
):
    """Call `fn()` up to `attempts` times with exponential backoff + jitter.

    Jitter matters: without it, thirty teachers hitting a rate-limited Gemini
    at the same moment all retry at the same moment and stay rate-limited.

    Non-retryable errors (bad input, missing config) are raised immediately —
    retrying those only makes the teacher wait longer for the same failure.
    """
    last = None
    for attempt in range(1, attempts + 1):
        started = time.time()
        try:
            result = fn()
            record(name, ok=True, duration_ms=(time.time() - started) * 1000)
            if attempt > 1:
                info("retry.recovered", target=name, attempt=attempt)
            return result
        except Exception as exc:  # noqa: BLE001 - classified immediately below
            err = classify(exc)
            record(name, ok=False, duration_ms=(time.time() - started) * 1000)
            last = err
            allowed = isinstance(err, retry_on) or (should_retry and should_retry(err))
            if not allowed or not err.retryable or attempt == attempts:
                error(
                    "retry.exhausted" if allowed else "call.failed",
                    target=name,
                    attempt=attempt,
                    code=err.code,
                    message=str(err)[:300],
                )
                raise err
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)  # jitter
            warn(
                "retry.scheduled",
                target=name,
                attempt=attempt,
                next_in_s=round(delay, 2),
                code=err.code,
            )
            sleep(delay)
    raise last or NiatError("retry failed without an error")


class CircuitBreaker:
    """Classic three-state breaker: closed -> open -> half_open -> closed.

    `failure_threshold` consecutive failures open the circuit. While open,
    calls fail immediately with `CircuitOpen` for `reset_after` seconds, then
    one trial call is allowed through (half-open) to test recovery.
    """

    def __init__(self, name, failure_threshold=5, reset_after=60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self._failures = 0
        self._opened_at = None
        self._state = "closed"
        self._lock = threading.Lock()

    @property
    def state(self):
        with self._lock:
            self._refresh()
            return self._state

    def _refresh(self):
        if self._state == "open" and self._opened_at is not None:
            if time.time() - self._opened_at >= self.reset_after:
                self._state = "half_open"

    def snapshot(self):
        with self._lock:
            self._refresh()
            return {
                "name": self.name,
                "state": self._state,
                "consecutive_failures": self._failures,
                "opens_for_s": (
                    max(0, int(self.reset_after - (time.time() - self._opened_at)))
                    if self._state == "open" and self._opened_at
                    else 0
                ),
            }

    def _on_success(self):
        with self._lock:
            if self._state != "closed":
                info("circuit.closed", target=self.name)
            self._failures = 0
            self._state = "closed"
            self._opened_at = None

    def _on_failure(self):
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold and self._state != "open":
                self._state = "open"
                self._opened_at = time.time()
                error("circuit.opened", target=self.name, failures=self._failures)

    def call(self, fn):
        with self._lock:
            self._refresh()
            if self._state == "open":
                raise CircuitOpen(
                    "circuit '{}' is open".format(self.name),
                    detail={"reset_after_s": self.reset_after},
                )
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            self._on_failure()
            raise classify(exc)
        self._on_success()
        return result


_breakers = {}
_breakers_lock = threading.Lock()


def breaker(name, **kwargs):
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(name, **kwargs)
        return _breakers[name]


def breakers_snapshot():
    with _breakers_lock:
        return [b.snapshot() for b in _breakers.values()]


def guard(name, fn, *, attempts=3, base_delay=1.0, failure_threshold=5, reset_after=60.0):
    """The one call site everything else should use: breaker + retry + metrics.

        text = resilience.guard("gemini", lambda: call_gemini(sys, user))
    """
    cb = breaker(name, failure_threshold=failure_threshold, reset_after=reset_after)
    return retry(
        lambda: cb.call(fn),
        attempts=attempts,
        base_delay=base_delay,
        name=name,
    )
