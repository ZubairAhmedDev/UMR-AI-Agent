"""Prepare both exact plans for one persistent motion workflow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from umr_agent.agent.improvement_service import improvement_attempt_name
from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    workflow_path,
    write_workflow,
)


SUPPORTED_MOTIONS = {
    "spin-kick",
    "run",
    "speed-vault",
}


def _validate_prepared_plan(
    plan: object,
    *,
    expected_attempt: str,
    expected_motion: str,
    expected_profile: str,
) -> None:
    if getattr(plan, "attempt", None) != expected_attempt:
        raise ValueError("Prepared attempt name does not match workflow")

    if getattr(plan, "motion_id", None) != expected_motion:
        raise ValueError("Prepared motion does not match workflow")

    if getattr(plan, "max_frames", None) != 0:
        raise ValueError("Workflow requires the full motion")

    if getattr(plan, "profile", None) != expected_profile:
        raise ValueError("Prepared profile does not match workflow")

    plan_hash = getattr(plan, "plan_hash", None)

    if not isinstance(plan_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}",
        plan_hash,
    ):
        raise ValueError("Prepared plan has an invalid hash")


def prepare_motion_workflow(
    root: Path,
    workflow_id: str,
    motion_id: str,
    writer: Callable,
) -> MotionWorkflow:
    """Prepare exact baseline and candidate plans without executing either."""

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,77}", workflow_id):
        raise ValueError("Invalid workflow ID")

    if motion_id not in SUPPORTED_MOTIONS:
        raise ValueError("Unsupported motion")

    if workflow_path(root, workflow_id).exists():
        raise ValueError("Workflow already exists")

    baseline_attempt = workflow_id
    candidate_attempt = improvement_attempt_name(
        baseline_attempt
    )

    baseline = writer(
        action="prepare",
        attempt=baseline_attempt,
        motion_id=motion_id,
        max_frames=0,
        profile="baseline",
    )

    _validate_prepared_plan(
        baseline,
        expected_attempt=baseline_attempt,
        expected_motion=motion_id,
        expected_profile="baseline",
    )

    candidate = writer(
        action="prepare",
        attempt=candidate_attempt,
        motion_id=motion_id,
        max_frames=0,
        profile="ground-contact",
    )

    _validate_prepared_plan(
        candidate,
        expected_attempt=candidate_attempt,
        expected_motion=motion_id,
        expected_profile="ground-contact",
    )

    workflow = MotionWorkflow(
        workflow_id=workflow_id,
        baseline_attempt=baseline_attempt,
        candidate_attempt=candidate_attempt,
        baseline_plan_hash=baseline.plan_hash,
        candidate_plan_hash=candidate.plan_hash,
        state="prepared",
    )

    write_workflow(
        root,
        workflow,
    )

    return workflow
