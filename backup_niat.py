#!/usr/bin/env python3
"""
Niat backup — zips the Question Bank (bank_soalan.db) and the saved
lesson plans / worksheets (output/) into a timestamped archive.

- Backups are written OUTSIDE the project (Documents\\Niat Backups) so they
  survive even if the project folder is moved or deleted.
- Keeps the most recent KEEP archives; older ones are pruned automatically.
- Python standard library only (no pip install).

Run manually any time:   python backup_niat.py
Runs automatically daily via the Windows scheduled task "Niat Backup".
"""

import os
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Niat Backups")
KEEP = 14  # keep the last 14 backups


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, "niat_backup_{}.zip".format(stamp))

    added = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        db = os.path.join(ROOT, "bank_soalan.db")
        if os.path.exists(db):
            z.write(db, "bank_soalan.db")
            added += 1
        out = os.path.join(ROOT, "output")
        if os.path.isdir(out):
            for name in sorted(os.listdir(out)):
                p = os.path.join(out, name)
                if os.path.isfile(p):
                    z.write(p, "output/" + name)
                    added += 1

    # Prune old backups, keep the most recent KEEP.
    archives = sorted(
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith("niat_backup_") and f.endswith(".zip")
    )
    for old in archives[:-KEEP]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            pass

    print("[{}] Backup OK: {} ({} files) -> {}".format(
        stamp, os.path.basename(dest), added, BACKUP_DIR))


if __name__ == "__main__":
    main()
