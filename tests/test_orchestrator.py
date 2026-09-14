"""Tests for the multi-agent orchestration state machine."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import orchestrator  # noqa: E402
import resilience  # noqa: E402


class OrchestratorTestCase(unittest.TestCase):
    def setUp(self):
        self._real_dir = orchestrator.RUNS_DIR
        self.tmp = tempfile.mkdtemp(prefix="niat-runs-")
        orchestrator.RUNS_DIR = self.tmp

    def tearDown(self):
        orchestrator.RUNS_DIR = self._real_dir
        shutil.rmtree(self.tmp, ignore_errors=True)


class RegistryTests(OrchestratorTestCase):
    def test_registry_describes_all_six_agents(self):
        reg = orchestrator.registry()
        self.assertEqual(len(reg["agents"]), 6)
        self.assertEqual([a["number"] for a in reg["agents"]], [1, 2, 3, 4, 5, 6])

    def test_every_dependency_refers_to_a_real_agent(self):
        for spec in orchestrator.AGENTS:
            for dep in spec.depends_on:
                self.assertIn(dep, orchestrator.BY_ID)

    def test_differentiation_and_reminder_are_autonomous(self):
        reg = orchestrator.registry()
        self.assertIn("agent4_differentiation", reg["autonomous_agents"])
        self.assertIn("agent6_reminder", reg["autonomous_agents"])

    def test_generative_steps_sit_behind_a_teacher_checkpoint(self):
        for aid in ("agent1_lesson_plan", "agent2_materials", "agent3_worksheet"):
            self.assertTrue(orchestrator.BY_ID[aid].checkpoint)


class RunFlowTests(OrchestratorTestCase):
    def test_happy_path_progresses_through_checkpoints(self):
        run = orchestrator.Run.start(context={"kelas": "3 Delima"}, owner="cikgu",
                                     agents=["agent1_lesson_plan", "agent2_materials"])
        self.assertEqual(run.next_runnable(), "agent1_lesson_plan")

        run.execute("agent1_lesson_plan", lambda: {"rph": "..."}, summarize=lambda r: "rph ok")
        self.assertEqual(run.step("agent1_lesson_plan")["status"], orchestrator.AWAITING)
        self.assertEqual(run.status, orchestrator.AWAITING)

        run.approve("agent1_lesson_plan", by="cikgu")
        self.assertEqual(run.next_runnable(), "agent2_materials")

        run.execute("agent2_materials", lambda: {"slides": 5})
        run.approve("agent2_materials", by="cikgu")
        self.assertEqual(run.status, orchestrator.DONE)

    def test_a_step_cannot_run_before_its_dependency(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan", "agent3_worksheet"])
        with self.assertRaises(resilience.ValidationError):
            run.execute("agent3_worksheet", lambda: "too early")
        self.assertEqual(run.step("agent3_worksheet")["status"], orchestrator.PENDING)

    def test_unapproved_checkpoint_blocks_the_next_agent(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan", "agent3_worksheet"])
        run.execute("agent1_lesson_plan", lambda: "rph")
        with self.assertRaises(resilience.ValidationError):
            run.execute("agent3_worksheet", lambda: "worksheet")
        run.approve("agent1_lesson_plan")
        self.assertEqual(run.execute("agent3_worksheet", lambda: "worksheet"), "worksheet")

    def test_skipping_an_optional_step_unblocks_the_run(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan", "agent5_reflection"])
        run.execute("agent1_lesson_plan", lambda: "rph")
        run.approve("agent1_lesson_plan")
        run.skip("agent5_reflection", reason="teacher left early")
        self.assertEqual(run.status, orchestrator.DONE)


class FailureTests(OrchestratorTestCase):
    def test_failure_is_recorded_not_swallowed(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan"])

        def boom():
            raise resilience.UpstreamError("gemini down")

        with self.assertRaises(resilience.UpstreamError):
            run.execute("agent1_lesson_plan", boom, attempts=1)

        step = run.step("agent1_lesson_plan")
        self.assertEqual(step["status"], orchestrator.FAILED)
        self.assertEqual(step["error"]["code"], "upstream_error")
        self.assertTrue(step["error"]["retryable"])
        self.assertEqual(run.status, orchestrator.FAILED)

    def test_a_failed_step_can_be_retried_back_to_health(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan"])
        with self.assertRaises(resilience.UpstreamError):
            run.execute("agent1_lesson_plan",
                        lambda: (_ for _ in ()).throw(resilience.UpstreamError("down")),
                        attempts=1)
        run.retry_step("agent1_lesson_plan", lambda: "rph at last")
        self.assertEqual(run.step("agent1_lesson_plan")["status"], orchestrator.AWAITING)
        self.assertIsNone(run.step("agent1_lesson_plan")["error"])

    def test_transient_failure_inside_a_step_is_retried_automatically(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan"])
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise resilience.UpstreamError("one blip")
            return "rph"

        self.assertEqual(run.execute("agent1_lesson_plan", flaky, attempts=3), "rph")
        self.assertEqual(run.step("agent1_lesson_plan")["attempts"], 2)

    def test_unknown_agent_is_rejected(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan"])
        with self.assertRaises(resilience.ValidationError):
            run.execute("agent99_imaginary", lambda: None)


class PersistenceTests(OrchestratorTestCase):
    def test_a_run_survives_a_restart(self):
        run = orchestrator.Run.start(context={"kelas": "5 Bestari"}, owner="cikgu",
                                     agents=["agent1_lesson_plan"])
        run.execute("agent1_lesson_plan", lambda: "rph")

        reloaded = orchestrator.Run.load(run.run_id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.data["context"]["kelas"], "5 Bestari")
        self.assertEqual(reloaded.step("agent1_lesson_plan")["status"], orchestrator.AWAITING)

    def test_trace_records_every_transition(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan"])
        run.execute("agent1_lesson_plan", lambda: "rph")
        run.approve("agent1_lesson_plan")
        events = [t["event"] for t in run.data["trace"]]
        for expected in ("run.started", "step.started", "step.finished", "step.approved"):
            self.assertIn(expected, events)

    def test_listing_filters_by_owner(self):
        orchestrator.Run.start(owner="cikgu_a", agents=["agent1_lesson_plan"])
        orchestrator.Run.start(owner="cikgu_b", agents=["agent1_lesson_plan"])
        self.assertEqual(len(orchestrator.list_runs(owner="cikgu_a")), 1)
        self.assertEqual(len(orchestrator.list_runs()), 2)

    def test_health_reports_success_rate(self):
        run = orchestrator.Run.start(agents=["agent1_lesson_plan"])
        run.execute("agent1_lesson_plan", lambda: "rph")
        health = orchestrator.health()
        self.assertEqual(health["agents_registered"], 6)
        self.assertEqual(health["recent_runs"], 1)
        self.assertEqual(health["recent_failed_runs"], 0)


if __name__ == "__main__":
    unittest.main()
