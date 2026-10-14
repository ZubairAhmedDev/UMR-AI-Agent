from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from umr_agent.domain.models import ArtifactRecord, ExecutionPlan, StrictModel
from umr_agent.validation.assets import confine_path, sha256_file


class ResultManifest(StrictModel):
    schema_version: str = "1.0"
    attempt_id: str = Field(min_length=1, max_length=100)
    plan_id: str = Field(min_length=1, max_length=100)
    plan_hash: str = Field(min_length=64, max_length=64)
    umr_git_commit: str = Field(min_length=40, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    artifacts: tuple[ArtifactRecord, ...]


def build_manifest(
    *,
    attempt_id: str,
    plan: ExecutionPlan,
    output_root: Path,
    artifacts: list[tuple[str, str, str]],
) -> ResultManifest:
    if plan.plan_hash is None or plan.plan_hash != plan.compute_hash():
        raise ValueError("cannot create a manifest for an unsealed plan")

    records: list[ArtifactRecord] = []
    for artifact_type, logical_path, media_type in artifacts:
        path = confine_path(output_root, logical_path)
        if not path.is_file():
            raise ValueError(f"declared artifact is not a file: {logical_path}")
        records.append(
            ArtifactRecord(
                artifact_type=artifact_type,
                logical_path=logical_path,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                media_type=media_type,
            )
        )

    return ResultManifest(
        attempt_id=attempt_id,
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        umr_git_commit=plan.umr_git_commit,
        artifacts=tuple(records),
    )


def verify_manifest(manifest: ResultManifest, output_root: Path) -> list[str]:
    errors: list[str] = []
    for artifact in manifest.artifacts:
        try:
            path = confine_path(output_root, artifact.logical_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"missing artifact: {artifact.logical_path}")
            continue
        if path.stat().st_size != artifact.size_bytes:
            errors.append(f"size mismatch: {artifact.logical_path}")
        if sha256_file(path) != artifact.sha256:
            errors.append(f"checksum mismatch: {artifact.logical_path}")
    return errors

