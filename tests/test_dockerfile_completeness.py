"""Guard against the image missing a module the server imports.

The Dockerfile deliberately copies an explicit list of runtime files rather
than `COPY . .`, so secrets and pupil data never become image layers. The cost
of that choice is that adding a new module and forgetting to list it produces
an image that builds cleanly and then crash-loops on boot with
ModuleNotFoundError — which is exactly what happened when resilience.py and
orchestrator.py were added.

This test reads server.py's imports and asserts that every first-party module
among them is actually copied into the image.
"""

import ast
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _server_imports():
    with open(os.path.join(ROOT, "server.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _first_party(names):
    """Modules that live in this repo as a top-level .py file."""
    return {n for n in names if os.path.isfile(os.path.join(ROOT, n + ".py"))}


def _dockerfile_copied_files():
    with open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8") as f:
        text = f.read()
    copied = set()
    for line in text.splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY"):
            continue
        line = re.sub(r"^COPY\s+(--chown=\S+\s+)?", "", line, flags=re.I)
        parts = line.split()
        for part in parts[:-1]:  # last token is the destination
            copied.add(os.path.basename(part.rstrip("/")))
    return copied


def _dockerignore_allowlist():
    """Files re-admitted with `!` after the deny-by-default `**` rule."""
    with open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8") as f:
        return {
            os.path.basename(line.strip()[1:].rstrip("/"))
            for line in f
            if line.strip().startswith("!")
        }


class DockerfileCompletenessTests(unittest.TestCase):
    def test_every_module_the_server_imports_is_in_the_image(self):
        expected = _first_party(_server_imports())
        copied = _dockerfile_copied_files()
        missing = sorted(
            "{}.py".format(m) for m in expected if "{}.py".format(m) not in copied
        )
        self.assertEqual(
            missing, [],
            "Dockerfile does not COPY these modules that server.py imports — the "
            "image would crash on boot with ModuleNotFoundError: " + ", ".join(missing),
        )

    def test_every_copied_module_is_allowed_into_the_build_context(self):
        # `.dockerignore` denies by default, so a file can be named in a COPY
        # and still be absent from the context — the build then fails with
        # "not found" even though the file exists in the repo.
        allowed = _dockerignore_allowlist()
        expected = _first_party(_server_imports())
        missing = sorted(
            "{}.py".format(m) for m in expected if "{}.py".format(m) not in allowed
        )
        self.assertEqual(
            missing, [],
            ".dockerignore does not admit these modules into the build context: "
            + ", ".join(missing),
        )

    def test_the_new_reliability_modules_are_included(self):
        copied = _dockerfile_copied_files()
        allowed = _dockerignore_allowlist()
        for module in ("resilience.py", "orchestrator.py"):
            self.assertIn(module, copied)
            self.assertIn(module, allowed)

    def test_the_public_status_page_ships_with_the_web_assets(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "web", "status.html")))
        self.assertIn("web", _dockerfile_copied_files())

    def test_the_image_still_refuses_a_blanket_copy(self):
        with open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8") as f:
            self.assertNotIn("COPY . .", f.read(),
                             "a blanket copy would put secrets and pupil data in the image")


if __name__ == "__main__":
    unittest.main()
