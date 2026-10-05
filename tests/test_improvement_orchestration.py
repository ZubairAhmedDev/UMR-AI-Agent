from types import SimpleNamespace

import pytest

from umr_agent.agent.improvement_service import (
    improvement_attempt_name,
    prepare_improvement,
)


def fake_status(state="completed"):
    return SimpleNamespace(state=state)


def fake_plan(
    *,
    profile="baseline",
    motion_id="spin-kick",
    max_frames=0,
):
    return SimpleNamespace(
        profile=profile,
        motion_id=motion_id,
        max_frames=max_frames,
    )


def fake_diagnosis(*, errors=0, skating=0):
    findings = []

    for index in range(errors):
        findings.append(
            {
                "check": f"error-{index}",
                "severity": "error",
            }
        )

    if skating:
        findings.append(
            {
                "check": "foot_skating",
                "severity": "warning",
                "foot": "left",
                "count": skating,
                "frames": list(range(skating)),
            }
        )

    return SimpleNamespace(findings=findings)


def make_reader(
    *,
    state="completed",
    profile="baseline",
    errors=0,
    skating=0,
):
    def reader(attempt, action):
        if action == "status":
            return fake_status(state)

        if action == "plan":
            if attempt.endswith("-gc"):
                raise RuntimeError("Attempt not found")
            return fake_plan(profile=profile)

        if action == "diagnose":
            return fake_diagnosis(
                errors=errors,
                skating=skating,
            )

        raise AssertionError(f"Unexpected action: {action}")

    return reader


def test_rejects_incomplete_baseline():
    reader = make_reader(state="running")

    with pytest.raises(
        ValueError,
        match="must be completed",
    ):
        prepare_improvement(
            "attempt-1",
            reader,
            lambda **kwargs: None,
        )


def test_does_not_improve_non_baseline_profile():
    reader = make_reader(profile="ground-contact")

    result = prepare_improvement(
        "attempt-1",
        reader,
        lambda **kwargs: None,
    )

    assert result.state == "not_applicable"
    assert result.candidate_attempt is None


def test_does_not_improve_when_errors_exist():
    reader = make_reader(errors=1, skating=5)

    result = prepare_improvement(
        "attempt-1",
        reader,
        lambda **kwargs: None,
    )

    assert result.state == "not_applicable"
    assert result.candidate_attempt is None


def test_no_candidate_when_no_skating_exists():
    reader = make_reader(skating=0)

    result = prepare_improvement(
        "attempt-1",
        reader,
        lambda **kwargs: None,
    )

    assert result.state == "not_needed"
    assert result.candidate_attempt is None


def test_prepares_ground_contact_candidate_when_skating_exists():
    reader = make_reader(skating=7)

    calls = []

    def writer(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            attempt=kwargs["attempt"],
            plan_hash="a" * 64,
        )

    result = prepare_improvement(
        "spin-kick-main",
        reader,
        writer,
    )

    assert result.state == "approval_required"
    assert result.baseline_attempt == "spin-kick-main"
    assert result.candidate_attempt == "spin-kick-main-gc"
    assert result.candidate_plan_hash == "a" * 64

    assert calls == [
        {
            "action": "prepare",
            "attempt": "spin-kick-main-gc",
            "motion_id": "spin-kick",
            "max_frames": 0,
            "profile": "ground-contact",
        }
    ]


def test_candidate_name_respects_attempt_limit():
    baseline = "a" * 80

    candidate = improvement_attempt_name(baseline)

    assert len(candidate) == 80
    assert candidate.endswith("-gc")


from umr_agent.agent.improvement_service import evaluate_improvement


def make_evaluation_reader(
    *,
    baseline_state="completed",
    candidate_state="completed",
    baseline_profile="baseline",
    candidate_profile="ground-contact",
    baseline_motion="spin-kick",
    candidate_motion="spin-kick",
    baseline_frames=0,
    candidate_frames=0,
    baseline_skating=7,
    candidate_skating=6,
    candidate_errors=0,
):
    def reader(attempt, action):
        is_candidate = attempt.endswith("-gc")

        if action == "status":
            return fake_status(
                candidate_state if is_candidate else baseline_state
            )

        if action == "plan":
            return SimpleNamespace(
                profile=(
                    candidate_profile
                    if is_candidate
                    else baseline_profile
                ),
                motion_id=(
                    candidate_motion
                    if is_candidate
                    else baseline_motion
                ),
                max_frames=(
                    candidate_frames
                    if is_candidate
                    else baseline_frames
                ),
            )

        if action == "diagnose":
            if is_candidate:
                return fake_diagnosis(
                    errors=candidate_errors,
                    skating=candidate_skating,
                )

            return fake_diagnosis(
                errors=0,
                skating=baseline_skating,
            )

        raise AssertionError(f"Unexpected action: {action}")

    return reader


def test_evaluation_selects_candidate_when_skating_improves():
    reader = make_evaluation_reader(
        baseline_skating=7,
        candidate_skating=6,
    )

    result = evaluate_improvement(
        "spin-main",
        reader,
    )

    assert result.state == "evaluated"
    assert result.winner == "candidate"
    assert result.winner_attempt == "spin-main-gc"
    assert result.baseline.skating_frames == 7
    assert result.candidate.skating_frames == 6


def test_evaluation_keeps_baseline_when_candidate_is_worse():
    reader = make_evaluation_reader(
        baseline_skating=7,
        candidate_skating=8,
    )

    result = evaluate_improvement(
        "spin-main",
        reader,
    )

    assert result.winner == "baseline"
    assert result.winner_attempt == "spin-main"


def test_evaluation_rejects_incomplete_candidate():
    reader = make_evaluation_reader(
        candidate_state="running",
    )

    with pytest.raises(
        ValueError,
        match="Candidate attempt must be completed",
    ):
        evaluate_improvement(
            "spin-main",
            reader,
        )


def test_evaluation_rejects_wrong_candidate_profile():
    reader = make_evaluation_reader(
        candidate_profile="baseline",
    )

    with pytest.raises(
        ValueError,
        match="ground-contact candidate",
    ):
        evaluate_improvement(
            "spin-main",
            reader,
        )


def test_evaluation_rejects_mismatched_motion():
    reader = make_evaluation_reader(
        candidate_motion="run",
    )

    with pytest.raises(
        ValueError,
        match="Candidate motion does not match baseline motion",
    ):
        evaluate_improvement(
            "spin-main",
            reader,
        )


def test_evaluation_rejects_mismatched_frame_limit():
    reader = make_evaluation_reader(
        candidate_frames=3,
    )

    with pytest.raises(
        ValueError,
        match="Candidate frame limit does not match baseline frame limit",
    ):
        evaluate_improvement(
            "spin-main",
            reader,
        )


def test_prepare_improvement_reuses_existing_candidate():
    candidate_plan = SimpleNamespace(
        attempt="spin-main-gc",
        profile="ground-contact",
        motion_id="spin-kick",
        max_frames=0,
        plan_hash="a" * 64,
    )

    def reader(attempt, action):
        if attempt == "spin-main-gc" and action == "plan":
            return candidate_plan

        if action == "status":
            return fake_status("completed")

        if action == "plan":
            return fake_plan(
                profile="baseline",
                motion_id="spin-kick",
                max_frames=0,
            )

        if action == "diagnose":
            return fake_diagnosis(
                errors=0,
                skating=7,
            )

        raise AssertionError(
            f"Unexpected read: {attempt} {action}"
        )

    writer_called = False

    def writer(**kwargs):
        nonlocal writer_called
        writer_called = True
        raise AssertionError("Existing candidate must be reused")

    result = prepare_improvement(
        "spin-main",
        reader,
        writer,
    )

    assert result.state == "approval_required"
    assert result.candidate_attempt == "spin-main-gc"
    assert result.candidate_plan_hash == "a" * 64
    assert writer_called is False


def test_prepare_improvement_rejects_mismatched_existing_candidate():
    candidate_plan = SimpleNamespace(
        attempt="spin-main-gc",
        profile="ground-contact",
        motion_id="run",
        max_frames=0,
        plan_hash="a" * 64,
    )

    def reader(attempt, action):
        if attempt == "spin-main-gc" and action == "plan":
            return candidate_plan

        if action == "status":
            return fake_status("completed")

        if action == "plan":
            return fake_plan(
                profile="baseline",
                motion_id="spin-kick",
                max_frames=0,
            )

        if action == "diagnose":
            return fake_diagnosis(
                errors=0,
                skating=7,
            )

        raise AssertionError(
            f"Unexpected read: {attempt} {action}"
        )

    with pytest.raises(
        ValueError,
        match="does not match the baseline motion",
    ):
        prepare_improvement(
            "spin-main",
            reader,
            lambda **kwargs: None,
        )


def test_prepare_improvement_reuses_existing_candidate():
    candidate_plan = SimpleNamespace(
        attempt="spin-main-gc",
        profile="ground-contact",
        motion_id="spin-kick",
        max_frames=0,
        plan_hash="a" * 64,
    )

    def reader(attempt, action):
        if attempt == "spin-main-gc" and action == "plan":
            return candidate_plan

        if action == "status":
            return fake_status("completed")

        if action == "plan":
            return fake_plan(
                profile="baseline",
                motion_id="spin-kick",
                max_frames=0,
            )

        if action == "diagnose":
            return fake_diagnosis(
                errors=0,
                skating=7,
            )

        raise AssertionError(
            f"Unexpected read: {attempt} {action}"
        )

    writer_called = False

    def writer(**kwargs):
        nonlocal writer_called
        writer_called = True
        raise AssertionError("Existing candidate must be reused")

    result = prepare_improvement(
        "spin-main",
        reader,
        writer,
    )

    assert result.state == "approval_required"
    assert result.candidate_attempt == "spin-main-gc"
    assert result.candidate_plan_hash == "a" * 64
    assert writer_called is False


def test_prepare_improvement_rejects_mismatched_existing_candidate():
    candidate_plan = SimpleNamespace(
        attempt="spin-main-gc",
        profile="ground-contact",
        motion_id="run",
        max_frames=0,
        plan_hash="a" * 64,
    )

    def reader(attempt, action):
        if attempt == "spin-main-gc" and action == "plan":
            return candidate_plan

        if action == "status":
            return fake_status("completed")

        if action == "plan":
            return fake_plan(
                profile="baseline",
                motion_id="spin-kick",
                max_frames=0,
            )

        if action == "diagnose":
            return fake_diagnosis(
                errors=0,
                skating=7,
            )

        raise AssertionError(
            f"Unexpected read: {attempt} {action}"
        )

    with pytest.raises(
        ValueError,
        match="does not match the baseline motion",
    ):
        prepare_improvement(
            "spin-main",
            reader,
            lambda **kwargs: None,
        )
