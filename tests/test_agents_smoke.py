import unittest
from unittest.mock import patch

import server


class AgentSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        curriculum = server.load_dskp(3)
        skill = curriculum["bidang"][0]
        content = skill["standard_kandungan"][0]
        learning = content["standard_pembelajaran"][0]
        cls.inputs = {
            "form": 3, "minggu": "1", "hari": "Monday",
            "nama_kelas": "Container Test", "tarikh": "2026-08-13",
            "masa": "08:00", "tempoh": "60", "bil_murid": "30",
            "tahap_murid": "Mixed", "theme": curriculum["themes"][0],
            "topic": "Test Topic", "bidang_kod": skill["kod"],
            "sk_kod": content["kod"], "sp_kods": [learning["kod"]],
            "strategi": [], "emk": [], "kbat": "Apply",
            "worksheet": {"bil_soalan": 1, "lots": 100, "mots": 0, "hots": 0},
        }

    def test_agent_1_orchestration(self):
        payload = {"tajuk": "Test lesson"}
        with patch.object(server, "call_llm_json", return_value=payload), \
                patch.object(server.guardrail, "check_rph",
                             return_value=(payload, {"repairs": [], "dropped": []})):
            result = server.generate_rph(dict(self.inputs))
        self.assertEqual(result["rph"]["tajuk"], "Test lesson")

    def test_agent_2_orchestration(self):
        payload = {"slides": [{"tajuk": "Introduction", "isi": ["Point"]}]}
        inputs = dict(self.inputs)
        inputs["plan"] = {"tingkatan_kelas": "Container Test"}
        with patch.object(server, "call_llm_json", return_value=payload):
            result = server.generate_materials(inputs)
        self.assertEqual(len(result["materials"]["slides"]), 1)

    def test_agent_3_orchestration(self):
        question = {
            "soalan": "Test?", "aras": "LOTS", "pilihan": ["A", "B", "C", "D"],
            "jawapan_betul": "A", "markah": 1,
        }
        payload = {"tajuk": "Worksheet", "arahan_murid": "Answer.",
                   "soalan": [question]}
        with patch.object(server.bank, "fetch_for_generation", return_value=[]), \
                patch.object(server, "call_llm_json", return_value=payload), \
                patch.object(server.guardrail, "check_worksheet",
                             side_effect=lambda worksheet, _standards:
                             (worksheet, {"repairs": [], "dropped": []})), \
                patch.object(server.wordlist, "prompt_block", return_value=""), \
                patch.object(server.wordlist, "check_worksheet", return_value=[]):
            result = server.generate_worksheet(dict(self.inputs))
        self.assertEqual(result["worksheet"]["jumlah_soalan"], 1)

    def test_agent_4_orchestration(self):
        payload = {"refleksi": "Completed.", "report": "Good progress."}
        with patch.object(server, "call_llm_json", return_value=payload):
            result = server.generate_reflection({
                "plan": {"tingkatan_kelas": "Container Test"},
                "results": "OK", "score_avg": "75",
            })
        self.assertEqual(result["refleksi"], "Completed.")

    def test_agent_5_decision_preview(self):
        performance = [{
            "emel": "test-subject@example.invalid", "nama": "Test Subject",
            "purata": 45, "bil": 2, "terkini": 40, "trend": "down",
        }]
        decision = {"ringkasan": "Differentiated.", "assignments": [{
            "emel": "test-subject@example.invalid", "band": "remedial",
            "sebab": "Needs support",
        }]}
        with patch.object(server.prestasi_murid, "cumulative_by_student",
                          return_value=performance), \
                patch.object(server, "call_llm_json", return_value=decision):
            result = server.differentiate({
                "class_name": "Container Test", "form": 3, "decide_only": True})
        self.assertTrue(result["ok"])
        self.assertEqual(result["assignments"][0]["band"], "remedial")


if __name__ == "__main__":
    unittest.main()
