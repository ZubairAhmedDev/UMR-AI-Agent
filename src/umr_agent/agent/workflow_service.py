"""Persistent state and approval for one baseline + improvement UMR workflow."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path


WORKFLOW_STATES = {
    "prepared",
    "queued",
    "running_baseline",
    "running_candidate",
    "evaluating",
    "rendering_preview",
    "completed",
    "failed",
}


@dataclass(frozen=True)
class MotionWorkflow:
    workflow_id: str
    baseline_attempt: str
    candidate_attempt: str
    baseline_plan_hash: str
    candidate_plan_hash: str
    state: str
    winner: str | None = None
    winner_attempt: str | None = None
    error: str | None = None


def workflow_path(root: Path, workflow_id: str) -> Path:
    if not workflow_id:
        raise ValueError("Workflow ID is required")

    base = root.resolve() / "output" / "agent_workflows"
    path = (base / f"{workflow_id}.json").resolve()

    if path.parent != base.resolve():
        raise ValueError("Workflow path escapes workflow directory")

    return path


def write_workflow(root: Path, workflow: MotionWorkflow) -> None:
    if workflow.state not in WORKFLOW_STATES:
        raise ValueError("Invalid workflow state")

    path = workflow_path(root, workflow.workflow_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".json.tmp")

    payload = {
        "workflow_id": workflow.workflow_id,
        "baseline_attempt": workflow.baseline_attempt,
        "candidate_attempt": workflow.candidate_attempt,
        "baseline_plan_hash": workflow.baseline_plan_hash,
        "candidate_plan_hash": workflow.candidate_plan_hash,
        "state": workflow.state,
        "winner": workflow.winner,
        "winner_attempt": workflow.winner_attempt,
        "error": workflow.error,
    }

    temporary.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_workflow(root: Path, workflow_id: str) -> MotionWorkflow:
    path = workflow_path(root, workflow_id)

    data = json.loads(path.read_text(encoding="utf-8"))

    workflow = MotionWorkflow(
        workflow_id=data["workflow_id"],
        baseline_attempt=data["baseline_attempt"],
        candidate_attempt=data["candidate_attempt"],
        baseline_plan_hash=data["baseline_plan_hash"],
        candidate_plan_hash=data["candidate_plan_hash"],
        state=data["state"],
        winner=data.get("winner"),
        winner_attempt=data.get("winner_attempt"),
        error=data.get("error"),
    )

    if workflow.workflow_id != workflow_id:
        raise ValueError("Workflow ID does not match workflow file")

    if workflow.state not in WORKFLOW_STATES:
        raise ValueError("Invalid workflow state")

    return workflow


def workflow_approval_hash(workflow: MotionWorkflow) -> str:
    """Bind one approval to both exact attempt plans."""

    for value in (
        workflow.baseline_plan_hash,
        workflow.candidate_plan_hash,
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Workflow contains an invalid plan hash")

    payload = {
        "schema_version": 1,
        "workflow_id": workflow.workflow_id,
        "baseline_attempt": workflow.baseline_attempt,
        "candidate_attempt": workflow.candidate_attempt,
        "baseline_plan_hash": workflow.baseline_plan_hash,
        "candidate_plan_hash": workflow.candidate_plan_hash,
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()


def queue_workflow(
    root: Path,
    workflow_id: str,
    approved_hash: str,
) -> MotionWorkflow:
    """Approve the exact workflow and move it into the execution queue."""

    if not re.fullmatch(r"[0-9a-f]{64}", approved_hash):
        raise ValueError("Approval must be a 64-character workflow hash")

    workflow = read_workflow(root, workflow_id)
    expected = workflow_approval_hash(workflow)

    if not hmac.compare_digest(approved_hash, expected):
        raise ValueError("Approval does not match the exact workflow")

    if workflow.state == "prepared":
        workflow = replace(
            workflow,
            state="queued",
        )
        write_workflow(root, workflow)
        return workflow

    # Network retries after a successful approval must not launch
    # another copy of the workflow.
    if workflow.state in {
        "queued",
        "running_baseline",
        "running_candidate",
        "evaluating",
        "rendering_preview",
        "completed",
    }:
        return workflow

    if workflow.state == "failed":
        raise ValueError("Failed workflow cannot be approved")

    raise ValueError("Workflow cannot be approved in its current state")
