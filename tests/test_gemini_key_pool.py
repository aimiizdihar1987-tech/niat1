"""Regression guard for the Gemini API key pool / failover (server.call_gemini).

A single free-tier Gemini key has a very small daily quota (seen in
production: ~20 requests/day), and one differentiated-worksheet generation
alone makes 3 calls. GOOGLE_API_KEY_2 lets a second, independent key take
over automatically when the first is rate-limited, instead of failing the
whole request. These tests lock in that failover behavior.
"""
import unittest
from unittest.mock import patch

import resilience
import server


class GeminiKeyPoolFailoverTests(unittest.TestCase):
    def setUp(self):
        # Circuit breakers are a shared, named, process-global registry —
        # clear it so one test's failures can't trip a breaker another test
        # then observes as already open.
        resilience._breakers.clear()

    def test_falls_through_to_second_key_on_rate_limit(self):
        calls = []

        def fake_request(key, model, payload):
            calls.append((key, model))
            if key == "key1":
                raise resilience.RateLimited("quota exceeded")
            return {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}

        with patch.object(server, "_GEMINI_KEYS", [("key1", "model-a"), ("key2", "model-b")]), \
                patch.object(server, "_gemini_request", side_effect=fake_request):
            text = server.call_gemini("sys", "user")

        self.assertEqual(text, '{"ok": true}')
        # key1 must be tried exactly once, not retried 3x — it's already
        # rate-limited, so burning retries on it before falling through to
        # key2 would only waste the teacher's time.
        self.assertEqual(calls, [("key1", "model-a"), ("key2", "model-b")])

    def test_raises_when_every_key_fails(self):
        def fake_request(key, model, payload):
            raise resilience.ConfigurationError("bad key: " + key)

        with patch.object(server, "_GEMINI_KEYS", [("key1", "model-a"), ("key2", "model-b")]), \
                patch.object(server, "_gemini_request", side_effect=fake_request):
            with self.assertRaises(resilience.NiatError):
                server.call_gemini("sys", "user")

    def test_single_key_pool_still_works_unchanged(self):
        """No GOOGLE_API_KEY_2 configured — behaves exactly as before pooling existed."""
        with patch.object(server, "_GEMINI_KEYS", [("key1", "model-a")]), \
                patch.object(server, "_gemini_request",
                             return_value={"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}):
            text = server.call_gemini("sys", "user")
        self.assertEqual(text, "hi")

    def test_no_keys_configured_raises_immediately(self):
        with patch.object(server, "_GEMINI_KEYS", []):
            with self.assertRaises(RuntimeError):
                server.call_gemini("sys", "user")


if __name__ == "__main__":
    unittest.main()
