"""Prepare and run a registered G1 Character motion in Ubuntu.

This is a local, single-attempt worker. Preparation writes a reviewable plan;
execution requires its exact SHA-256 as an explicit human approval input.
Only allowlisted Character motions with their own verified manifests are accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from zipfile import BadZipFile
from pathlib import Path

import numpy as np

from register_umr_assets import GENERATED_VIEWER_XML, SLOTS, inside, verify

CONFIG = "robot_configs/humanoid_retarget_unitree_g1_example.json"
XML = "assets/g1/g1_29dof.xml"
MOTION = "sample_data/humanoid_character/humanoid_spinkick.pkl"
SEQUENCE = "humanoid_spinkick"
MOTIONS = {
    "spin-kick": (MOTION, SEQUENCE, "spin_kick_g1"),
    "run": ("sample_data/humanoid_character/humanoid_run.pkl", "humanoid_run", "humanoid_run_g1"),
    "speed-vault": ("sample_data/humanoid_character/humanoid_speed_vault.pkl", "humanoid_speed_vault", "humanoid_speed_vault_g1"),
}
PIPELINE = "scripts/humanoid_retarget_pipeline_character.py"
DEFAULTS = "humanoid_retarget_defaults_humanoid_character.json"
MAX_SECONDS = 1800

PROFILES = {"baseline", "ground-contact"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def registration_path(motion_id: str) -> str:
    if motion_id not in MOTIONS:
        raise ValueError("Unsupported Character motion")
    return ("output/g1_asset_registration.json" if motion_id == "spin-kick"
            else f"output/g1_asset_registration_{motion_id}.json")


def evidence(root: Path, motion_id: str = "spin-kick") -> tuple[dict, str]:
    motion, sequence, _ = MOTIONS[motion_id]
    manifest_path = inside(root, root / registration_path(motion_id))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify(root, manifest)
    expected = {
        "robot_config": CONFIG, "robot_xml": XML, "motion": motion,
        "correspondence_slots": SLOTS, "sequence_key": sequence,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Registered inputs do not match the selected G1 Character motion")
    changed = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        text=True, capture_output=True, timeout=30, check=True,
    )
    if changed.stdout.strip():
        raise ValueError("UMR tracked files have local modifications")
    return manifest, hashlib.sha256(canonical(manifest)).hexdigest()


def attempt_dir(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name):
        raise ValueError("Attempt name must contain only letters, digits, underscore, or hyphen")
    base = (root / "output/agent_attempts").resolve(strict=False)
    if root.resolve(strict=True) not in base.parents:
        raise ValueError("Attempt base escapes UMR checkout")
    location = base / name
    if location.resolve(strict=False).parent != base:
        raise ValueError("Attempt escapes output directory")
    return location


def planned(root: Path, manifest: dict, manifest_hash: str, name: str,
            frames: int, motion_id: str = "spin-kick",
            profile: str = "baseline") -> tuple[dict, bytes]:
    motion, sequence, stem = MOTIONS[motion_id]
    if frames not in (0, 3):
        raise ValueError("Only full motion (0) or three-frame smoke (3) is supported")
    robot = json.loads(inside(root, root / CONFIG).read_text(encoding="utf-8"))
    if not isinstance(robot, dict) or set(robot) != {"robot"} or not isinstance(robot["robot"], dict):
        raise ValueError("Expected a robot-only G1 configuration")
    xml = inside(root, root / XML)
    selected_xml = inside(root, (root / CONFIG).parent / robot["robot"]["xml"])
    if selected_xml != xml:
        raise ValueError("Robot configuration selects a different XML")
    directory = attempt_dir(root, name)
    result = directory / f"{stem}.npz"
    robot["robot"]["xml"] = str(xml)
    robot["motion"] = {"data": str(inside(root, root / motion)),
                       "seq_key": sequence, "max_frames": frames}
    robot["correspondence"] = {"slots": str(inside(root, root / SLOTS))}
    robot["retarget"] = {"out": str(result)}

    if profile not in PROFILES:
        raise ValueError("Unsupported retarget profile")

    if profile == "ground-contact":
        solver = robot.setdefault("solver", {})
        solver["ground_contact_anchor_cost"] = 2.0
        solver["ground_contact_map_snap_threshold"] = 0.005

    config_bytes = (json.dumps(robot, sort_keys=True, indent=2) + "\n").encode()
    pipeline = inside(root, root / PIPELINE)
    defaults = inside(root, root / DEFAULTS)
    file_hashes = {item["path"]: item["sha256"] for item in manifest["files"]}
    plan = {
        "schema_version": 1, "attempt": name, "max_frames": frames,
        "motion_id": motion_id, "profile": profile,
        "motion_path": motion, "sequence_key": sequence,
        "viewer_xml": f"assets/g1/{stem}.floating_mjcf.xml",
        "umr_git_commit": manifest["umr_git_commit"],
        "manifest_sha256": manifest_hash,
        "robot_config_sha256": file_hashes[CONFIG],
        "robot_xml_sha256": file_hashes[XML],
        "motion_sha256": file_hashes[motion],
        "correspondence_slots_sha256": file_hashes[SLOTS],
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "pipeline_sha256": digest(pipeline), "defaults_sha256": digest(defaults),
        "worker_sha256": digest(Path(__file__).resolve()),
        "output": str(result),
        # Keep the venv entry point. Resolving this symlink selects uv's base
        # interpreter and can bypass packages installed into UMR's .venv.
        "argv": [sys.executable, str(pipeline),
                 "--config", str(directory / "character_config.json"),
                 "--stage", "retarget", "--skip-view"],
    }
    return plan, config_bytes


def prepare(root: Path, name: str, frames: int, motion_id: str = "spin-kick",
            profile: str = "baseline") -> dict:
    manifest, manifest_hash = evidence(root, motion_id)
    plan, config_bytes = planned(
        root, manifest, manifest_hash, name, frames, motion_id, profile
    )
    directory = attempt_dir(root, name)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "character_config.json").write_bytes(config_bytes)
    plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
    record = {**plan, "plan_hash": plan_hash}
    (directory / "plan.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def inspect(path: Path, root: Path, viewer_path: str = GENERATED_VIEWER_XML) -> dict:
    if not path.is_file() or path.stat().st_size > 1024 * 1024 * 1024:
        raise ValueError("Result NPZ is missing or too large")
    with np.load(path, allow_pickle=False) as archive:
        qpos = archive["qpos"]
        fps = archive["fps"]
        if qpos.ndim != 2 or qpos.shape[0] < 1 or qpos.shape[1] != 36:
            raise ValueError("Expected a nonempty G1 qpos array with width 36")
        if not np.issubdtype(qpos.dtype, np.number) or not np.isfinite(qpos).all():
            raise ValueError("Result qpos contains invalid values")
        if fps.size != 1 or not np.issubdtype(fps.dtype, np.number):
            raise ValueError("Result fps is invalid")
        rate = float(fps.reshape(-1)[0])
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("Result fps must be positive and finite")
        viewer = inside(root, root / viewer_path)
        return {"frames": int(qpos.shape[0]), "qpos_width": 36, "fps": rate,
                "sha256": digest(path),
                "viewer_xml": viewer_path,
                "viewer_xml_sha256": digest(viewer),
                "checks_not_run": ["joint_limits", "foot_ground_contact", "temporal_motion"]}


def execute(root: Path, name: str, approved_hash: str) -> dict:
    directory = attempt_dir(root, name)
    record = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
    motion_id = record.get("motion_id", "spin-kick")
    if motion_id not in MOTIONS:
        raise ValueError("Unsupported Character motion")
    manifest, manifest_hash = evidence(root, motion_id)
    profile = record.get("profile", "baseline")
    plan, config_bytes = planned(
        root,
        manifest,
        manifest_hash,
        name,
        record["max_frames"],
        motion_id,
        profile,
    )
    plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
    if (record != {**plan, "plan_hash": plan_hash} or approved_hash != plan_hash
            or not re.fullmatch(r"[0-9a-f]{64}", approved_hash)):
        raise ValueError("Approval does not match the current exact attempt plan")
    if (directory / "character_config.json").read_bytes() != config_bytes:
        raise ValueError("Prepared configuration changed")
    result_path = Path(plan["output"])
    if result_path.exists() or (directory / "run.json").exists():
        raise ValueError("Attempt has already run or produced an output")
    started = {"state": "running", "plan_hash": plan_hash}
    (directory / "run.json").write_text(json.dumps(started, indent=2) + "\n", encoding="utf-8")
    with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
        try:
            process = subprocess.run(plan["argv"], cwd=root, stdout=stdout, stderr=stderr,
                                     stdin=subprocess.DEVNULL, timeout=MAX_SECONDS, check=False)
            if process.returncode != 0:
                raise ValueError(f"UMR exited with code {process.returncode}; inspect stderr.log")
            report = inspect(result_path, root, plan["viewer_xml"])
            state = {"state": "completed", "plan_hash": plan_hash, "result": report}
        except (OSError, ValueError, KeyError, EOFError, BadZipFile,
                subprocess.TimeoutExpired) as exc:
            state = {"state": "failed_verification" if result_path.exists() else "failed",
                     "plan_hash": plan_hash, "error": str(exc)}
    (directory / "run.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "execute"])
    parser.add_argument("--umr-root", type=Path, required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--max-frames", type=int, choices=[0, 3], default=3)
    parser.add_argument("--motion-id", choices=sorted(MOTIONS), default="spin-kick")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="baseline")
    parser.add_argument("--approve-plan-hash")
    args = parser.parse_args()
    try:
        root = args.umr_root.resolve(strict=True)
        if args.action == "prepare":
            if args.approve_plan_hash is not None:
                raise ValueError("Approval is only accepted for execute")
            print(json.dumps(
                prepare(
                    root,
                    args.attempt,
                    args.max_frames,
                    args.motion_id,
                    args.profile,
                ),
                indent=2,
            ))
        else:
            if not args.approve_plan_hash:
                raise ValueError("Execute requires --approve-plan-hash")
            state = execute(root, args.attempt, args.approve_plan_hash)
            print(json.dumps(state, indent=2))
            if state["state"] != "completed":
                raise SystemExit(1)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Attempt failed: {exc}\n")


if __name__ == "__main__":
    main()
