"""Regression guard for the differentiated-worksheet human-in-the-loop flow.

This locks in a specific safety property so a future change can't silently
reintroduce auto-posting: generating a worksheet for a class with assigned
pupil levels must NEVER post to Google Classroom by itself, and posting must
NEVER regenerate — it can only send exactly the bands the teacher already
reviewed. If either of these tests fails, that guarantee has been broken.
"""
import unittest
from unittest.mock import patch

import server


def _band_worksheet(band):
    return {
        "tajuk": "Worksheet — {}".format(band), "arahan_murid": "Answer all.",
        "jumlah_soalan": 1, "jumlah_markah": 1,
        "soalan": [{"soalan": "Q?", "pilihan": ["A", "B", "C", "D"],
                    "jawapan_betul": "A", "markah": 1, "maklum_balas": "Good."}],
    }


class DifferentiatedWorksheetReviewTests(unittest.TestCase):
    CLASS_NAME = "3 Regression Test"
    STATIC_BANDS = {
        "pupil1@example.invalid": "extension",
        "pupil2@example.invalid": "core",
        "pupil3@example.invalid": "remedial",
    }

    def test_generate_worksheet_returns_bands_without_posting(self):
        """generate_worksheet() must return all bands for review and must
        never call the hub — nothing gets posted at generation time."""
        with patch.object(server.student_levels, "bands_for_class",
                          return_value=self.STATIC_BANDS), \
                patch.object(server, "_worksheet_for_band",
                             side_effect=lambda inputs, band: _band_worksheet(band)), \
                patch.object(server, "_post_hub") as mock_post_hub:
            result = server.generate_worksheet({
                "nama_kelas": self.CLASS_NAME, "form": 3,
                "worksheet": {"bil_soalan": 1, "lots": 100, "mots": 0, "hots": 0},
            })

        mock_post_hub.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["differentiated"])
        bands_seen = {b["band"] for b in result["bands"]}
        self.assertEqual(bands_seen, {"extension", "core", "remedial"})
        for b in result["bands"]:
            self.assertTrue(b["emails"])
            self.assertEqual(b["worksheet"]["jumlah_soalan"], 1)

    def test_classroom_worksheet_refuses_without_reviewed_bands(self):
        """A differentiated class must not auto-post if the client didn't
        send back reviewed bands — this is the human-in-the-loop gate."""
        with patch.object(server.student_levels, "bands_for_class",
                          return_value=self.STATIC_BANDS), \
                patch.object(server, "_post_hub") as mock_post_hub:
            result = server.classroom_worksheet({"class_name": self.CLASS_NAME})

        mock_post_hub.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertIn("review", result["error"].lower())

    def test_classroom_worksheet_posts_exactly_the_reviewed_bands(self):
        """Posting must send precisely what was reviewed — no regeneration."""
        reviewed_bands = [
            {"band": "extension", "cefr": "B1 Mid",
             "emails": ["pupil1@example.invalid"], "worksheet": _band_worksheet("extension")},
            {"band": "core", "cefr": "B1 Low",
             "emails": ["pupil2@example.invalid"], "worksheet": _band_worksheet("core")},
        ]
        with patch.object(server, "_load_classrooms",
                          return_value={"classes": {self.CLASS_NAME: "12345"}}), \
                patch.object(server, "_worksheet_for_band") as mock_gen, \
                patch.object(server, "_post_hub",
                             return_value={"ok": True, "results": []}) as mock_post_hub:
            result = server.classroom_worksheet({
                "class_name": self.CLASS_NAME, "bands": reviewed_bands,
                "due_date": "2026-09-20", "due_time": "20:00",
            })

        mock_gen.assert_not_called()  # no regeneration — only what was reviewed is sent
        mock_post_hub.assert_called_once()
        sent = mock_post_hub.call_args[0][0]
        self.assertEqual(sent["action"], "differentiatedworksheet")
        self.assertEqual(sent["courseId"], "12345")
        self.assertEqual({g["band"] for g in sent["groups"]}, {"extension", "core"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["differentiated"])


if __name__ == "__main__":
    unittest.main()
