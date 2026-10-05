from __future__ import annotations

import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from umr_agent.api.wsl_attempts import AttemptRejected, read_attempt, write_attempt


class AttemptBridgeTests(unittest.TestCase):
    def test_readonly_plan_response_must_match_its_hash(self) -> None:
        plan = {
            "schema_version": 1, "attempt": "run-restore", "max_frames": 3,
            "motion_id": "run", "motion_path": "sample_data/humanoid_character/humanoid_run.pkl",
            "sequence_key": "humanoid_run", "viewer_xml": "assets/g1/run.xml",
            "umr_git_commit": "a" * 40, "manifest_sha256": "b" * 64,
            "robot_config_sha256": "c" * 64, "robot_xml_sha256": "d" * 64,
            "motion_sha256": "e" * 64, "correspondence_slots_sha256": "f" * 64,
            "config_sha256": "1" * 64, "pipeline_sha256": "2" * 64,
            "defaults_sha256": "3" * 64, "worker_sha256": "4" * 64,
            "output": "/home/user/projects/UMR/output/run.npz", "argv": ["python", "script.py"],
        }
        plan["plan_hash"] = hashlib.sha256(json.dumps(
            plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        base = ("Ubuntu", "/home/user/projects/UMR", "/mnt/c/agent/scripts/register_umr_assets.py",
                "run-restore", "plan")
        with patch("umr_agent.api.wsl_attempts.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout=json.dumps(plan))) as call:
            restored = read_attempt(*base)
        self.assertEqual(restored.plan_hash, plan["plan_hash"])
        self.assertEqual(call.call_args.args[0][-2:], ["--action", "plan"])
        plan["max_frames"] = 0
        with (patch("umr_agent.api.wsl_attempts.subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout=json.dumps(plan))),
              self.assertRaisesRegex(RuntimeError, "invalid attempt report")):
            read_attempt(*base)

    def test_launch_is_fixed_argv_with_explicit_hash(self) -> None:
        approved = "a" * 64
        output = json.dumps({"attempt": "g1-run-002", "state": "queued", "plan_hash": approved})
        with patch("umr_agent.api.wsl_attempts.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout=output)) as call:
            result = write_attempt("Ubuntu", "/home/user/projects/UMR",
                                   "/mnt/c/agent/scripts/register_umr_assets.py",
                                   "launch", "g1-run-002", approved_hash=approved)
        self.assertEqual(result.state, "queued")
        command = call.call_args.args[0]
        self.assertEqual(command[:4], ["wsl.exe", "-d", "Ubuntu", "--exec"])
        self.assertEqual(command[-2:], ["--approve-plan-hash", approved])
        self.assertTrue(command[5].endswith("/launch_character_attempt.py"))
        self.assertEqual(call.call_args.kwargs["stdin"], -3)

    def test_rejects_bad_hash_and_worker_failure(self) -> None:
        with patch("umr_agent.api.wsl_attempts.subprocess.run") as call:
            with self.assertRaisesRegex(ValueError, "Approval"):
                write_attempt("Ubuntu", "/home/user/projects/UMR",
                              "/mnt/c/agent/scripts/register_umr_assets.py",
                              "launch", "g1-run-002", approved_hash="bad")
            call.assert_not_called()
        with (patch("umr_agent.api.wsl_attempts.subprocess.run",
                    return_value=SimpleNamespace(returncode=1, stdout="")),
              self.assertRaises(AttemptRejected)):
            write_attempt("Ubuntu", "/home/user/projects/UMR",
                          "/mnt/c/agent/scripts/register_umr_assets.py",
                          "launch", "g1-run-002", approved_hash="a" * 64)


if __name__ == "__main__":
    unittest.main()
