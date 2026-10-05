"""Diagnose a completed registered G1 Character attempt without loading pickle metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import mujoco
import numpy as np

XML = "assets/g1/g1_29dof.xml"
VIEWER_XML = "assets/g1/spin_kick_g1.floating_mjcf.xml"
ROBOT_CONFIG = "robot_configs/humanoid_retarget_unitree_g1_example.json"
MAX_NPZ_BYTES = 1024 * 1024 * 1024
FOOT_CONTACT_Z = 0.02
FOOT_SKATE_SPEED = 0.25
FOOT_SKATE_MIN_FRAMES = 2

FOOT_BODIES = {
    "left": [f"left_ankle_roll_sphere_{i}_link" for i in range(1, 6)],
    "right": [f"right_ankle_roll_sphere_{i}_link" for i in range(1, 6)],
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def findings(model: mujoco.MjModel, qpos: np.ndarray, fps: float) -> list[dict]:
    """Compare qpos to the actual MuJoCo joint layout; velocities use qvel space."""
    result: list[dict] = []
    for joint in range(model.njnt):
        kind = int(model.jnt_type[joint])
        if kind not in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
            continue
        if not model.jnt_limited[joint]:
            continue
        address = int(model.jnt_qposadr[joint])
        lo, hi = map(float, model.jnt_range[joint])
        bad = np.flatnonzero((qpos[:, address] < lo - 1e-5) | (qpos[:, address] > hi + 1e-5))
        if bad.size:
            result.append({"check": "joint_limits", "severity": "error",
                           "joint": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint) or str(joint),
                           "count": int(bad.size), "frames": bad[:20].tolist(),
                           "range": [lo, hi]})

    for joint in range(model.njnt):
        kind = int(model.jnt_type[joint])
        if kind not in (int(mujoco.mjtJoint.mjJNT_FREE), int(mujoco.mjtJoint.mjJNT_BALL)):
            continue
        offset = 3 if kind == int(mujoco.mjtJoint.mjJNT_FREE) else 0
        address = int(model.jnt_qposadr[joint]) + offset
        norms = np.linalg.norm(qpos[:, address:address + 4], axis=1)
        bad = np.flatnonzero(np.abs(norms - 1) > 1e-3)
        if bad.size:
            result.append({"check": "quaternion_norm", "severity": "error",
                           "joint": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint) or str(joint),
                           "count": int(bad.size), "frames": bad[:20].tolist()})

    threshold_rad = math.radians(720)
    speed_counts: dict[str, list[int]] = {}
    max_joint_speed = 0.0
    max_root_speed = 0.0
    velocity = np.zeros(model.nv)
    for frame in range(1, qpos.shape[0]):
        mujoco.mj_differentiatePos(model, velocity, 1.0 / fps,
                                   np.asarray(qpos[frame - 1], dtype=np.float64),
                                   np.asarray(qpos[frame], dtype=np.float64))
        for joint in range(model.njnt):
            kind = int(model.jnt_type[joint])
            dof = int(model.jnt_dofadr[joint])
            if kind == int(mujoco.mjtJoint.mjJNT_HINGE):
                speed = abs(float(velocity[dof]))
                max_joint_speed = max(max_joint_speed, speed)
                if speed > threshold_rad:
                    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint) or str(joint)
                    speed_counts.setdefault(name, []).append(frame)
            elif kind == int(mujoco.mjtJoint.mjJNT_FREE):
                speed = float(np.linalg.norm(velocity[dof:dof + 3]))
                max_root_speed = max(max_root_speed, speed)
                if speed > 5.0:
                    speed_counts.setdefault("root_translation", []).append(frame)
    for name, frames in speed_counts.items():
        result.append({"check": "velocity_spike", "severity": "warning", "joint": name,
                       "count": len(frames), "frames": frames[:20]})
    result.append({"check": "speed_summary", "severity": "info",
                   "max_hinge_deg_s": round(math.degrees(max_joint_speed), 2),
                   "max_root_m_s": round(max_root_speed, 3)})
    return result

def foot_findings(model: mujoco.MjModel, qpos: np.ndarray, fps: float) -> list[dict]:
    """Check foot-ground contact and horizontal sliding while near the ground."""
    result: list[dict] = []
    data = mujoco.MjData(model)

    body_ids: dict[str, list[int]] = {}

    for side, names in FOOT_BODIES.items():
        ids = []

        for name in names:
            body_id = mujoco.mj_name2id(
                model,
                mujoco.mjtObj.mjOBJ_BODY,
                name,
            )

            if body_id < 0:
                raise ValueError(f"Required {side} foot body is missing: {name}")

            ids.append(body_id)

        body_ids[side] = ids

    centers = {
        side: np.zeros((qpos.shape[0], 3), dtype=float)
        for side in body_ids
    }

    minimum_heights = {
        side: np.zeros(qpos.shape[0], dtype=float)
        for side in body_ids
    }

    for frame, position in enumerate(qpos):
        data.qpos[:] = np.asarray(position, dtype=np.float64)
        mujoco.mj_forward(model, data)

        for side, ids in body_ids.items():
            points = np.asarray(
                [data.xpos[body_id] for body_id in ids],
                dtype=float,
            )

            centers[side][frame] = points.mean(axis=0)
            minimum_heights[side][frame] = float(points[:, 2].min())

    for side in ("left", "right"):
        contact = minimum_heights[side] <= FOOT_CONTACT_Z
        contact_frames = np.flatnonzero(contact)

        result.append({
            "check": "foot_ground_contact",
            "severity": "info",
            "foot": side,
            "count": int(contact_frames.size),
            "frames": contact_frames[:20].tolist(),
            "minimum_height_m": round(
                float(minimum_heights[side].min()),
                5,
            ),
        })

        candidate_frames: list[int] = []

        for frame in range(1, qpos.shape[0]):
            if not (contact[frame] and contact[frame - 1]):
                continue

            xy_distance = np.linalg.norm(
                centers[side][frame, :2]
                - centers[side][frame - 1, :2]
            )

            horizontal_speed = float(xy_distance * fps)

            if horizontal_speed > FOOT_SKATE_SPEED:
                candidate_frames.append(frame)

        confirmed_frames: list[int] = []
        current_run: list[int] = []

        for frame in candidate_frames:
            if not current_run or frame == current_run[-1] + 1:
                current_run.append(frame)
            else:
                if len(current_run) >= FOOT_SKATE_MIN_FRAMES:
                    confirmed_frames.extend(current_run)

                current_run = [frame]

        if len(current_run) >= FOOT_SKATE_MIN_FRAMES:
            confirmed_frames.extend(current_run)

        if confirmed_frames:
            result.append({
                "check": "foot_skating",
                "severity": "warning",
                "foot": side,
                "count": len(confirmed_frames),
                "frames": confirmed_frames[:20],
            })

    return result


def diagnose(root: Path, attempt: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", attempt):
        raise ValueError("Invalid attempt name")
    root = root.resolve(strict=True)
    directory = (root / "output/agent_attempts" / attempt).resolve(strict=True)
    if root not in directory.parents:
        raise ValueError("Attempt path escapes UMR checkout")
    plan = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
    run = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    expected = hashlib.sha256(canonical({k: v for k, v in plan.items() if k != "plan_hash"})).hexdigest()
    if (plan.get("attempt") != attempt or plan.get("plan_hash") != expected
            or run.get("plan_hash") != expected or run.get("state") != "completed"):
        raise ValueError("A matching completed attempt is required")
    source_xml = (root / XML).resolve(strict=True)
    viewer_relative = run.get("result", {}).get("viewer_xml", VIEWER_XML)
    if not isinstance(viewer_relative, str) or viewer_relative not in {
        VIEWER_XML,
        "assets/g1/humanoid_run_g1.floating_mjcf.xml",
        "assets/g1/humanoid_speed_vault_g1.floating_mjcf.xml",
    } or viewer_relative != plan.get("viewer_xml", VIEWER_XML):
        raise ValueError("Playback model is not the one selected by the attempt")
    viewer_xml = (root / viewer_relative).resolve(strict=True)
    config = (root / ROBOT_CONFIG).resolve(strict=True)
    motion_id = plan.get("motion_id", "spin-kick")
    stems = {"spin-kick": "spin_kick_g1", "run": "humanoid_run_g1",
             "speed-vault": "humanoid_speed_vault_g1"}
    if motion_id not in stems:
        raise ValueError("Unknown Character motion in attempt")
    output = (directory / f"{stems[motion_id]}.npz").resolve(strict=True)
    if (plan.get("output") != str(output)
            or digest(source_xml) != plan.get("robot_xml_sha256")
            or digest(config) != plan.get("robot_config_sha256")
            or not output.is_file() or output.stat().st_size > MAX_NPZ_BYTES
            or digest(output) != run.get("result", {}).get("sha256")):
        raise ValueError("Robot model or result differs from the completed run")
    if root not in viewer_xml.parents:
        raise ValueError("Viewer XML escapes UMR checkout")
    # The visualizer reports this generated floating model for the spin kick.
    # It is checked as the current playback model, not as a plan-bound input.
    viewer_hash = digest(viewer_xml)
    recorded_viewer_hash = run.get("result", {}).get("viewer_xml_sha256")
    if recorded_viewer_hash is not None and recorded_viewer_hash != viewer_hash:
        raise ValueError("Viewer XML changed since the completed run")
    model = mujoco.MjModel.from_xml_path(str(viewer_xml))
    with np.load(output, allow_pickle=False) as archive:
        qpos = archive["qpos"]
        fps_array = archive["fps"]
        if qpos.ndim != 2 or qpos.shape[0] < 1 or qpos.shape[1] != model.nq:
            raise ValueError("qpos dimensions do not match the robot model")
        if not np.issubdtype(qpos.dtype, np.number) or not np.isfinite(qpos).all():
            raise ValueError("qpos must be finite numeric values")
        if fps_array.size != 1 or not np.issubdtype(fps_array.dtype, np.number):
            raise ValueError("fps must be a numeric scalar")
        fps = float(fps_array.reshape(-1)[0])
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("fps must be finite and positive")
        checks = findings(model, qpos, fps)
        checks.extend(foot_findings(model, qpos, fps))
    return {"attempt": attempt, "plan_hash": expected, "result_sha256": digest(output),
            "frames": int(qpos.shape[0]), "fps": fps, "findings": checks,
            "viewer_xml": viewer_relative, "viewer_xml_sha256": viewer_hash,
            "viewer_model_provenance": ("recorded in completed run" if recorded_viewer_hash
                                        else "current playback XML; not captured by the completed run manifest"),
            "checks_not_run": [ "visual_motion_review"],
            "thresholds": {
		"hinge_velocity_deg_s": 720,
    		"root_translation_m_s": 5.0,
    		"foot_contact_height_m": FOOT_CONTACT_Z,
    		"foot_skating_speed_m_s": FOOT_SKATE_SPEED,
    		"foot_skating_min_frames": FOOT_SKATE_MIN_FRAMES,
	}
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--umr-root", type=Path, required=True)
    parser.add_argument("--attempt", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(diagnose(args.umr_root, args.attempt), indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Diagnosis failed: {exc}\n")


if __name__ == "__main__":
    main()
