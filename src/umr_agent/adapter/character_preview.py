"""Materialize a bounded dry-run preview for the verified G1 Character example."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from umr_agent.agent.reviews import InputReview
from umr_agent.api.wsl_assets import EXPECTED_SLOTS
from umr_agent.validation.assets import confine_path, sha256_file

SEQUENCE_KEY = "humanoid_spinkick"


@dataclass(frozen=True, slots=True)
class CharacterPreview:
    config_path: Path
    config_sha256: str
    slots_path: Path
    slots_sha256: str
    result_path: Path
    argv: tuple[str, ...]


def _verified_file(root: Path, relative: str, digest: str, suffix: str) -> Path:
    path = confine_path(root, relative)
    if not path.is_file() or path.suffix.lower() != suffix:
        raise ValueError(f"Required registered {suffix} asset is unavailable: {relative}")
    if sha256_file(path) != digest:
        raise ValueError(f"Registered asset SHA-256 mismatch: {relative}")
    return path


def prepare_character_preview(
    review: InputReview,
    *,
    umr_root: Path,
    python_executable: Path,
    attempt_name: str,
) -> CharacterPreview:
    """Write only an attempt config; return argv ending in --dry-run.

    The review is limited to the already verified G1 spin kick. This function
    never launches a subprocess.
    """
    if review.review_hash != review.compute_hash() or review.executable:
        raise ValueError("A valid read-only input review is required")
    if review.robot_id != "unitree-g1" or review.motion_id != "humanoid-spin-kick":
        raise ValueError("Only the reviewed G1 spin kick is supported")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", attempt_name):
        raise ValueError("Invalid attempt name")
    if (review.correspondence_slots != EXPECTED_SLOTS
            or not re.fullmatch(r"[0-9a-f]{64}", review.correspondence_slots_sha256)):
        raise ValueError("A registered slots SHA-256 is required")

    root = umr_root.resolve(strict=True)
    source_config = _verified_file(root, review.robot_config, review.robot_config_sha256, ".json")
    xml = _verified_file(root, review.robot_xml, review.robot_xml_sha256, ".xml")
    motion = _verified_file(root, review.motion, review.motion_sha256, ".pkl")
    slots = _verified_file(root, review.correspondence_slots,
                           review.correspondence_slots_sha256, ".npz")
    try:
        config = json.loads(source_config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Robot config is not valid JSON") from exc
    if not isinstance(config, dict) or any(
        key in config for key in ("motion", "correspondence", "retarget", "extends")
    ):
        raise ValueError("Robot config cannot be safely overlaid for this preview")
    robot = config.get("robot")
    if not isinstance(robot, dict) or not isinstance(robot.get("xml"), str):
        raise ValueError("Robot XML selection is missing")
    if (source_config.parent / robot["xml"]).resolve(strict=True) != xml:
        raise ValueError("Robot config selects a different XML")

    attempt = confine_path(root, f"output/agent_attempts/{attempt_name}")
    config_path = attempt / "character_config.json"
    result_path = attempt / "spin_kick_g1.npz"
    robot["xml"] = str(xml)
    config["motion"] = {"data": str(motion), "seq_key": SEQUENCE_KEY}
    config["correspondence"] = {"slots": str(slots)}
    config["retarget"] = {"out": str(result_path)}
    encoded = (json.dumps(config, sort_keys=True, indent=2) + "\n").encode("utf-8")
    attempt.mkdir(parents=True, exist_ok=False)
    config_path.write_bytes(encoded)
    argv = (
        str(python_executable.resolve(strict=False)),
        str(confine_path(root, "scripts/humanoid_retarget_pipeline_character.py")),
        "--config", str(config_path), "--stage", "retarget", "--skip-view", "--dry-run",
    )
    return CharacterPreview(
        config_path=config_path,
        config_sha256=hashlib.sha256(encoded).hexdigest(),
        slots_path=slots,
        slots_sha256=review.correspondence_slots_sha256,
        result_path=result_path,
        argv=argv,
    )
