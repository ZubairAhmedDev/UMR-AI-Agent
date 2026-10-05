"""Token-protected API's fixed command bridge to the Ubuntu UMR checkout."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import PurePosixPath

from pydantic import Field, model_validator

from umr_agent.domain.models import StrictModel


class AttemptStatus(StrictModel):
    attempt: str
    state: str
    plan_hash: str
    motion_id: str
    profile: str = Field(
        default="baseline",
        pattern=r"^(baseline|ground-contact)$",
    )
    result: dict | None = None


class AttemptDiagnosis(StrictModel):
    attempt: str
    plan_hash: str
    result_sha256: str
    frames: int = Field(gt=0)
    fps: float = Field(gt=0)
    findings: list[dict]
    viewer_xml: str
    viewer_xml_sha256: str
    viewer_model_provenance: str
    checks_not_run: list[str]
    thresholds: dict


class PreparedAttempt(StrictModel):
    schema_version: int
    attempt: str
    max_frames: int
    motion_id: str
    profile: str = Field(
        default="baseline",
        pattern=r"^(baseline|ground-contact)$",
    )
    motion_path: str
    sequence_key: str
    viewer_xml: str
    umr_git_commit: str
    manifest_sha256: str
    robot_config_sha256: str
    robot_xml_sha256: str
    motion_sha256: str
    correspondence_slots_sha256: str
    config_sha256: str
    pipeline_sha256: str
    defaults_sha256: str
    worker_sha256: str
    output: str
    argv: tuple[str, ...]
    plan_hash: str

    @model_validator(mode="after")
    def validate_hash(self) -> PreparedAttempt:
        payload = self.model_dump(mode="json", exclude={"plan_hash"})

        # Preserve hashes for plans created before the profile field existed.
        if "profile" not in self.model_fields_set:
            payload.pop("profile", None)

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        if hashlib.sha256(canonical).hexdigest() != self.plan_hash:
            raise ValueError("Prepared plan hash does not match its fields")
        return self


class QueuedAttempt(StrictModel):
    attempt: str
    state: str
    plan_hash: str


class AttemptRejected(RuntimeError):
    """Ubuntu rejected a submitted plan without executing it."""


def write_attempt(distro: str | None, root: str | None, registration_script: str | None,
                  action: str, attempt: str, motion_id: str | None = None,
                  max_frames: int | None = None, approved_hash: str | None = None,
                  profile: str | None = None, execution_mode: str = "wsl"
                  ) -> PreparedAttempt | QueuedAttempt:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", attempt):
        raise ValueError("Invalid attempt name")
    if action == "prepare":
        profile = profile or "baseline"

        if (
            motion_id not in {"spin-kick", "run", "speed-vault"}
            or max_frames not in {0, 3}
            or approved_hash is not None
            or profile not in {"baseline", "ground-contact"}
        ):
            raise ValueError("Unsupported registered motion, frame limit, or retarget profile")
    elif action == "launch":
        if (
            motion_id is not None
            or max_frames is not None
            or profile is not None
            or not approved_hash
            or not re.fullmatch(r"[0-9a-f]{64}", approved_hash)
        ):
            raise ValueError("Approval must match a 64-character plan hash")
    else:
        raise ValueError("Unknown attempt action")
    if execution_mode not in {"wsl", "native"}:
        raise RuntimeError("Attempt execution mode is invalid")
    if not all((root, registration_script)):
        raise RuntimeError("Attempt bridge is not configured")
    if execution_mode == "wsl" and (
        not distro or not re.fullmatch(r"[A-Za-z0-9_-]+", distro)
    ):
        raise RuntimeError("Ubuntu bridge is not configured")

    root_path, script_path = PurePosixPath(root), PurePosixPath(registration_script)
    if any(not path.is_absolute() or ".." in path.parts for path in (root_path, script_path)):
        raise RuntimeError("Attempt bridge paths are invalid")

    python = str(root_path / ".venv/bin/python")
    prefix = (
        ["wsl.exe", "-d", distro, "--exec", python]
        if execution_mode == "wsl"
        else [python]
    )
    common = ["--umr-root", root, "--attempt", attempt]

    if action == "prepare":
        command = [
            *prefix,
            str(script_path.with_name("run_character_attempt.py")),
            "prepare",
            *common,
            "--motion-id", motion_id,
            "--max-frames", str(max_frames),
            "--profile", profile,
        ]
    else:
        command = [
            *prefix,
            str(script_path.with_name("launch_character_attempt.py")),
            *common,
            "--approve-plan-hash", approved_hash,
        ]
    try:
        process = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Ubuntu attempt command could not finish") from exc
    if process.returncode != 0:
        raise AttemptRejected("Ubuntu rejected the attempt; check the local registration and attempt logs")
    if len(process.stdout) > 128_000:
        raise RuntimeError("Ubuntu attempt response is too large")
    try:
        model = PreparedAttempt if action == "prepare" else QueuedAttempt
        result = model.model_validate_json(process.stdout)
        if result.attempt != attempt or (action == "launch" and
                                        (result.plan_hash != approved_hash or result.state != "queued")):
            raise ValueError("Mismatched attempt response")
        return result
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Ubuntu returned an invalid attempt record") from exc


def read_attempt(distro: str | None, root: str | None, registration_script: str | None,
                 attempt: str, action: str, execution_mode: str = "wsl"
                 ) -> PreparedAttempt | AttemptStatus | AttemptDiagnosis:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", attempt):
        raise ValueError("Invalid attempt name")
    if action not in {"plan", "status", "diagnose"}:
        raise ValueError("Invalid read action")
    if execution_mode not in {"wsl", "native"}:
        raise RuntimeError("Attempt execution mode is invalid")
    if not all((root, registration_script)):
        raise RuntimeError("Attempt bridge is not configured")
    if execution_mode == "wsl" and (
        not distro or not re.fullmatch(r"[A-Za-z0-9_-]+", distro)
    ):
        raise RuntimeError("Ubuntu bridge is not configured")

    root_path = PurePosixPath(root)
    script_path = PurePosixPath(registration_script)
    if any(not path.is_absolute() or ".." in path.parts for path in (root_path, script_path)):
        raise RuntimeError("Attempt bridge paths are invalid")

    python = str(root_path / ".venv/bin/python")
    reader = str(script_path.with_name("inspect_character_attempt.py"))
    prefix = (
        ["wsl.exe", "-d", distro, "--exec", python]
        if execution_mode == "wsl"
        else [python]
    )
    command = [
        *prefix,
        reader,
        "--umr-root", root,
        "--attempt", attempt,
        "--action", action,
    ]
    try:
        process = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, timeout=120 if action == "diagnose" else 15,
                                 check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Ubuntu inspection could not finish") from exc
    if process.returncode != 0 or len(process.stdout) > 128_000:
        raise RuntimeError("Ubuntu inspection failed; inspect the local attempt")
    try:
        data = json.loads(process.stdout)
        model = {"plan": PreparedAttempt, "status": AttemptStatus,
                 "diagnose": AttemptDiagnosis}[action]
        result = model.model_validate(data)
        if result.attempt != attempt or not re.fullmatch(r"[0-9a-f]{64}", result.plan_hash):
            raise ValueError("Mismatched attempt response")
        return result
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("Ubuntu returned an invalid attempt report") from exc
