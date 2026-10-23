from pathlib import Path
from types import SimpleNamespace

import pytest

from umr_agent.agent.workflow_preparation import (
    prepare_motion_workflow,
)
from umr_agent.agent.workflow_service import read_workflow


def fake_plan(
    *,
    attempt,
    motion_id,
    profile,
    plan_hash,
):
    return SimpleNamespace(
        attempt=attempt,
        motion_id=motion_id,
        max_frames=0,
        profile=profile,
        plan_hash=plan_hash,
    )


def test_prepares_baseline_and_candidate(tmp_path: Path):
    calls = []

    def writer(**kwargs):
        calls.append(kwargs)

        return fake_plan(
            attempt=kwargs["attempt"],
            motion_id=kwargs["motion_id"],
            profile=kwargs["profile"],
            plan_hash=(
                "a" * 64
                if kwargs["profile"] == "baseline"
                else "b" * 64
            ),
        )

    result = prepare_motion_workflow(
        tmp_path,
        "spin-flow-1",
        "spin-kick",
        writer,
    )

    assert result.state == "prepared"
    assert result.baseline_attempt == "spin-flow-1"
    assert result.candidate_attempt == "spin-flow-1-gc"
    assert result.baseline_plan_hash == "a" * 64
    assert result.candidate_plan_hash == "b" * 64

    assert calls == [
        {
            "action": "prepare",
            "attempt": "spin-flow-1",
            "motion_id": "spin-kick",
            "max_frames": 0,
            "profile": "baseline",
        },
        {
            "action": "prepare",
            "attempt": "spin-flow-1-gc",
            "motion_id": "spin-kick",
            "max_frames": 0,
            "profile": "ground-contact",
        },
    ]


def test_prepared_workflow_is_persisted(tmp_path: Path):
    def writer(**kwargs):
        return fake_plan(
            attempt=kwargs["attempt"],
            motion_id=kwargs["motion_id"],
            profile=kwargs["profile"],
            plan_hash=(
                "a" * 64
                if kwargs["profile"] == "baseline"
                else "b" * 64
            ),
        )

    prepare_motion_workflow(
        tmp_path,
        "spin-flow-1",
        "spin-kick",
        writer,
    )

    restored = read_workflow(
        tmp_path,
        "spin-flow-1",
    )

    assert restored.state == "prepared"
    assert restored.baseline_attempt == "spin-flow-1"
    assert restored.candidate_attempt == "spin-flow-1-gc"


def test_invalid_motion_is_rejected_before_prepare(tmp_path: Path):
    calls = []

    with pytest.raises(
        ValueError,
        match="Unsupported motion",
    ):
        prepare_motion_workflow(
            tmp_path,
            "bad-flow",
            "backflip",
            lambda **kwargs: calls.append(kwargs),
        )

    assert calls == []


def test_invalid_candidate_plan_is_rejected(tmp_path: Path):
    def writer(**kwargs):
        if kwargs["profile"] == "baseline":
            return fake_plan(
                attempt=kwargs["attempt"],
                motion_id=kwargs["motion_id"],
                profile="baseline",
                plan_hash="a" * 64,
            )

        return fake_plan(
            attempt=kwargs["attempt"],
            motion_id=kwargs["motion_id"],
            profile="baseline",
            plan_hash="b" * 64,
        )

    with pytest.raises(
        ValueError,
        match="profile does not match",
    ):
        prepare_motion_workflow(
            tmp_path,
            "spin-flow-1",
            "spin-kick",
            writer,
        )
