from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


def differentiate(_model, out, dt, first, second):
    out[:] = 0
    out[:3] = (second[:3] - first[:3]) / dt
    out[6] = (second[7] - first[7]) / dt


fake_mujoco = SimpleNamespace(
    mjtJoint=SimpleNamespace(mjJNT_FREE=0, mjJNT_BALL=1, mjJNT_SLIDE=2, mjJNT_HINGE=3),
    mjtObj=SimpleNamespace(mjOBJ_JOINT=0),
    mj_id2name=lambda _model, _type, joint: ("root", "knee")[joint],
    mj_differentiatePos=differentiate,
    MjModel=SimpleNamespace(from_xml_path=lambda _: None),
)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/diagnose_character_result.py"
spec = importlib.util.spec_from_file_location("diagnose_character_result", SCRIPT)
assert spec and spec.loader
with patch.dict(sys.modules, {"mujoco": fake_mujoco}):
    diagnosis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnosis)


class DiagnosisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = SimpleNamespace(
            njnt=2, nq=8, nv=7,
            jnt_type=np.array([0, 3]), jnt_limited=np.array([0, 1]),
            jnt_qposadr=np.array([0, 7]), jnt_dofadr=np.array([0, 6]),
            jnt_range=np.array([[0, 0], [-1, 1]], dtype=float),
        )
        self.clean = np.zeros((60, 8), dtype=float)
        self.clean[:, 3] = 1

    def test_clean_sequence_has_only_speed_summary(self) -> None:
        checks = diagnosis.findings(self.model, self.clean, 60)
        self.assertEqual([item["check"] for item in checks], ["speed_summary"])

    def test_limit_quaternion_and_velocity_defects_are_separate(self) -> None:
        motion = self.clean.copy()
        motion[10, 7] = 2
        motion[20, 3] = 0
        motion[30, 7] = 0.8
        checks = diagnosis.findings(self.model, motion, 60)
        self.assertIn("joint_limits", [item["check"] for item in checks])
        self.assertIn("quaternion_norm", [item["check"] for item in checks])
        self.assertIn("velocity_spike", [item["check"] for item in checks])
        self.assertEqual(next(item for item in checks if item["check"] == "joint_limits")["frames"], [10])

    def test_diagnosis_uses_current_viewer_model_and_reports_its_hash(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            attempt = "full-001"
            directory = root / "output/agent_attempts" / attempt
            directory.mkdir(parents=True)
            for relative in (diagnosis.XML, diagnosis.VIEWER_XML, diagnosis.ROBOT_CONFIG):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative)
            result = directory / "spin_kick_g1.npz"
            np.savez(result, qpos=self.clean, fps=np.array([60.0]))
            plan = {"attempt": attempt, "output": str(result),
                    "robot_xml_sha256": diagnosis.digest(root / diagnosis.XML),
                    "robot_config_sha256": diagnosis.digest(root / diagnosis.ROBOT_CONFIG)}
            plan_hash = hashlib.sha256(diagnosis.canonical(plan)).hexdigest()
            (directory / "plan.json").write_text(json.dumps({**plan, "plan_hash": plan_hash}))
            (directory / "run.json").write_text(json.dumps({"state": "completed", "plan_hash": plan_hash,
                                                           "result": {"sha256": diagnosis.digest(result)}}))
            with patch.object(
                diagnosis.mujoco.MjModel,
                "from_xml_path",
                return_value=self.model,
            ) as load, patch.object(
                diagnosis,
                "foot_findings",
                return_value=[],
            ):
                report = diagnosis.diagnose(root, attempt)
            load.assert_called_once_with(str(root / diagnosis.VIEWER_XML))
            self.assertEqual(report["viewer_xml_sha256"], diagnosis.digest(root / diagnosis.VIEWER_XML))


if __name__ == "__main__":
    unittest.main()
