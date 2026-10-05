from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "register_umr_assets.py"
spec = importlib.util.spec_from_file_location("register_umr_assets", SCRIPT)
assert spec and spec.loader
registration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registration)


class RegistrationTests(unittest.TestCase):
    def test_create_and_verify_detects_changed_assets(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "robot_configs").mkdir()
            (root / "assets" / "g1").mkdir(parents=True)
            (root / "sample_data").mkdir()
            config = root / "robot_configs" / "g1.json"
            config.write_text(json.dumps({"robot": {"xml": "../assets/g1/g1.xml"}}))
            (root / "assets" / "g1" / "g1.xml").write_text("<mujoco/>")
            mesh = root / "assets" / "g1" / "mesh.obj"
            mesh.write_text("mesh content")
            motion = root / "sample_data" / "motion.pkl"
            motion.write_bytes(b"motion bytes")
            generated = root / registration.GENERATED_VIEWER_XML
            generated.write_text("<mujoco model='generated' />")
            slots = root / registration.SLOTS
            slots.parent.mkdir(parents=True)
            slots.write_bytes(b"slots bytes")

            fake_mujoco = SimpleNamespace(
                MjModel=SimpleNamespace(from_xml_path=lambda _: SimpleNamespace(nbody=51))
            )
            with (
                patch.dict(sys.modules, {"mujoco": fake_mujoco}),
                patch.object(registration.subprocess, "check_output", return_value="a" * 40),
                patch.object(registration.subprocess, "run", return_value=SimpleNamespace(returncode=1)),
            ):
                manifest = registration.create(root, config, motion, "motion")
                self.assertEqual(len(manifest["files"]), 5)
                registration.verify(root, manifest)
                generated.write_text("<mujoco model='regenerated' />")
                registration.verify(root, manifest)
                slots.write_bytes(b"changed slots")
                with self.assertRaisesRegex(ValueError, "changed"):
                    registration.verify(root, manifest)
                slots.write_bytes(b"slots bytes")
                mesh.write_text("changed")
                with self.assertRaisesRegex(ValueError, "changed"):
                    registration.verify(root, manifest)

    def test_rejects_unchecked_out_lfs_and_path_escape(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            pointer = root / "motion.pkl"
            pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:123\n")
            with self.assertRaisesRegex(ValueError, "Git LFS pointer"):
                registration.record(root, pointer)
            with self.assertRaisesRegex(ValueError, "escapes"):
                registration.inside(root, Path(__file__))

    def test_generated_xml_is_retained_when_referenced(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = root / "robot_configs/g1.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"robot": {"xml": "../assets/g1/g1.xml"}}))
            xml = root / "assets/g1/g1.xml"
            xml.parent.mkdir(parents=True)
            generated = root / registration.GENERATED_VIEWER_XML
            xml.write_text(f'<mujoco><include file="{generated.name}"/></mujoco>')
            generated.write_text("<mujoco/>")
            motion = root / "motion.pkl"
            motion.write_bytes(b"motion")
            slots = root / registration.SLOTS
            slots.parent.mkdir(parents=True)
            slots.write_bytes(b"slots")
            fake_mujoco = SimpleNamespace(
                MjModel=SimpleNamespace(from_xml_path=lambda _: SimpleNamespace(nbody=51))
            )
            with (patch.dict(sys.modules, {"mujoco": fake_mujoco}),
                  patch.object(registration.subprocess, "check_output", return_value="a" * 40),
                  patch.object(registration.subprocess, "run", return_value=SimpleNamespace(returncode=1))):
                manifest = registration.create(root, config, motion, "motion")
            self.assertIn(registration.GENERATED_VIEWER_XML,
                          {item["path"] for item in manifest["files"]})


if __name__ == "__main__":
    unittest.main()
