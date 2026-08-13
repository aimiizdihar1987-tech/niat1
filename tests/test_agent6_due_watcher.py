import unittest
from unittest.mock import patch

import remind_cron
import server


class Agent6DueWatcherTests(unittest.TestCase):
    def test_watcher_passes_due_time_and_one_reminder_cap(self):
        assignments = [{
            "class_name": "3 Delima",
            "coursework_title": "Unit 3 Worksheet",
            "due_iso": "2026-08-13T10:30",
        }]
        calls = []

        def fake_remind(payload):
            calls.append(payload)
            return {"ok": True, "sent": 0, "ringkasan": "test"}

        with patch.object(remind_cron, "_teacher_email", return_value="teacher@example.test"), \
                patch.object(remind_cron, "_overdue_assignments",
                             return_value=(assignments, "hub")), \
                patch.object(remind_cron.server, "remind_agent",
                             side_effect=fake_remind), \
                patch.object(remind_cron, "log"):
            remind_cron.main()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["due_iso"], "2026-08-13T10:30")
        self.assertEqual(calls[0]["max_reminders"], 1)

    def test_reminder_history_key_identifies_exact_classroom_assignment(self):
        states = {
            "ok": True,
            "coursework": "Unit 3 Worksheet",
            "due_iso": "2026-08-13T10:30",
            "source": "hub",
            "students": [
                {"email": "missing@example.test", "name": "Aiman",
                 "submitted": False},
                {"email": "done@example.test", "name": "Bella",
                 "submitted": True},
            ],
        }
        captured = {}

        def fake_counts(key, emails):
            captured["key"] = key
            captured["emails"] = emails
            return {"missing@example.test": 0}

        decision = {
            "reminders": [{
                "emel": "missing@example.test",
                "hantar": True,
                "aras": "gentle",
                "subjek": "Your work is waiting",
                "mesej": "Hi Aiman, please turn in your work. — Cikgu",
            }]
        }

        with patch.object(server, "_submission_states", return_value=states), \
                patch.object(server.prestasi_murid, "cumulative_by_student",
                             return_value=[]), \
                patch.object(server.peringatan, "counts_for",
                             side_effect=fake_counts), \
                patch.object(server, "call_llm_json", return_value=decision):
            result = server.remind_agent({
                "class_name": "3 Delima",
                "coursework_title": "Unit 3 Worksheet",
                "dry_run": True,
                "max_reminders": 1,
            })

        self.assertTrue(result["ok"])
        self.assertEqual(captured["key"],
                         "3 Delima | Unit 3 Worksheet | 2026-08-13T10:30")
        self.assertEqual(captured["emails"], ["missing@example.test"])
        self.assertEqual(len(result["reminders"]), 1)


if __name__ == "__main__":
    unittest.main()
