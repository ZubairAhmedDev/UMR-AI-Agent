"""Advance a persistent UMR baseline + improvement workflow."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    read_workflow,
    write_workflow,
)


ACTIVE_ATTEMPT_STATES = {"queued", "running"}
FAILED_ATTEMPT_STATES = {
    "failed",
    "failed_launch",
    "failed_verification",
}


def _save(root: Path, workflow: MotionWorkflow) -> MotionWorkflow:
    write_workflow(root, workflow)
    return workflow


def _verify_plan_hash(status: object, expected: str, label: str) -> None:
    if getattr(status, "plan_hash", None) != expected:
        raise ValueError(f"{label} attempt does not match the approved workflow plan")


def _fail(
    root: Path,
    workflow: MotionWorkflow,
    message: str,
) -> MotionWorkflow:
    return _save(
        root,
        replace(
            workflow,
            state="failed",
            error=message,
        ),
    )


def advance_workflow(
    root: Path,
    workflow_id: str,
    reader: Callable,
    launcher: Callable,
    evaluator: Callable,
    renderer: Callable | None = None,
) -> MotionWorkflow:
    """Advance one workflow by at most one durable stage."""

    workflow = read_workflow(root, workflow_id)

    if workflow.state in {"completed", "failed"}:
        return workflow

    # Prepared means plans exist, but the user has not approved execution.
    if workflow.state == "prepared":
        return workflow

    try:
        if workflow.state == "queued":
            status = reader(
                workflow.baseline_attempt,
                "status",
            )

            _verify_plan_hash(
                status,
                workflow.baseline_plan_hash,
                "Baseline",
            )

            if status.state == "prepared":
                launcher(
                    action="launch",
                    attempt=workflow.baseline_attempt,
                    approved_hash=workflow.baseline_plan_hash,
                )

                return _save(
                    root,
                    replace(
                        workflow,
                        state="running_baseline",
                    ),
                )

            if status.state in ACTIVE_ATTEMPT_STATES:
                return _save(
                    root,
                    replace(
                        workflow,
                        state="running_baseline",
                    ),
                )

            if status.state == "completed":
                return _save(
                    root,
                    replace(
                        workflow,
                        state="running_candidate",
                    ),
                )

            if status.state in FAILED_ATTEMPT_STATES:
                return _fail(
                    root,
                    workflow,
                    f"Baseline attempt ended in state {status.state}.",
                )

            raise ValueError(
                f"Unsupported baseline state: {status.state}"
            )

        if workflow.state == "running_baseline":
            status = reader(
                workflow.baseline_attempt,
                "status",
            )

            _verify_plan_hash(
                status,
                workflow.baseline_plan_hash,
                "Baseline",
            )

            # Recovery case:
            # the workflow state may have been saved just before
            # the launch completed.
            if status.state == "prepared":
                launcher(
                    action="launch",
                    attempt=workflow.baseline_attempt,
                    approved_hash=workflow.baseline_plan_hash,
                )

                return workflow

            if status.state in ACTIVE_ATTEMPT_STATES:
                return workflow

            if status.state == "completed":
                return _save(
                    root,
                    replace(
                        workflow,
                        state="running_candidate",
                    ),
                )

            if status.state in FAILED_ATTEMPT_STATES:
                return _fail(
                    root,
                    workflow,
                    f"Baseline attempt ended in state {status.state}.",
                )

            raise ValueError(
                f"Unsupported baseline state: {status.state}"
            )

        if workflow.state == "running_candidate":
            status = reader(
                workflow.candidate_attempt,
                "status",
            )

            _verify_plan_hash(
                status,
                workflow.candidate_plan_hash,
                "Candidate",
            )

            if status.state == "prepared":
                launcher(
                    action="launch",
                    attempt=workflow.candidate_attempt,
                    approved_hash=workflow.candidate_plan_hash,
                )

                return workflow

            if status.state in ACTIVE_ATTEMPT_STATES:
                return workflow

            if status.state == "completed":
                return _save(
                    root,
                    replace(
                        workflow,
                        state="evaluating",
                    ),
                )

            if status.state in FAILED_ATTEMPT_STATES:
                return _fail(
                    root,
                    workflow,
                    f"Candidate attempt ended in state {status.state}.",
                )

            raise ValueError(
                f"Unsupported candidate state: {status.state}"
            )

        if workflow.state == "evaluating":
            result = evaluator(workflow.baseline_attempt)

            if result.winner not in {"baseline", "candidate"}:
                raise ValueError("Evaluation returned an invalid winner")

            expected_winner_attempt = (
                workflow.candidate_attempt
                if result.winner == "candidate"
                else workflow.baseline_attempt
            )

            if result.winner_attempt != expected_winner_attempt:
                raise ValueError(
                    "Evaluation winner does not match workflow attempts"
                )

            return _save(
                root,
                replace(
                    workflow,
                    state="rendering_preview",
                    winner=result.winner,
                    winner_attempt=result.winner_attempt,
                    error=None,
                ),
            )

        if workflow.state == "rendering_preview":
            if workflow.winner not in {"baseline", "candidate"}:
                raise ValueError(
                    "Workflow does not contain a valid winner"
                )

            expected_winner_attempt = (
                workflow.candidate_attempt
                if workflow.winner == "candidate"
                else workflow.baseline_attempt
            )

            if workflow.winner_attempt != expected_winner_attempt:
                raise ValueError(
                    "Workflow winner does not match workflow attempts"
                )

            if renderer is None:
                raise RuntimeError(
                    "Preview renderer is required"
                )

            renderer(workflow.winner_attempt)

            return _save(
                root,
                replace(
                    workflow,
                    state="completed",
                    error=None,
                ),
            )

        raise ValueError(
            f"Unsupported workflow state: {workflow.state}"
        )

    except (ValueError, RuntimeError) as exc:
        return _fail(
            root,
            workflow,
            str(exc),
        )
