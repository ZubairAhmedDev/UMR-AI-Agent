from __future__ import annotations

import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from umr_agent.api.app import Settings, create_app
from umr_agent.api.wsl_assets import check_assets


class WslAssetTests(unittest.TestCase):
    def test_verification_uses_fixed_arguments_and_reports_only_matching_assets(self) -> None:
        output = {
            "verified": True,
            "robot_config": "robot_configs/humanoid_retarget_unitree_g1_example.json",
            "robot_xml": "assets/g1/g1_29dof.xml",
            "motion": "sample_data/humanoid_character/humanoid_spinkick.pkl",
            "correspondence_slots": "output/g1_cpu_smoke_512/correspondence_slots_final.npz",
            "sequence_key": "humanoid_spinkick",
            "umr_git_commit": "a" * 40,
            "file_count": 144,
            "robot_config_sha256": "1" * 64,
            "robot_xml_sha256": "2" * 64,
            "motion_sha256": "3" * 64,
            "correspondence_slots_sha256": "5" * 64,
            "manifest_sha256": "4" * 64,
        }
        with patch("umr_agent.api.wsl_assets.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(output))
            status = check_assets("Ubuntu", "/home/test/UMR", "/mnt/c/agent/register.py")
        self.assertEqual(status.state, "verified")
        self.assertEqual(status.file_count, 144)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["wsl.exe", "-d", "Ubuntu", "--exec"])
        self.assertEqual(command[-2:], ["--verify", "--json"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("shell", run.call_args.kwargs)

        output["motion"] = "sample_data/other.pkl"
        with patch("umr_agent.api.wsl_assets.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(output))
            status = check_assets("Ubuntu", "/home/test/UMR", "/mnt/c/agent/register.py")
        self.assertEqual(status.state, "failed")

    def test_fail_closed_on_missing_setup_and_failed_process(self) -> None:
        self.assertEqual(check_assets(None, None, None).state, "unconfigured")
        with patch("umr_agent.api.wsl_assets.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=1, stdout="")
            self.assertEqual(check_assets("Ubuntu", "/home/test/UMR", "/mnt/c/check.py").state, "failed")

    def test_status_endpoint_requires_token(self) -> None:
        client = TestClient(create_app(Settings(api_token="s" * 32)))
        self.assertEqual(client.get("/api/assets/status").status_code, 401)
        response = client.get("/api/assets/status", headers={"Authorization": f"Bearer {'s' * 32}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "unconfigured")

    def test_native_verification_executes_python_without_wsl(self) -> None:
        output = {
            "verified": True,
            "robot_config": "robot_configs/humanoid_retarget_unitree_g1_example.json",
            "robot_xml": "assets/g1/g1_29dof.xml",
            "motion": "sample_data/humanoid_character/humanoid_spinkick.pkl",
            "correspondence_slots": "output/g1_cpu_smoke_512/correspondence_slots_final.npz",
            "sequence_key": "humanoid_spinkick",
            "umr_git_commit": "a" * 40,
            "file_count": 144,
            "robot_config_sha256": "1" * 64,
            "robot_xml_sha256": "2" * 64,
            "motion_sha256": "3" * 64,
            "correspondence_slots_sha256": "5" * 64,
            "manifest_sha256": "4" * 64,
        }

        with patch("umr_agent.api.wsl_assets.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(output))
            status = check_assets(
                None,
                "/srv/UMR",
                "/srv/agent/scripts/register_umr_assets.py",
                execution_mode="native",
            )

        self.assertEqual(status.state, "verified")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/srv/UMR/.venv/bin/python")
        self.assertEqual(command[1], "/srv/agent/scripts/register_umr_assets.py")
        self.assertNotIn("wsl.exe", command)


if __name__ == "__main__":
    unittest.main()
