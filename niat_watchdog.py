#!/usr/bin/env python3
"""
Niat Watchdog — keeps the Niat server alive.

Runs every 30 minutes via the Windows scheduled task "Niat Watchdog":
checks http://127.0.0.1:8050/api/health and silently restarts the server
(windowless pythonw) if it is not responding. Python stdlib only.
"""

import os
import subprocess
import sys
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "watchdog_log.txt")
DETACHED_PROCESS = 0x00000008


def log(msg):
    stamp = datetime.now().isoformat(timespec="seconds")
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("[{}] {}\n".format(stamp, msg))
    except OSError:
        pass


def healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8050/api/health", timeout=6) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def main():
    if healthy():
        return  # all good - stay quiet
    env = dict(os.environ, PORT="8050", HOST="0.0.0.0")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = "pythonw"
    subprocess.Popen([pythonw, os.path.join(ROOT, "server.py")],
                     cwd=ROOT, env=env, creationflags=DETACHED_PROCESS,
                     close_fds=True)
    log("server was DOWN - restarted")


if __name__ == "__main__":
    main()
