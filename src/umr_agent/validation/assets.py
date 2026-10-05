from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from umr_agent.domain.models import MotionSpec, PipelineSpec, RobotSpec, SourceType


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: Severity
    message: str
    evidence: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


def confine_path(root: Path, logical_path: str) -> Path:
    resolved_root = root.resolve(strict=False)
    candidate = (resolved_root / logical_path).resolve(strict=False)
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError(f"path escapes configured root: {logical_path}")
    return candidate


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _file_findings(path: Path, expected_sha256: str, expected_suffixes: set[str]) -> list[Finding]:
    if not path.exists():
        return [
            Finding(
                code="file_missing",
                severity=Severity.BLOCKING,
                message="Required asset does not exist.",
                evidence={"path": str(path)},
            )
        ]
    if not path.is_file():
        return [
            Finding(
                code="not_a_file",
                severity=Severity.BLOCKING,
                message="Asset path is not a regular file.",
                evidence={"path": str(path)},
            )
        ]

    findings: list[Finding] = []
    if path.suffix.lower() not in expected_suffixes:
        findings.append(
            Finding(
                code="unsupported_extension",
                severity=Severity.BLOCKING,
                message="Asset extension is not allowed for this asset type.",
                evidence={"path": str(path), "suffix": path.suffix.lower()},
            )
        )
    observed = sha256_file(path)
    if observed != expected_sha256:
        findings.append(
            Finding(
                code="checksum_mismatch",
                severity=Severity.BLOCKING,
                message="Asset bytes do not match the registered checksum.",
                evidence={"path": str(path), "expected": expected_sha256, "observed": observed},
            )
        )
    return findings


def inline_tpose_sha256(value: object) -> str:
    """Hash the JSON pose values, independent of object key or whitespace order."""
    if isinstance(value, dict):
        entries = value.items()
        if not value or any(not isinstance(key, str) or not key for key in value):
            raise ValueError("embedded T-pose must contain named joints")
        values = [item for _, item in entries]
    elif isinstance(value, list) and value:
        values = value
    else:
        raise ValueError("embedded T-pose must be a nonempty joint mapping or list")
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
           or (isinstance(item, float) and not math.isfinite(item)) for item in values):
        raise ValueError("embedded T-pose joint values must be finite numbers")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _inline_tpose_findings(
    robot: RobotSpec, project_root: Path, pipeline: PipelineSpec
) -> list[Finding]:
    try:
        config_path = confine_path(project_root, pipeline.robot_config_path)
    except ValueError as exc:
        return [Finding("path_escape", Severity.BLOCKING, str(exc), {})]
    if pipeline.robot_config_sha256 is None:
        return [Finding("missing_robot_config", Severity.BLOCKING,
                        "Inline T-pose needs a registered robot configuration.", {})]
    findings = _file_findings(config_path, pipeline.robot_config_sha256, {".json"})
    if findings:
        return findings
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            config = json.load(stream)
        config_robot = config["robot"]
        configured_xml = config_robot["xml"]
        if not isinstance(configured_xml, str) or not configured_xml:
            raise ValueError("robot.xml must be a project-relative path")
        if confine_path(project_root, configured_xml) != confine_path(
            project_root, robot.mjcf_path
        ):
            raise ValueError("robot.xml does not match the selected MJCF")
        pose = config_robot["tpose_qpos"]
        observed = inline_tpose_sha256(pose)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [Finding("invalid_inline_tpose", Severity.BLOCKING, str(exc), {})]
    if observed != robot.tpose_sha256:
        return [Finding("tpose_checksum_mismatch", Severity.BLOCKING,
                        "Embedded T-pose does not match the registered checksum.",
                        {"expected": robot.tpose_sha256, "observed": observed})]
    return []


def validate_robot_asset(
    robot: RobotSpec, project_root: Path, pipeline: PipelineSpec | None = None
) -> list[Finding]:
    try:
        mjcf = confine_path(project_root, robot.mjcf_path)
        tpose = (confine_path(project_root, robot.tpose_qpos_path)
                 if robot.tpose_qpos_path is not None else None)
    except ValueError as exc:
        return [
            Finding(
                code="path_escape",
                severity=Severity.BLOCKING,
                message=str(exc),
                evidence={},
            )
        ]
    findings = _file_findings(mjcf, robot.asset_sha256, {".xml"})
    if tpose is not None:
        return findings + _file_findings(
            tpose, robot.tpose_sha256, {".npy", ".npz", ".json"}
        )
    if pipeline is None or pipeline.robot_config_sha256 is None:
        return findings + [Finding("missing_robot_config", Severity.BLOCKING,
                                   "Inline T-pose needs a registered robot configuration.", {})]
    return findings + _inline_tpose_findings(robot, project_root, pipeline)


def validate_motion_asset(motion: MotionSpec, project_root: Path) -> list[Finding]:
    try:
        path = confine_path(project_root, motion.path)
    except ValueError as exc:
        return [
            Finding(
                code="path_escape",
                severity=Severity.BLOCKING,
                message=str(exc),
                evidence={},
            )
        ]
    suffixes = {".npz", ".fbx", ".bvh"}
    if motion.source_type == SourceType.HUMANOID_CHARACTER:
        suffixes.add(".pkl")
    return _file_findings(path, motion.sha256, suffixes)
