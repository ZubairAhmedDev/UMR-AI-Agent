from types import SimpleNamespace

from umr_agent.agent.workflow_runner import advance_workflow
from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    read_workflow,
    write_workflow,
)


def make_workflow(state: str) -> MotionWorkflow:
    return MotionWorkflow(
        workflow_id="preview-test",
        baseline_attempt="preview-test",
        candidate_attempt="preview-test-gc",
        baseline_plan_hash="a" * 64,
        candidate_plan_hash="b" * 64,
        state=state,
    )


def unused_reader(*args, **kwargs):
    raise AssertionError("reader should not be called")


def unused_launcher(*args, **kwargs):
    raise AssertionError("launcher should not be called")


def evaluator(_baseline_attempt):
    return SimpleNamespace(
        winner="candidate",
        winner_attempt="preview-test-gc",
    )


def test_evaluation_saves_winner_before_rendering(tmp_path):
    write_workflow(
        tmp_path,
        make_workflow("evaluating"),
    )

    rendered = []

    workflow = advance_workflow(
        tmp_path,
        "preview-test",
        unused_reader,
        unused_launcher,
        evaluator,
        rendered.append,
    )

    assert workflow.state == "rendering_preview"
    assert workflow.winner == "candidate"
    assert workflow.winner_attempt == "preview-test-gc"
    assert rendered == []

    persisted = read_workflow(
        tmp_path,
        "preview-test",
    )

    assert persisted.state == "rendering_preview"
    assert persisted.winner_attempt == "preview-test-gc"


def test_rendering_preview_completes_workflow(tmp_path):
    workflow = make_workflow(
        "rendering_preview",
    )

    workflow = MotionWorkflow(
        **{
            **workflow.__dict__,
            "winner": "candidate",
            "winner_attempt": "preview-test-gc",
        }
    )

    write_workflow(
        tmp_path,
        workflow,
    )

    rendered = []

    result = advance_workflow(
        tmp_path,
        "preview-test",
        unused_reader,
        unused_launcher,
        evaluator,
        rendered.append,
    )

    assert rendered == ["preview-test-gc"]
    assert result.state == "completed"
    assert result.winner == "candidate"
    assert result.winner_attempt == "preview-test-gc"


def test_render_failure_fails_workflow(tmp_path):
    workflow = make_workflow(
        "rendering_preview",
    )

    workflow = MotionWorkflow(
        **{
            **workflow.__dict__,
            "winner": "candidate",
            "winner_attempt": "preview-test-gc",
        }
    )

    write_workflow(
        tmp_path,
        workflow,
    )

    def broken_renderer(_attempt):
        raise RuntimeError(
            "renderer test failure"
        )

    result = advance_workflow(
        tmp_path,
        "preview-test",
        unused_reader,
        unused_launcher,
        evaluator,
        broken_renderer,
    )

    assert result.state == "failed"
    assert result.error == "renderer test failure"
