from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("run_character_attempt", SCRIPTS / "run_character_attempt.py")
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
import inspect_character_attempt as reader
import launch_character_attempt as launcher


class CharacterWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        paths = {
            worker.CONFIG: json.dumps({"robot": {"name": "unitree_g1", "xml": "../assets/g1/g1_29dof.xml"}}),
            worker.XML: "<mujoco/>", worker.MOTION: "motion", worker.SLOTS: "slots",
            worker.DEFAULTS: "{}",
            worker.GENERATED_VIEWER_XML: "<mujoco/>",
            worker.PIPELINE: (
                "import argparse, json, numpy as np\n"
                "p=argparse.ArgumentParser(); p.add_argument('--config'); p.add_argument('--stage'); "
                "p.add_argument('--skip-view', action='store_true'); a=p.parse_args()\n"
                "d=json.load(open(a.config)); np.savez(d['retarget']['out'], "
                "qpos=np.zeros((3,36)), fps=np.array([60.]))\n"
            ),
        }
        for relative, content in paths.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.manifest = {"umr_git_commit": "a" * 40,
                         "files": [{"path": p, "sha256": worker.digest(self.root / p)}
                                   for p in (worker.CONFIG, worker.XML, worker.MOTION, worker.SLOTS)]}
        self.evidence_patch = patch.object(worker, "evidence", return_value=(self.manifest, "b" * 64))
        self.evidence_patch.start()
        self.addCleanup(self.evidence_patch.stop)

    def test_prepare_approve_execute_and_inspect(self) -> None:
        plan = worker.prepare(self.root, "smoke-001", 3)
        self.assertEqual(plan["argv"][0], sys.executable)
        self.assertEqual(plan["max_frames"], 3)
        self.assertFalse(Path(plan["output"]).exists())
        with self.assertRaisesRegex(ValueError, "Approval"):
            worker.execute(self.root, "smoke-001", "0" * 64)
        done = worker.execute(self.root, "smoke-001", plan["plan_hash"])
        self.assertEqual(done["state"], "completed")
        self.assertEqual(done["result"]["frames"], 3)
        self.assertEqual(done["result"]["fps"], 60.0)
        self.assertEqual(done["result"]["viewer_xml_sha256"],
                         worker.digest(self.root / worker.GENERATED_VIEWER_XML))
        with self.assertRaisesRegex(ValueError, "already run"):
            worker.execute(self.root, "smoke-001", plan["plan_hash"])

    def test_readonly_plan_recovery_validates_hash(self) -> None:
        plan = worker.prepare(self.root, "resume-001", 3)
        self.assertEqual(reader.inspect_attempt(self.root, "resume-001", "plan"), plan)
        self.assertEqual(reader.inspect_attempt(self.root, "resume-001")["state"], "prepared")
        path = self.root / "output/agent_attempts/resume-001/plan.json"
        tampered = json.loads(path.read_text(encoding="utf-8"))
        tampered["max_frames"] = 0
        path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash"):
            reader.inspect_attempt(self.root, "resume-001", "plan")

    def test_changed_config_blocks_execution(self) -> None:
        plan = worker.prepare(self.root, "smoke-002", 3)
        config = self.root / "output/agent_attempts/smoke-002/character_config.json"
        config.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            worker.execute(self.root, "smoke-002", plan["plan_hash"])
        self.assertFalse((config.parent / "run.json").exists())

    def test_run_motion_binds_registered_clip_and_rejects_substitution(self) -> None:
        motion, sequence, stem = worker.MOTIONS["run"]
        clip = self.root / motion
        clip.write_bytes(b"run motion")
        viewer = self.root / f"assets/g1/{stem}.floating_mjcf.xml"
        viewer.write_text("<mujoco/>", encoding="utf-8")
        manifest = dict(self.manifest)
        manifest.update(motion=motion, sequence_key=sequence)
        manifest["files"] = [*self.manifest["files"],
                             {"path": motion, "sha256": worker.digest(clip)}]
        with patch.object(worker, "evidence", return_value=(manifest, "c" * 64)):
            plan = worker.prepare(self.root, "run-001", 3, "run")
            self.assertEqual(plan["motion_path"], motion)
            self.assertEqual(plan["output"], str(self.root / "output/agent_attempts/run-001" / f"{stem}.npz"))
            prepared = json.loads((self.root / "output/agent_attempts/run-001/character_config.json").read_text())
            self.assertEqual(prepared["motion"], {"data": str(clip), "seq_key": sequence, "max_frames": 3})
            clip.write_bytes(b"changed")
            changed = dict(manifest)
            changed["files"] = [*self.manifest["files"],
                                {"path": motion, "sha256": worker.digest(clip)}]
            with (patch.object(worker, "evidence", return_value=(changed, "d" * 64)),
                  self.assertRaisesRegex(ValueError, "Approval")):
                worker.execute(self.root, "run-001", plan["plan_hash"])
            self.assertFalse((self.root / "output/agent_attempts/run-001/run.json").exists())

    def test_invalid_result_is_failed_verification(self) -> None:
        plan = worker.prepare(self.root, "smoke-003", 3)
        script = self.root / worker.PIPELINE
        script.write_text(script.read_text().replace("np.zeros((3,36))", "np.full((3,36), np.nan)"))
        with self.assertRaisesRegex(ValueError, "Approval"):
            worker.execute(self.root, "smoke-003", plan["plan_hash"])
        plan = worker.prepare(self.root, "smoke-004", 3)
        done = worker.execute(self.root, "smoke-004", plan["plan_hash"])
        self.assertEqual(done["state"], "failed_verification")
        self.assertIn("invalid values", done["error"])

    def test_launch_needs_exact_hash_and_is_single_use(self) -> None:
        plan = worker.prepare(self.root, "smoke-launch", 3)
        directory = self.root / "output/agent_attempts/smoke-launch"
        with patch.object(launcher, "evidence", return_value=(self.manifest, "b" * 64)):
            with self.assertRaisesRegex(ValueError, "Approval"):
                launcher.launch(self.root, "smoke-launch", "0" * 64)
            self.assertFalse((directory / "launch.json").exists())
            with patch.object(launcher.subprocess, "Popen") as popen:
                popen.return_value.pid = 424242
                queued = launcher.launch(self.root, "smoke-launch", plan["plan_hash"])
                self.assertEqual(queued["state"], "queued")
                args, kwargs = popen.call_args
                self.assertEqual(args[0][-1], plan["plan_hash"])
                self.assertTrue(kwargs["start_new_session"])
                with self.assertRaises(FileExistsError):
                    launcher.launch(self.root, "smoke-launch", plan["plan_hash"])
                self.assertEqual(popen.call_count, 1)
        with patch.object(reader.os, "kill"):
            self.assertEqual(reader.inspect_attempt(self.root, "smoke-launch")["state"], "queued")

    def test_launch_rechecks_config_before_writing_marker(self) -> None:
        plan = worker.prepare(self.root, "smoke-changed", 3)
        directory = self.root / "output/agent_attempts/smoke-changed"
        (directory / "character_config.json").write_text("{}", encoding="utf-8")
        with (patch.object(launcher, "evidence", return_value=(self.manifest, "b" * 64)),
              self.assertRaisesRegex(ValueError, "Approval")):
            launcher.launch(self.root, "smoke-changed", plan["plan_hash"])
        self.assertFalse((directory / "launch.json").exists())


if __name__ == "__main__":
    unittest.main()
