from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from umr_agent.agent.diagnosis_loop import (
    Action,
    RuleBasedDiagnosisModel,
    ToolCall,
    run_diagnosis,
)
from umr_agent.api.app import Settings, create_app
from umr_agent.api.wsl_attempts import AttemptDiagnosis, AttemptStatus, read_attempt

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/inspect_character_attempt.py"
spec = importlib.util.spec_from_file_location("inspect_character_attempt", SCRIPT)
assert spec and spec.loader
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)

HASH = "a" * 64
STATUS = AttemptStatus(attempt="run-001", state="completed", plan_hash=HASH,
                       motion_id="run", result={"frames": 25, "sha256": "b" * 64})
REPORT = AttemptDiagnosis(attempt="run-001", plan_hash=HASH, result_sha256="b" * 64,
                          frames=25, fps=30.0, findings=[
                              {"check": "velocity_spike", "severity": "warning",
                               "joint": "left_knee_joint", "frames": [12]}],
                          viewer_xml="assets/g1/humanoid_run_g1.floating_mjcf.xml",
                          viewer_xml_sha256="c" * 64, viewer_model_provenance="recorded in completed run",
                          checks_not_run=["visual_motion_review"],
                          thresholds={"hinge_velocity_deg_s": 720})


class DiagnosisLoopTests(unittest.TestCase):
    def test_completed_attempt_uses_two_tools_and_finishes(self) -> None:
        calls = []
        def reader(name, action):
            calls.append((name, action))
            return STATUS if action == "status" else REPORT
        reply = run_diagnosis("run-001", "Explain warnings", RuleBasedDiagnosisModel(), reader)
        self.assertEqual(calls, [("run-001", "status"), ("run-001", "diagnose")])
        self.assertEqual(reply.steps, ("get_run_status", "diagnose_result"))
        self.assertIn("left_knee_joint", reply.summary)
        self.assertIn("Visual motion quality still requires human review.", reply.summary)
        self.assertNotIn("Foot contact, skating", reply.summary)
        self.assertEqual(reply.diagnosis.frames, 25)

    def test_unfinished_attempt_stops_before_diagnosis(self) -> None:
        status = STATUS.model_copy(update={"state": "running", "result": None})
        calls = []
        def reader(name, action):
            calls.append(action)
            return status
        reply = run_diagnosis("run-001", "Review", RuleBasedDiagnosisModel(), reader)
        self.assertEqual(calls, ["status"])
        self.assertIsNone(reply.diagnosis)

    def test_model_cannot_skip_or_swap_tools(self) -> None:
        class BadModel:
            def next_action(self, goal, history, allowed):
                return ToolCall(name=Action.FINISH, summary="Looks fine")
        with self.assertRaisesRegex(ValueError, "outside"):
            run_diagnosis("run-001", "Review", BadModel(), lambda *_: STATUS)
        with self.assertRaisesRegex(ValueError, "does not match"):
            run_diagnosis("run-001", "Review", RuleBasedDiagnosisModel(),
                          lambda _, action: STATUS if action == "status" else REPORT.model_copy(update={"plan_hash": "0" * 64}))

    def test_bridge_uses_fixed_argv_and_rejects_other_attempt(self) -> None:
        with patch("umr_agent.api.wsl_attempts.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=STATUS.model_dump_json())
            result = read_attempt("Ubuntu", "/home/test/UMR", "/mnt/c/agent/register_umr_assets.py", "run-001", "status")
        self.assertEqual(result, STATUS)
        self.assertEqual(run.call_args.args[0][-6:], ["--umr-root", "/home/test/UMR", "--attempt", "run-001", "--action", "status"])
        with self.assertRaisesRegex(ValueError, "Invalid attempt"):
            read_attempt("Ubuntu", "/home/test/UMR", "/mnt/c/agent/register.py", "../other", "status")
        with patch("umr_agent.api.wsl_attempts.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=STATUS.model_copy(update={"attempt": "other"}).model_dump_json())
            with self.assertRaises(RuntimeError):
                read_attempt("Ubuntu", "/home/test/UMR", "/mnt/c/agent/register.py", "run-001", "status")

    def test_ubuntu_status_reads_plan_and_rejects_tampered_run(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / "output/agent_attempts/run-001"
            directory.mkdir(parents=True)
            plan = {"attempt": "run-001", "motion_id": "run"}
            plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            (directory / "plan.json").write_text(json.dumps({**plan, "plan_hash": plan_hash}))
            self.assertEqual(inspector.inspect_attempt(root, "run-001")["state"], "prepared")
            (directory / "run.json").write_text(json.dumps({"state": "running", "plan_hash": plan_hash}))
            self.assertEqual(inspector.inspect_attempt(root, "run-001")["state"], "running")
            (directory / "run.json").write_text(json.dumps({"state": "completed", "plan_hash": "0" * 64}))
            with self.assertRaisesRegex(ValueError, "does not match"):
                inspector.inspect_attempt(root, "run-001")

    def test_private_endpoints_require_token(self) -> None:
        token = "t" * 32
        client = TestClient(create_app(Settings(api_token=token)))
        self.assertEqual(client.get("/api/attempts/run-001/status").status_code, 401)
        self.assertEqual(client.post("/api/agent/attempts/run-001/analyze", json={}).status_code, 401)
        with patch("umr_agent.api.app.read_attempt", side_effect=lambda *args: STATUS if args[-1] == "status" else REPORT):
            headers = {"Authorization": f"Bearer {token}"}
            self.assertEqual(client.get("/api/attempts/run-001/status", headers=headers).json()["state"], "completed")
            response = client.post("/api/agent/attempts/run-001/analyze", json={"provider": "rules"}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["steps"], ["get_run_status", "diagnose_result"])


if __name__ == "__main__":
    unittest.main()
