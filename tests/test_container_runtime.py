import os
import unittest
from pathlib import Path
from unittest.mock import patch

import auth
import lessons
import niat_google
import server


ROOT = Path(__file__).resolve().parents[1]


class ContainerRuntimeTests(unittest.TestCase):
    def test_dockerfile_uses_minimal_non_root_image(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("COPY . .", dockerfile)
        self.assertIn("USER niat", dockerfile)
        self.assertIn("NIAT_STORAGE=supabase", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)

    def test_dockerignore_is_deny_by_default(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertEqual(ignore.splitlines()[2], "**")
        for forbidden in ("apikey.txt", "users.json", "classroom-simulator"):
            self.assertNotIn("!" + forbidden, ignore)

    def test_complete_container_configuration_is_accepted(self):
        env = {
            "GOOGLE_API_KEY": "test-key",
            "SUPABASE_URL": "https://example.invalid",
            "SUPABASE_ANON_KEY": "anon",
            "SUPABASE_SERVICE_ROLE_KEY": "service",
            "NIAT_STORAGE": "supabase",
            "NIAT_AUTH_SECRET": "x" * 32,
            "NIAT_REQUIRE_HUB": "0",
            "NIAT_REQUIRE_GOOGLE_OAUTH": "0",
        }
        with patch.object(server, "CONTAINER_MODE", True), \
                patch.object(server, "GOOGLE_API_KEY", "test-key"), \
                patch.object(server.sb, "configured", return_value=True), \
                patch.object(server.sb, "cloud_required", return_value=True), \
                patch.dict(os.environ, env, clear=False):
            self.assertEqual(server.runtime_configuration_errors(), [])

    def test_container_rejects_missing_persistent_configuration(self):
        with patch.object(server, "CONTAINER_MODE", True), \
                patch.object(server, "GOOGLE_API_KEY", ""), \
                patch.object(server.sb, "configured", return_value=False), \
                patch.object(server.sb, "cloud_required", return_value=False), \
                patch.dict(os.environ, {"NIAT_AUTH_SECRET": "", "NIAT_STORAGE": "local",
                                        "NIAT_REQUIRE_HUB": "0",
                                        "NIAT_REQUIRE_GOOGLE_OAUTH": "0"},
                           clear=False):
            errors = server.runtime_configuration_errors()
        self.assertGreaterEqual(len(errors), 4)

    def test_reminder_environment_overrides_local_file(self):
        with patch.dict(os.environ, {
                "APPSCRIPT_HUB_URL": "https://example.invalid/hub",
                "APPSCRIPT_HUB_KEY": "environment-key"}, clear=False):
            cfg = server._read_reminder_cfg()
        self.assertEqual(cfg["APPSCRIPT_HUB_KEY"], "environment-key")

    def test_cloud_lesson_is_owned_by_signed_in_profile(self):
        inserted = []
        with patch.object(lessons.sb, "use_cloud", return_value=True), \
                patch.object(lessons, "_owner_id", return_value="owner-uuid"), \
                patch.object(lessons.sb, "insert",
                             side_effect=lambda _table, row: inserted.append(row) or [{"id": 7}]):
            lesson_id = lessons.save_lesson({"plan": {"tajuk": "Owned"}}, "teacher")
        self.assertEqual(lesson_id, 7)
        self.assertEqual(inserted[0]["owner"], "owner-uuid")

    def test_container_cookie_is_secure(self):
        with patch.object(auth, "CONTAINER_MODE", True), \
                patch.dict(os.environ, {"NIAT_COOKIE_SECURE": ""}, clear=False):
            self.assertIn("; Secure", auth.session_cookie("token"))

    def test_readiness_fails_when_database_is_unreachable(self):
        with patch.object(server, "runtime_configuration_errors", return_value=[]), \
                patch.object(server.sb, "configured", return_value=True), \
                patch.object(server.sb, "use_cloud", return_value=True), \
                patch.object(server.sb, "select",
                             side_effect=server.sb.SupabaseError("unreachable")):
            status = server.runtime_readiness(check_database=True)
        self.assertFalse(status["ready"])
        self.assertFalse(status["database_reachable"])

    def test_google_authorize_forces_account_selection(self):
        with patch.object(niat_google, "CONTAINER_MODE", False), \
                patch.object(niat_google, "_dependencies_available", return_value=True), \
                patch.object(niat_google, "_services") as services:
            self.assertEqual(niat_google.main(["--authorize"]), 0)
        services.assert_called_once_with(interactive=True, force_reauth=True)


if __name__ == "__main__":
    unittest.main()
