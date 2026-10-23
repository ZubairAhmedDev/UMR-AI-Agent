from pathlib import Path

import pytest

from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    read_workflow,
    write_workflow,
)


def make_workflow(state="prepared"):
    return MotionWorkflow(
        workflow_id="spin-workflow-1",
        baseline_attempt="spin-main",
        candidate_attempt="spin-main-gc",
        baseline_plan_hash="a" * 64,
        candidate_plan_hash="b" * 64,
        state=state,
    )


def test_workflow_round_trip(tmp_path: Path):
    workflow = make_workflow()

    write_workflow(tmp_path, workflow)

    restored = read_workflow(
        tmp_path,
        "spin-workflow-1",
    )

    assert restored == workflow


def test_workflow_can_store_completed_winner(tmp_path: Path):
    workflow = MotionWorkflow(
        workflow_id="spin-workflow-1",
        baseline_attempt="spin-main",
        candidate_attempt="spin-main-gc",
        baseline_plan_hash="a" * 64,
        candidate_plan_hash="b" * 64,
        state="completed",
        winner="candidate",
        winner_attempt="spin-main-gc",
    )

    write_workflow(tmp_path, workflow)

    restored = read_workflow(
        tmp_path,
        "spin-workflow-1",
    )

    assert restored.state == "completed"
    assert restored.winner == "candidate"
    assert restored.winner_attempt == "spin-main-gc"


def test_invalid_state_is_rejected(tmp_path: Path):
    workflow = make_workflow(
        state="something-invalid",
    )

    with pytest.raises(
        ValueError,
        match="Invalid workflow state",
    ):
        write_workflow(
            tmp_path,
            workflow,
        )
