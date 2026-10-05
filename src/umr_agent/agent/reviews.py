"""Exact, read-only input snapshot for the tested G1 example."""

import hashlib
import json

from pydantic import Field, model_validator

from umr_agent.api.wsl_assets import EXPECTED_CONFIG, EXPECTED_MOTION, EXPECTED_XML, EXPECTED_SLOTS, AssetStatus
from umr_agent.domain.models import StrictModel


class ReviewRequest(StrictModel):
    robot_id: str = Field(min_length=1, max_length=100)
    motion_id: str = Field(min_length=1, max_length=100)
    correspondence_workers: int = Field(ge=1, le=12)


class InputReview(StrictModel):
    robot_id: str
    motion_id: str
    source_type: str = "humanoid_character"
    robot_config: str = EXPECTED_CONFIG
    robot_xml: str = EXPECTED_XML
    motion: str = EXPECTED_MOTION
    correspondence_slots: str = EXPECTED_SLOTS
    robot_config_sha256: str
    robot_xml_sha256: str
    motion_sha256: str
    correspondence_slots_sha256: str
    manifest_sha256: str
    umr_git_commit: str
    file_count: int
    correspondence_workers: int
    executable: bool = False
    review_hash: str | None = None

    @model_validator(mode="after")
    def validate_hash(self) -> "InputReview":
        if self.review_hash is not None and self.review_hash != self.compute_hash():
            raise ValueError("review hash does not match the verified input snapshot")
        return self

    def compute_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"review_hash"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_input_review(request: ReviewRequest, status: AssetStatus) -> InputReview:
    if request.robot_id != "unitree-g1" or request.motion_id != "humanoid-spin-kick":
        raise ValueError("only the verified G1 spin kick example can be reviewed")
    if status.state != "verified" or any(value is None for value in (
        status.robot_config_sha256, status.robot_xml_sha256, status.motion_sha256,
        status.correspondence_slots_sha256,
        status.manifest_sha256, status.umr_git_commit, status.file_count,
    )):
        raise ValueError("Ubuntu inputs must pass a fresh verification")
    review = InputReview(
        robot_id=request.robot_id, motion_id=request.motion_id,
        robot_config_sha256=status.robot_config_sha256,
        robot_xml_sha256=status.robot_xml_sha256,
        motion_sha256=status.motion_sha256,
        correspondence_slots_sha256=status.correspondence_slots_sha256,
        manifest_sha256=status.manifest_sha256,
        umr_git_commit=status.umr_git_commit, file_count=status.file_count,
        correspondence_workers=request.correspondence_workers,
    )
    return review.model_copy(update={"review_hash": review.compute_hash()})
