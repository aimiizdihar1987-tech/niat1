"""Tests for the retry / circuit-breaker / error-taxonomy layer."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import resilience  # noqa: E402


class ErrorTaxonomyTests(unittest.TestCase):
    def test_timeout_is_classified_as_retryable_upstream(self):
        err = resilience.classify(TimeoutError("timed out"))
        self.assertIsInstance(err, resilience.UpstreamTimeout)
        self.assertTrue(err.retryable)
        self.assertEqual(err.http_status, 504)

    def test_quota_message_becomes_rate_limited(self):
        err = resilience.classify(RuntimeError("HTTP 429 quota exceeded"))
        self.assertIsInstance(err, resilience.RateLimited)

    def test_bad_input_is_not_retryable(self):
        err = resilience.classify(ValueError("kelas missing"))
        self.assertFalse(err.retryable)
        self.assertEqual(err.http_status, 400)

    def test_niat_errors_pass_through_unchanged(self):
        original = resilience.ConfigurationError("no key")
        self.assertIs(resilience.classify(original), original)

    def test_payload_is_safe_to_return_to_a_browser(self):
        payload = resilience.UpstreamError("raw detail with https://key@host").to_dict()
        self.assertIn("ralat", payload)
        self.assertEqual(payload["error"], "upstream_error")
        self.assertTrue(payload["retryable"])


class RetryTests(unittest.TestCase):
    def test_succeeds_after_transient_failures(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise resilience.UpstreamError("503")
            return "ok"

        result = resilience.retry(flaky, attempts=3, name="t.flaky", sleep=lambda s: None)
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)

    def test_gives_up_after_the_attempt_budget(self):
        calls = {"n": 0}

        def always_fails():
            calls["n"] += 1
            raise resilience.UpstreamError("503")

        with self.assertRaises(resilience.UpstreamError):
            resilience.retry(always_fails, attempts=3, name="t.dead", sleep=lambda s: None)
        self.assertEqual(calls["n"], 3)

    def test_does_not_retry_a_permanent_error(self):
        calls = {"n": 0}

        def bad_config():
            calls["n"] += 1
            raise resilience.ConfigurationError("missing API key")

        with self.assertRaises(resilience.ConfigurationError):
            resilience.retry(bad_config, attempts=5, name="t.config", sleep=lambda s: None)
        self.assertEqual(calls["n"], 1, "permanent errors must not be retried")

    def test_backoff_grows_and_is_jittered(self):
        delays = []

        def fails():
            raise resilience.UpstreamError("503")

        with self.assertRaises(resilience.UpstreamError):
            resilience.retry(fails, attempts=4, base_delay=1.0, name="t.backoff",
                             sleep=delays.append)
        self.assertEqual(len(delays), 3)
        self.assertLess(delays[0], delays[-1], "delay should grow")
        self.assertTrue(all(d > 0 for d in delays))


class CircuitBreakerTests(unittest.TestCase):
    def test_opens_after_threshold_and_fails_fast(self):
        cb = resilience.CircuitBreaker("t.cb", failure_threshold=3, reset_after=60)
        for _ in range(3):
            with self.assertRaises(resilience.UpstreamError):
                cb.call(lambda: (_ for _ in ()).throw(resilience.UpstreamError("boom")))
        self.assertEqual(cb.state, "open")

        calls = {"n": 0}

        def should_not_run():
            calls["n"] += 1

        with self.assertRaises(resilience.CircuitOpen):
            cb.call(should_not_run)
        self.assertEqual(calls["n"], 0, "open circuit must not reach the upstream")

    def test_half_open_then_closes_on_recovery(self):
        cb = resilience.CircuitBreaker("t.cb2", failure_threshold=1, reset_after=0)
        with self.assertRaises(resilience.UpstreamError):
            cb.call(lambda: (_ for _ in ()).throw(resilience.UpstreamError("boom")))
        self.assertEqual(cb.state, "half_open")
        self.assertEqual(cb.call(lambda: "recovered"), "recovered")
        self.assertEqual(cb.state, "closed")

    def test_success_resets_the_failure_count(self):
        cb = resilience.CircuitBreaker("t.cb3", failure_threshold=3)
        with self.assertRaises(resilience.UpstreamError):
            cb.call(lambda: (_ for _ in ()).throw(resilience.UpstreamError("boom")))
        cb.call(lambda: "fine")
        self.assertEqual(cb.snapshot()["consecutive_failures"], 0)


class ObservabilityTests(unittest.TestCase):
    def test_metrics_track_success_rate(self):
        name = "t.metrics.{}".format(id(self))
        resilience.record(name, ok=True, duration_ms=10)
        resilience.record(name, ok=False, duration_ms=30)
        snap = resilience.metrics_snapshot()[name]
        self.assertEqual(snap["calls"], 2)
        self.assertEqual(snap["failures"], 1)
        self.assertEqual(snap["success_rate"], 50.0)

    def test_correlation_id_is_scoped(self):
        with resilience.log_context(cid="cid_outer"):
            self.assertEqual(resilience.correlation_id(), "cid_outer")
            with resilience.log_context(cid="cid_inner"):
                self.assertEqual(resilience.correlation_id(), "cid_inner")
            self.assertEqual(resilience.correlation_id(), "cid_outer")

    def test_recent_errors_are_retrievable(self):
        resilience.error("test.boom", detail="x")
        events = [r["event"] for r in resilience.recent_logs(limit=50, level="error")]
        self.assertIn("test.boom", events)


if __name__ == "__main__":
    unittest.main()
