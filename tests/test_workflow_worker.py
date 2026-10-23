from pathlib import Path
from types import SimpleNamespace

from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    read_workflow,
    write_workflow,
)
from umr_agent.agent.workflow_worker import (
    run_worker_pass,
    workflow_ids,
)


BASELINE_HASH = "a" * 64
CANDIDATE_HASH = "b" * 64


def make_workflow(
    workflow_id: str,
    state: str,
) -> MotionWorkflow:
    return MotionWorkflow(
        workflow_id=workflow_id,
        baseline_attempt=workflow_id,
        candidate_attempt=f"{workflow_id}-gc",
        baseline_plan_hash=BASELINE_HASH,
        candidate_plan_hash=CANDIDATE_HASH,
        state=state,
    )


def test_no_workflow_directory_returns_empty(tmp_path: Path):
    assert workflow_ids(tmp_path) == []


def test_worker_skips_inactive_workflows(tmp_path: Path):
    write_workflow(
        tmp_path,
        make_workflow(
            "prepared-flow",
            "prepared",
        ),
    )

    write_workflow(
        tmp_path,
        make_workflow(
            "completed-flow",
            "completed",
        ),
    )

    results, errors = run_worker_pass(
        tmp_path,
        lambda *_: None,
        lambda **kwargs: None,
        lambda *_: None,
    )

    assert results == []
    assert errors == []


def test_worker_advances_queued_workflow(tmp_path: Path):
    write_workflow(
        tmp_path,
        make_workflow(
            "spin-flow",
            "queued",
        ),
    )

    launches = []

    def reader(attempt, action):
        return SimpleNamespace(
            state="prepared",
            plan_hash=BASELINE_HASH,
        )

    results, errors = run_worker_pass(
        tmp_path,
        reader,
        lambda **kwargs: launches.append(kwargs),
        lambda *_: None,
    )

    assert errors == []
    assert len(results) == 1
    assert results[0].state == "running_baseline"

    assert launches == [
        {
            "action": "launch",
            "attempt": "spin-flow",
            "approved_hash": BASELINE_HASH,
        }
    ]

    restored = read_workflow(
        tmp_path,
        "spin-flow",
    )

    assert restored.state == "running_baseline"


def test_bad_workflow_does_not_block_good_workflow(tmp_path: Path):
    base = (
        tmp_path
        / "output"
        / "agent_workflows"
    )
    base.mkdir(parents=True)

    (base / "bad-flow.json").write_text(
        "{broken-json",
        encoding="utf-8",
    )

    write_workflow(
        tmp_path,
        make_workflow(
            "good-flow",
            "queued",
        ),
    )

    def reader(attempt, action):
        return SimpleNamespace(
            state="prepared",
            plan_hash=BASELINE_HASH,
        )

    results, errors = run_worker_pass(
        tmp_path,
        reader,
        lambda **kwargs: None,
        lambda *_: None,
    )

    assert len(results) == 1
    assert results[0].state == "running_baseline"

    assert len(errors) == 1
    assert "bad-flow" in errors[0]
