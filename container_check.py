#!/usr/bin/env python3
"""Static pre-build checks for the Niat production container."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    required = [
        "Dockerfile", ".dockerignore", ".gcloudignore", "requirements.txt",
        "server.py", "auth.py", "supabase_client.py", "web/index.html",
        "prompts/agent1_rph.md", "prompts/agent6_reminder.md",
        "data/cefr_b1_wordlist.json",
    ]
    errors = ["missing: " + path for path in required if not (ROOT / path).is_file()]

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    checks = {
        "Dockerfile must not copy the workspace": "COPY . ." not in dockerfile,
        "container must run as non-root": "USER niat" in dockerfile,
        "container must force Supabase": "NIAT_STORAGE=supabase" in dockerfile,
        "Docker context must deny by default": "\n**\n" in dockerignore,
        "Google API client must be installed": "google-api-python-client" in requirements,
    }
    errors.extend(label for label, passed in checks.items() if not passed)
    if errors:
        for error in errors:
            print("FAIL: " + error)
        raise SystemExit(1)
    print("Container pre-build checks passed ({} runtime files checked).".format(len(required)))


if __name__ == "__main__":
    main()
