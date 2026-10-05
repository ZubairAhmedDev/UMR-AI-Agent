from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.helpers import make_plan, plan_data
from umr_agent.artifacts.manifest import build_manifest, verify_manifest
from umr_agent.domain.models import ExecutionPlan
from umr_agent.validation.assets import (
    confine_path,
    inline_tpose_sha256,
    validate_motion_asset,
    validate_robot_asset,
)


class ValidationAndManifestTests(unittest.TestCase):
    def test_embedded_tpose_is_bound_to_robot_config_and_rejects_changes(self) -> None:
        with TemporaryDirectory() as root:
            project = Path(root)
            xml = project / "assets/robot.xml"
            xml.parent.mkdir(parents=True)
            xml.write_bytes(b"robot model")
            pose = {"left_hip": 0.1, "right_hip": -0.1}
            config = project / "configs/robot.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"robot": {"xml": "assets/robot.xml",
                                                    "tpose_qpos": pose}}), encoding="utf-8")
            data = plan_data()
            data["robot"]["tpose_qpos_path"] = None  # type: ignore[index]
            data["robot"]["asset_sha256"] = hashlib.sha256(xml.read_bytes()).hexdigest()  # type: ignore[index]
            data["robot"]["tpose_sha256"] = inline_tpose_sha256(pose)  # type: ignore[index]
            data["pipeline"]["robot_config_sha256"] = hashlib.sha256(  # type: ignore[index]
                config.read_bytes()
            ).hexdigest()
            plan = ExecutionPlan.model_validate(data)
            self.assertEqual(validate_robot_asset(plan.robot, project, plan.pipeline), [])
            config.write_text(json.dumps({"robot": {"xml": "assets/robot.xml",
                                                    "tpose_qpos": {"left_hip": 0.3}}}),
                              encoding="utf-8")
            findings = validate_robot_asset(plan.robot, project, plan.pipeline)
            self.assertIn("checksum_mismatch", {item.code for item in findings})
            data["pipeline"]["robot_config_sha256"] = hashlib.sha256(  # type: ignore[index]
                config.read_bytes()
            ).hexdigest()
            updated = ExecutionPlan.model_validate(data)
            findings = validate_robot_asset(updated.robot, project, updated.pipeline)
            self.assertIn("tpose_checksum_mismatch", {item.code for item in findings})
            config.write_text(json.dumps({"robot": {"xml": "assets/other.xml",
                                                    "tpose_qpos": pose}}), encoding="utf-8")
            data["pipeline"]["robot_config_sha256"] = hashlib.sha256(  # type: ignore[index]
                config.read_bytes()
            ).hexdigest()
            updated = ExecutionPlan.model_validate(data)
            findings = validate_robot_asset(updated.robot, project, updated.pipeline)
            self.assertIn("invalid_inline_tpose", {item.code for item in findings})

    def test_embedded_tpose_rejects_invalid_values_and_missing_config_hash(self) -> None:
        data = plan_data()
        data["robot"]["tpose_qpos_path"] = None  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "registered robot config"):
            ExecutionPlan.model_validate(data)
        for pose in ({"joint": float("nan")}, {"joint": True}, {}):
            with self.assertRaises(ValueError):
                inline_tpose_sha256(pose)

    def test_confine_path_blocks_escape(self) -> None:
        with TemporaryDirectory() as root, self.assertRaises(ValueError):
            confine_path(Path(root), "../escape.txt")

    def test_motion_validator_accepts_registered_bytes(self) -> None:
        with TemporaryDirectory() as root:
            project = Path(root)
            path = project / "assets/motion.npz"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"fixture-motion")
            data = plan_data()
            data["motion"]["sha256"] = hashlib.sha256(b"fixture-motion").hexdigest()  # type: ignore[index]
            plan = ExecutionPlan.model_validate(data)
            self.assertEqual(validate_motion_asset(plan.motion, project), [])

    def test_character_motion_pkl_requires_matching_source_type_and_checksum(self) -> None:
        with TemporaryDirectory() as root:
            project = Path(root)
            path = project / "assets/spinkick.pkl"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"registered-character-motion")
            data = plan_data()
            data["motion"]["path"] = "assets/spinkick.pkl"  # type: ignore[index]
            data["motion"]["sha256"] = hashlib.sha256(  # type: ignore[index]
                b"registered-character-motion"
            ).hexdigest()
            data["motion"]["source_type"] = "humanoid_character"  # type: ignore[index]
            motion = ExecutionPlan.model_validate(data).motion
            self.assertEqual(validate_motion_asset(motion, project), [])

            data["motion"]["source_type"] = "smplx"  # type: ignore[index]
            findings = validate_motion_asset(ExecutionPlan.model_validate(data).motion, project)
            self.assertIn("unsupported_extension", {finding.code for finding in findings})

            path.write_bytes(b"changed-character-motion")
            data["motion"]["source_type"] = "humanoid_character"  # type: ignore[index]
            findings = validate_motion_asset(ExecutionPlan.model_validate(data).motion, project)
            self.assertIn("checksum_mismatch", {finding.code for finding in findings})

    def test_manifest_detects_mutated_artifact(self) -> None:
        with TemporaryDirectory() as root:
            output_root = Path(root)
            result = output_root / "result.npz"
            result.write_bytes(b"first")
            manifest = build_manifest(
                attempt_id="attempt-001",
                plan=make_plan(sealed=True),
                output_root=output_root,
                artifacts=[("robot_motion_npz", "result.npz", "application/octet-stream")],
            )
            self.assertEqual(verify_manifest(manifest, output_root), [])
            result.write_bytes(b"changed")
            errors = verify_manifest(manifest, output_root)
            self.assertTrue(any("mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
