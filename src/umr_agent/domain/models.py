from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceType(StrEnum):
    SMPLX = "smplx"
    HUMANOID_CHARACTER = "humanoid_character"
    BONES_SEED_SOMA = "bones_seed_soma"
    OMNICONTACT = "omnicontact"
    FBX = "fbx"
    BVH = "bvh"
    ADAPT = "adapt"


class CachePolicy(StrEnum):
    REUSE_IF_EXACT = "reuse_if_exact"
    FORCE_REBUILD = "force_rebuild"
    DISABLED = "disabled"


def _validate_sha256(value: str) -> str:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
        raise ValueError("must be a 64-character hexadecimal SHA-256 value")
    return value.lower()


def _validate_logical_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("must be a project-relative logical path without '..'")
    return str(path)


class RobotSpec(StrictModel):
    robot_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    mjcf_path: str
    root_body: str = Field(min_length=1, max_length=200)
    tpose_qpos_path: str | None
    asset_sha256: str
    tpose_sha256: str

    _mjcf_path = field_validator("mjcf_path")(_validate_logical_path)
    @field_validator("tpose_qpos_path")
    @classmethod
    def validate_tpose_path(cls, value: str | None) -> str | None:
        return _validate_logical_path(value) if value is not None else None
    _asset_hash = field_validator("asset_sha256")(_validate_sha256)
    _tpose_hash = field_validator("tpose_sha256")(_validate_sha256)


class MotionSpec(StrictModel):
    motion_id: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    path: str
    sha256: str
    sequence_key: str | None = Field(default=None, max_length=200)
    frames: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0, le=1000)
    template_id: str = Field(min_length=1, max_length=200)

    _path = field_validator("path")(_validate_logical_path)
    _hash = field_validator("sha256")(_validate_sha256)


class PipelineSpec(StrictModel):
    entrypoint: str = "scripts/humanoid_retarget_pipeline.py"
    robot_config_path: str
    robot_config_sha256: str | None = None
    defaults_path: str | None = None

    _entrypoint_path = field_validator("entrypoint")(_validate_logical_path)
    _config_path = field_validator("robot_config_path")(_validate_logical_path)

    @field_validator("robot_config_sha256")
    @classmethod
    def validate_config_hash(cls, value: str | None) -> str | None:
        return _validate_sha256(value) if value is not None else None

    @field_validator("defaults_path")
    @classmethod
    def validate_defaults_path(cls, value: str | None) -> str | None:
        return _validate_logical_path(value) if value is not None else None


class ResourceLimits(StrictModel):
    cpus: int = Field(default=8, ge=1, le=128)
    memory_gib: int = Field(default=24, ge=1, le=1024)
    gpu_ids: tuple[int, ...] = (0,)
    timeout_seconds: int = Field(default=14_400, ge=60, le=86_400)

    @field_validator("gpu_ids")
    @classmethod
    def validate_gpu_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item < 0 for item in value):
            raise ValueError("GPU identifiers must be non-negative")
        if len(set(value)) != len(value):
            raise ValueError("GPU identifiers must be unique")
        return value


class ExecutionPlan(StrictModel):
    schema_version: str = "1.0"
    plan_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    robot: RobotSpec
    motion: MotionSpec
    pipeline: PipelineSpec
    resources: ResourceLimits = ResourceLimits()
    cache_policy: CachePolicy = CachePolicy.REUSE_IF_EXACT
    requested_outputs: tuple[str, ...] = (
        "robot_motion_npz",
        "manifest",
        "quality_report",
        "logs",
    )
    umr_git_commit: str = Field(min_length=40, max_length=64)
    correspondence_settings_sha256: str
    created_by: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    plan_hash: str | None = None

    _correspondence_hash = field_validator("correspondence_settings_sha256")(
        _validate_sha256
    )

    @field_validator("umr_git_commit")
    @classmethod
    def validate_commit(cls, value: str) -> str:
        if any(ch not in "0123456789abcdef" for ch in value.lower()):
            raise ValueError("UMR Git commit must be hexadecimal")
        return value.lower()

    @field_validator("requested_outputs")
    @classmethod
    def validate_outputs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {"robot_motion_npz", "manifest", "quality_report", "logs"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unsupported outputs: {sorted(unknown)}")
        if len(set(value)) != len(value):
            raise ValueError("requested outputs must be unique")
        return value

    @model_validator(mode="after")
    def validate_plan_hash(self) -> ExecutionPlan:
        if self.robot.tpose_qpos_path is None and self.pipeline.robot_config_sha256 is None:
            raise ValueError("inline T-pose requires a registered robot config SHA-256")
        if self.plan_hash is not None and self.plan_hash != self.compute_hash():
            raise ValueError("plan_hash does not match the canonical plan content")
        return self

    def compute_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"plan_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def sealed(self) -> ExecutionPlan:
        return self.model_copy(update={"plan_hash": self.compute_hash()})


class Approval(StrictModel):
    approval_id: str = Field(min_length=1, max_length=100)
    plan_id: str = Field(min_length=1, max_length=100)
    plan_hash: str
    actor: str = Field(min_length=1, max_length=200)
    approved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime

    _plan_hash = field_validator("plan_hash")(_validate_sha256)

    @model_validator(mode="after")
    def validate_expiry(self) -> Approval:
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expiry must be after approval time")
        return self

    def authorizes(self, plan: ExecutionPlan, at: datetime | None = None) -> bool:
        now = at or datetime.now(UTC)
        return (
            plan.plan_hash is not None
            and self.plan_id == plan.plan_id
            and self.plan_hash == plan.plan_hash
            and now < self.expires_at
        )


class ArtifactRecord(StrictModel):
    artifact_type: str = Field(min_length=1, max_length=100)
    logical_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=200)

    _path = field_validator("logical_path")(_validate_logical_path)
    _hash = field_validator("sha256")(_validate_sha256)
