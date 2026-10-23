from pathlib import Path
from types import SimpleNamespace

from umr_agent.agent.workflow_runner import advance_workflow
from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    read_workflow,
    write_workflow,
)


BASELINE_HASH = "a" * 64
CANDIDATE_HASH = "b" * 64


def workflow(state: str) -> MotionWorkflow:
    return MotionWorkflow(
        workflow_id="spin-flow-1",
        baseline_attempt="spin-main",
        candidate_attempt="spin-main-gc",
        baseline_plan_hash=BASELINE_HASH,
        candidate_plan_hash=CANDIDATE_HASH,
        state=state,
    )


def test_prepared_workflow_does_not_execute(tmp_path: Path):
    write_workflow(tmp_path, workflow("prepared"))

    launches = []

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        lambda *_: None,
        lambda **kwargs: launches.append(kwargs),
        lambda *_: None,
    )

    assert result.state == "prepared"
    assert launches == []


def test_queued_workflow_launches_baseline(tmp_path: Path):
    write_workflow(tmp_path, workflow("queued"))

    launches = []

    def reader(attempt, action):
        assert attempt == "spin-main"
        assert action == "status"
        return SimpleNamespace(
            state="prepared",
            plan_hash=BASELINE_HASH,
        )

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        reader,
        lambda **kwargs: launches.append(kwargs),
        lambda *_: None,
    )

    assert result.state == "running_baseline"

    assert launches == [
        {
            "action": "launch",
            "attempt": "spin-main",
            "approved_hash": BASELINE_HASH,
        }
    ]


def test_completed_baseline_moves_to_candidate(tmp_path: Path):
    write_workflow(
        tmp_path,
        workflow("running_baseline"),
    )

    def reader(attempt, action):
        return SimpleNamespace(
            state="completed",
            plan_hash=BASELINE_HASH,
        )

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        reader,
        lambda **kwargs: None,
        lambda *_: None,
    )

    assert result.state == "running_candidate"


def test_candidate_is_launched(tmp_path: Path):
    write_workflow(
        tmp_path,
        workflow("running_candidate"),
    )

    launches = []

    def reader(attempt, action):
        assert attempt == "spin-main-gc"
        return SimpleNamespace(
            state="prepared",
            plan_hash=CANDIDATE_HASH,
        )

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        reader,
        lambda **kwargs: launches.append(kwargs),
        lambda *_: None,
    )

    assert result.state == "running_candidate"

    assert launches == [
        {
            "action": "launch",
            "attempt": "spin-main-gc",
            "approved_hash": CANDIDATE_HASH,
        }
    ]


def test_completed_candidate_moves_to_evaluation(tmp_path: Path):
    write_workflow(
        tmp_path,
        workflow("running_candidate"),
    )

    def reader(attempt, action):
        return SimpleNamespace(
            state="completed",
            plan_hash=CANDIDATE_HASH,
        )

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        reader,
        lambda **kwargs: None,
        lambda *_: None,
    )

    assert result.state == "evaluating"


def test_evaluation_saves_candidate_winner(tmp_path: Path):
    write_workflow(
        tmp_path,
        workflow("evaluating"),
    )

    def evaluator(baseline_attempt):
        assert baseline_attempt == "spin-main"

        return SimpleNamespace(
            winner="candidate",
            winner_attempt="spin-main-gc",
        )

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        lambda *_: None,
        lambda **kwargs: None,
        evaluator,
    )

    assert result.state == "rendering_preview"
    assert result.winner == "candidate"
    assert result.winner_attempt == "spin-main-gc"

    restored = read_workflow(
        tmp_path,
        "spin-flow-1",
    )

    assert restored.state == "rendering_preview"
    assert restored.winner == "candidate"


def test_failed_baseline_fails_workflow(tmp_path: Path):
    write_workflow(
        tmp_path,
        workflow("running_baseline"),
    )

    def reader(attempt, action):
        return SimpleNamespace(
            state="failed",
            plan_hash=BASELINE_HASH,
        )

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        reader,
        lambda **kwargs: None,
        lambda *_: None,
    )

    assert result.state == "failed"
    assert "Baseline attempt ended" in result.error


def test_hash_mismatch_fails_workflow(tmp_path: Path):
    write_workflow(
        tmp_path,
        workflow("running_baseline"),
    )

    def reader(attempt, action):
        return SimpleNamespace(
            state="running",
            plan_hash="c" * 64,
        )

    result = advance_workflow(
        tmp_path,
        "spin-flow-1",
        reader,
        lambda **kwargs: None,
        lambda *_: None,
    )

    assert result.state == "failed"
    assert "approved workflow plan" in result.error
