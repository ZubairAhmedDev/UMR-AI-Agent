"""Process persistent UMR motion workflows one safe step at a time."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from umr_agent.agent.workflow_runner import advance_workflow
from umr_agent.agent.workflow_service import MotionWorkflow, read_workflow


ACTIVE_WORKFLOW_STATES = {
    "queued",
    "running_baseline",
    "running_candidate",
    "evaluating",
    "rendering_preview",
}


def workflow_ids(root: Path) -> list[str]:
    base = root.resolve() / "output" / "agent_workflows"

    if not base.exists():
        return []

    return [
        path.stem
        for path in sorted(base.glob("*.json"))
        if path.is_file()
    ]


def run_worker_pass(
    root: Path,
    reader: Callable,
    launcher: Callable,
    evaluator: Callable,
    renderer: Callable | None = None,
) -> tuple[list[MotionWorkflow], list[str]]:
    """Advance every active workflow by at most one durable stage."""

    results: list[MotionWorkflow] = []
    errors: list[str] = []

    for workflow_id in workflow_ids(root):
        try:
            workflow = read_workflow(
                root,
                workflow_id,
            )

            if workflow.state not in ACTIVE_WORKFLOW_STATES:
                continue

            result = advance_workflow(
                root,
                workflow_id,
                reader,
                launcher,
                evaluator,
                renderer,
            )

            results.append(result)

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            errors.append(
                f"{workflow_id}: {exc}"
            )

    return results, errors
