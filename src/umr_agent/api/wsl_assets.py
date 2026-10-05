"""Read-only local WSL asset verification for the G1 development checkout."""

import json
import subprocess
from pathlib import PurePosixPath

from pydantic import Field

from umr_agent.domain.models import StrictModel

EXPECTED_CONFIG = "robot_configs/humanoid_retarget_unitree_g1_example.json"
EXPECTED_MOTION = "sample_data/humanoid_character/humanoid_spinkick.pkl"
EXPECTED_XML = "assets/g1/g1_29dof.xml"
EXPECTED_SLOTS = "output/g1_cpu_smoke_512/correspondence_slots_final.npz"


class AssetStatus(StrictModel):
    state: str
    message: str
    robot_id: str = "unitree-g1"
    motion_id: str = "humanoid-spin-kick"
    file_count: int | None = Field(default=None, ge=1)
    umr_git_commit: str | None = None
    robot_config_sha256: str | None = None
    robot_xml_sha256: str | None = None
    motion_sha256: str | None = None
    correspondence_slots_sha256: str | None = None
    manifest_sha256: str | None = None


def check_assets(
    distro: str | None,
    root: str | None,
    script: str | None,
    execution_mode: str = "wsl",
) -> AssetStatus:
    if execution_mode not in {"wsl", "native"}:
        return AssetStatus(state="failed", message="Asset execution mode is invalid.")
    if not all((root, script)):
        return AssetStatus(state="unconfigured", message="Asset check is not configured.")
    if execution_mode == "wsl" and not distro:
        return AssetStatus(state="unconfigured", message="WSL asset check is not configured.")
    # Values come only from the local server configuration, never an HTTP request.
    if any(not PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
           for path in (root, script)):
        return AssetStatus(state="failed", message="WSL asset paths are invalid.")
    python = f"{root}/.venv/bin/python"
    prefix = (
        ["wsl.exe", "-d", distro, "--exec", python]
        if execution_mode == "wsl"
        else [python]
    )
    command = [
        *prefix,
        script,
        "--umr-root", root,
        "--out", f"{root}/output/g1_asset_registration.json",
        "--verify", "--json",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=90, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return AssetStatus(state="failed", message="Ubuntu verification could not finish.")
    if result.returncode != 0:
        return AssetStatus(state="failed", message="Ubuntu asset verification failed. Check the registration in Ubuntu.")
    try:
        data = json.loads(result.stdout)
        if (data["verified"] is not True or data["robot_config"] != EXPECTED_CONFIG
                or data["robot_xml"] != EXPECTED_XML
                or data["motion"] != EXPECTED_MOTION or data["sequence_key"] != "humanoid_spinkick"
                or data["correspondence_slots"] != EXPECTED_SLOTS
                or not isinstance(data["file_count"], int) or data["file_count"] < 3
                or not isinstance(data["umr_git_commit"], str)
                or len(data["umr_git_commit"]) != 40):
            raise ValueError("unexpected verification result")
        digests = (
            data["robot_config_sha256"], data["robot_xml_sha256"],
            data["motion_sha256"], data["correspondence_slots_sha256"], data["manifest_sha256"],
        )
        if any(not isinstance(value, str) or len(value) != 64
               or any(char not in "0123456789abcdef" for char in value) for value in digests):
            raise ValueError("invalid asset hashes")
        return AssetStatus(
            state="verified", message="G1 and spin kick files verified in Ubuntu.",
            file_count=data["file_count"], umr_git_commit=data["umr_git_commit"],
            robot_config_sha256=digests[0], robot_xml_sha256=digests[1],
            motion_sha256=digests[2], correspondence_slots_sha256=digests[3],
            manifest_sha256=digests[4],
        )
    except (ValueError, KeyError, TypeError):
        return AssetStatus(state="failed", message="Ubuntu returned an invalid verification result.")
