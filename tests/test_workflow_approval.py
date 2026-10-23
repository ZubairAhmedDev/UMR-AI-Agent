from pathlib import Path

import pytest

from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    queue_workflow,
    read_workflow,
    workflow_approval_hash,
    write_workflow,
)


def make_workflow(
    *,
    baseline_hash="a" * 64,
    candidate_hash="b" * 64,
):
    return MotionWorkflow(
        workflow_id="spin-flow-1",
        baseline_attempt="spin-flow-1",
        candidate_attempt="spin-flow-1-gc",
        baseline_plan_hash=baseline_hash,
        candidate_plan_hash=candidate_hash,
        state="prepared",
    )


def test_workflow_approval_hash_is_deterministic():
    workflow = make_workflow()

    first = workflow_approval_hash(workflow)
    second = workflow_approval_hash(workflow)

    assert first == second
    assert len(first) == 64


def test_changing_candidate_plan_changes_approval_hash():
    first = make_workflow(
        candidate_hash="b" * 64,
    )

    second = make_workflow(
        candidate_hash="c" * 64,
    )

    assert (
        workflow_approval_hash(first)
        != workflow_approval_hash(second)
    )


def test_wrong_approval_does_not_queue_workflow(tmp_path: Path):
    workflow = make_workflow()
    write_workflow(tmp_path, workflow)

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        queue_workflow(
            tmp_path,
            workflow.workflow_id,
            "c" * 64,
        )

    restored = read_workflow(
        tmp_path,
        workflow.workflow_id,
    )

    assert restored.state == "prepared"


def test_exact_approval_queues_workflow(tmp_path: Path):
    workflow = make_workflow()
    write_workflow(tmp_path, workflow)

    approved_hash = workflow_approval_hash(workflow)

    result = queue_workflow(
        tmp_path,
        workflow.workflow_id,
        approved_hash,
    )

    assert result.state == "queued"

    restored = read_workflow(
        tmp_path,
        workflow.workflow_id,
    )

    assert restored.state == "queued"


def test_repeated_exact_approval_is_idempotent(tmp_path: Path):
    workflow = make_workflow()
    write_workflow(tmp_path, workflow)

    approved_hash = workflow_approval_hash(workflow)

    first = queue_workflow(
        tmp_path,
        workflow.workflow_id,
        approved_hash,
    )

    second = queue_workflow(
        tmp_path,
        workflow.workflow_id,
        approved_hash,
    )

    assert first.state == "queued"
    assert second.state == "queued"
