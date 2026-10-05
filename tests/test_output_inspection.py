from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from umr_agent.quality.metrics import inspect_motion_npz


class OutputInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "motion.npz"

    def test_three_frame_g1_shape_without_fps_does_not_invent_timing(self) -> None:
        np.savez(self.path, qpos=np.zeros((3, 36)))
        report = inspect_motion_npz(self.path, expected_width=36)
        self.assertTrue(report.valid)
        self.assertEqual((report.frame_count, report.qpos_width, report.fps), (3, 36, None))
        self.assertIn("temporal_motion", report.checks_not_run)

    def test_nonfinite_frames_are_reported_once_each(self) -> None:
        motion = np.zeros((3, 36))
        motion[1, 2] = np.nan
        motion[1, 3] = np.inf
        np.savez(self.path, qpos=motion)
        report = inspect_motion_npz(self.path)
        self.assertFalse(report.valid)
        finding = next(f for f in report.findings if f.check == "finite")
        self.assertEqual(finding.frame_indices, (1,))
        self.assertIn("1 frame(s)", finding.message)

    def test_missing_array_and_wrong_width(self) -> None:
        np.savez(self.path, other=np.zeros((3, 36)))
        self.assertIn("qpos", {f.check for f in inspect_motion_npz(self.path).findings})
        np.savez(self.path, qpos=np.zeros((3, 29)))
        self.assertIn("qpos_width", {
            f.check for f in inspect_motion_npz(self.path, expected_width=36).findings
        })

    def test_invalid_fps_is_error_and_never_replaced_by_default(self) -> None:
        np.savez(self.path, qpos=np.zeros((3, 36)), fps=np.array(0.0))
        report = inspect_motion_npz(self.path)
        self.assertIsNone(report.fps)
        self.assertIn("fps", {f.check for f in report.findings})

    def test_object_array_cannot_be_deserialized(self) -> None:
        np.savez(self.path, qpos=np.array([[object()]], dtype=object))
        with self.assertRaises(ValueError):
            inspect_motion_npz(self.path)


if __name__ == "__main__":
    unittest.main()
