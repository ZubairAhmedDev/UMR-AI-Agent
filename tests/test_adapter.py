from __future__ import annotations

import unittest
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.helpers import make_plan, plan_data
from umr_agent.adapter.cache import derive_correspondence_key
from umr_agent.adapter.commands import build_umr_command
from umr_agent.domain.models import ExecutionPlan


class AdapterTests(unittest.TestCase):
    @staticmethod
    def _character_fixture(base: Path, data: dict) -> None:
        repository = base / "umr"
        repository.mkdir()
        motion = repository / "sample_data/humanoid_character/spinkick.pkl"
        motion.parent.mkdir(parents=True)
        motion.write_bytes(b"trusted fixture bytes; never unpickle")
        data["motion"]["path"] = "sample_data/humanoid_character/spinkick.pkl"
        data["motion"]["sha256"] = hashlib.sha256(motion.read_bytes()).hexdigest()
        data["motion"]["sequence_key"] = "spinkick"
        (repository / "humanoid_retarget_defaults_humanoid_character.json").write_text(
            json.dumps({"motion": {"data": data["motion"]["path"], "seq_key": "spinkick"}}),
            encoding="utf-8",
        )
        config = base / "project/configs/robot.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"robot": {"name": "G1"}}), encoding="utf-8")

    def test_cache_key_is_stable_and_changes_with_robot(self) -> None:
        first = make_plan()
        second_data = plan_data()
        second_data["robot"]["tpose_sha256"] = "9" * 64  # type: ignore[index]
        second = ExecutionPlan.model_validate(second_data)
        self.assertEqual(derive_correspondence_key(first), derive_correspondence_key(first))
        self.assertNotEqual(derive_correspondence_key(first), derive_correspondence_key(second))

    def test_command_is_argv_not_shell_text(self) -> None:
        plan = make_plan(sealed=True)
        with TemporaryDirectory() as root:
            base = Path(root)
            spec = build_umr_command(
                plan,
                python_executable=base / "env/bin/python",
                umr_repository=base / "umr",
                project_root=base / "project",
            )
        args = spec.as_process_args()
        self.assertEqual(args[0], str((base / "env/bin/python").resolve(strict=False)))
        self.assertIn("--config", args)
        self.assertNotIn("shell=True", " ".join(args))

    def test_unsealed_plan_cannot_build_command(self) -> None:
        with self.assertRaises(ValueError):
            build_umr_command(
                make_plan(),
                python_executable=Path("/opt/umr-python"),
                umr_repository=Path("/opt/umr"),
                project_root=Path("/srv/project"),
            )

    def test_character_preview_uses_character_entrypoint_and_supported_flags(self) -> None:
        data = plan_data()
        data["motion"]["source_type"] = "humanoid_character"  # type: ignore[index]
        data["pipeline"]["entrypoint"] = (  # type: ignore[index]
            "scripts/humanoid_retarget_pipeline_character.py"
        )
        data["pipeline"]["defaults_path"] = None  # type: ignore[index]
        with TemporaryDirectory() as root:
            base = Path(root)
            self._character_fixture(base, data)
            plan = ExecutionPlan.model_validate(data).sealed()
            spec = build_umr_command(
                plan,
                python_executable=base / "env/bin/python",
                umr_repository=base / "umr",
                project_root=base / "project",
            )
            self.assertEqual(
                spec.argv,
                (
                    str((base / "umr/scripts/humanoid_retarget_pipeline_character.py").resolve()),
                    "--config",
                    str((base / "project/configs/robot.json").resolve()),
                    "--skip-view",
                    "--dry-run",
                ),
            )

    def test_character_preview_rejects_changed_config_or_motion_bytes(self) -> None:
        data = plan_data()
        data["motion"]["source_type"] = "humanoid_character"  # type: ignore[index]
        data["pipeline"]["entrypoint"] = (  # type: ignore[index]
            "scripts/humanoid_retarget_pipeline_character.py"
        )
        data["pipeline"]["defaults_path"] = None  # type: ignore[index]
        with TemporaryDirectory() as root:
            base = Path(root)
            self._character_fixture(base, data)
            plan = ExecutionPlan.model_validate(data).sealed()

            def preview() -> None:
                build_umr_command(plan, python_executable=base / "env/bin/python",
                                  umr_repository=base / "umr", project_root=base / "project")

            config = base / "project/configs/robot.json"
            config.write_text(json.dumps({"motion": {"data": "another.pkl"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different motion"):
                preview()
            config.write_text(json.dumps({"motion": {"seq_key": "other"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different sequence"):
                preview()
            config.write_text("{}", encoding="utf-8")
            motion = base / "umr/sample_data/humanoid_character/spinkick.pkl"
            motion.write_bytes(b"changed motion")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                preview()

    def test_character_pipeline_rejects_mismatched_source_and_unsupported_flag(self) -> None:
        data = plan_data()
        data["pipeline"]["entrypoint"] = (  # type: ignore[index]
            "scripts/humanoid_retarget_pipeline_character.py"
        )
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            build_umr_command(
                ExecutionPlan.model_validate(data).sealed(),
                python_executable=Path("/opt/umr-python"),
                umr_repository=Path("/opt/umr"),
                project_root=Path("/srv/project"),
            )
        data["motion"]["source_type"] = "humanoid_character"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "does not accept --defaults"):
            build_umr_command(
                ExecutionPlan.model_validate(data).sealed(),
                python_executable=Path("/opt/umr-python"),
                umr_repository=Path("/opt/umr"),
                project_root=Path("/srv/project"),
            )


if __name__ == "__main__":
    unittest.main()
