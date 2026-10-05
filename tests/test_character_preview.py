from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from umr_agent.adapter.character_preview import prepare_character_preview
from umr_agent.agent.reviews import InputReview


def _write(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


class CharacterPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = json.dumps({"robot": {"name": "unitree_g1", "xml": "../assets/g1/g1_29dof.xml",
                                       "tpose_qpos": {"hip": 0.1}}}).encode()
        config_hash = _write(self.root,
                             "robot_configs/humanoid_retarget_unitree_g1_example.json", config)
        xml_hash = _write(self.root, "assets/g1/g1_29dof.xml", b"robot")
        motion_hash = _write(self.root,
                             "sample_data/humanoid_character/humanoid_spinkick.pkl", b"motion")
        self.slots_hash = _write(self.root,
                                 "output/g1_cpu_smoke_512/correspondence_slots_final.npz",
                                 b"slots")
        review = InputReview(
            robot_id="unitree-g1", motion_id="humanoid-spin-kick",
            robot_config_sha256=config_hash, robot_xml_sha256=xml_hash,
            motion_sha256=motion_hash, manifest_sha256="1" * 64,
            correspondence_slots_sha256=self.slots_hash,
            umr_git_commit="a" * 40, file_count=144, correspondence_workers=6,
        )
        self.review = review.model_copy(update={"review_hash": review.compute_hash()})

    def _preview(self, **kwargs):
        return prepare_character_preview(
            kwargs.get("review", self.review), umr_root=self.root,
            python_executable=self.root / ".venv/bin/python",
            attempt_name=kwargs.get("attempt_name", "attempt-001"),
        )

    def test_derived_config_selects_verified_motion_slots_and_is_dry_run(self) -> None:
        preview = self._preview()
        config = json.loads(preview.config_path.read_text())
        self.assertEqual(Path(config["robot"]["xml"]).resolve(), (self.root / self.review.robot_xml).resolve())
        self.assertEqual(Path(config["motion"]["data"]).resolve(), (self.root / self.review.motion).resolve())
        self.assertEqual(Path(config["correspondence"]["slots"]).resolve(), preview.slots_path.resolve())
        self.assertEqual(Path(config["retarget"]["out"]).resolve(), preview.result_path.resolve())
        self.assertEqual(config["retarget"]["out"], str(preview.result_path))
        self.assertEqual(preview.argv[-4:], ("--stage", "retarget", "--skip-view", "--dry-run"))
        self.assertFalse(preview.result_path.exists())
        with self.assertRaises(FileExistsError):
            self._preview()

    def test_changed_slots_or_motion_fail_before_writing_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            (self.root / self.review.correspondence_slots).write_bytes(b"changed slots")
            self._preview()
        self.assertFalse((self.root / "output/agent_attempts/attempt-001").exists())
        (self.root / self.review.correspondence_slots).write_bytes(b"slots")
        (self.root / self.review.motion).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self._preview()

    def test_attempt_name_cannot_escape_workspace(self) -> None:
        with self.assertRaisesRegex(ValueError, "attempt name"):
            self._preview(attempt_name="../other")


if __name__ == "__main__":
    unittest.main()
