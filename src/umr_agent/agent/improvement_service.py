"""Deterministic preparation and comparison of UMR motion improvements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from umr_agent.api.wsl_attempts import AttemptDiagnosis, PreparedAttempt


@dataclass(frozen=True)
class DiagnosisScore:
    errors: int
    skating_frames: int
    velocity_warning_groups: int


@dataclass(frozen=True)
class ComparisonResult:
    winner: str
    reason: str
    baseline: DiagnosisScore
    candidate: DiagnosisScore


@dataclass(frozen=True)
class ImprovementPreparation:
    state: str
    baseline_attempt: str
    candidate_attempt: str | None
    candidate_plan_hash: str | None
    reason: str


def score_diagnosis(report: AttemptDiagnosis) -> DiagnosisScore:
    errors = sum(
        1
        for finding in report.findings
        if finding.get("severity") == "error"
    )

    skating_frames = sum(
        int(finding.get("count", 0))
        for finding in report.findings
        if finding.get("check") == "foot_skating"
    )

    velocity_warning_groups = sum(
        1
        for finding in report.findings
        if finding.get("check") == "velocity_spike"
        and finding.get("severity") == "warning"
    )

    return DiagnosisScore(
        errors=errors,
        skating_frames=skating_frames,
        velocity_warning_groups=velocity_warning_groups,
    )


def compare_diagnoses(
    baseline: AttemptDiagnosis,
    candidate: AttemptDiagnosis,
) -> ComparisonResult:
    baseline_score = score_diagnosis(baseline)
    candidate_score = score_diagnosis(candidate)

    if candidate_score.errors > baseline_score.errors:
        return ComparisonResult(
            winner="baseline",
            reason="Candidate introduced additional errors.",
            baseline=baseline_score,
            candidate=candidate_score,
        )

    if candidate_score.errors < baseline_score.errors:
        return ComparisonResult(
            winner="candidate",
            reason="Candidate reduced errors.",
            baseline=baseline_score,
            candidate=candidate_score,
        )

    if candidate_score.skating_frames < baseline_score.skating_frames:
        return ComparisonResult(
            winner="candidate",
            reason="Candidate reduced foot-skating frames without adding errors.",
            baseline=baseline_score,
            candidate=candidate_score,
        )

    if candidate_score.skating_frames > baseline_score.skating_frames:
        return ComparisonResult(
            winner="baseline",
            reason="Candidate increased foot-skating frames.",
            baseline=baseline_score,
            candidate=candidate_score,
        )

    if (
        candidate_score.velocity_warning_groups
        < baseline_score.velocity_warning_groups
    ):
        return ComparisonResult(
            winner="candidate",
            reason="Foot skating tied, but candidate reduced velocity warnings.",
            baseline=baseline_score,
            candidate=candidate_score,
        )

    return ComparisonResult(
        winner="baseline",
        reason="Candidate did not produce a measurable improvement.",
        baseline=baseline_score,
        candidate=candidate_score,
    )


def improvement_attempt_name(baseline_attempt: str) -> str:
    """Create one deterministic candidate name within the 80-character limit."""
    suffix = "-gc"
    return f"{baseline_attempt[:80 - len(suffix)]}{suffix}"


def prepare_improvement(
    baseline_attempt: str,
    reader: Callable,
    writer: Callable,
) -> ImprovementPreparation:
    """Prepare one ground-contact candidate for a completed baseline attempt."""

    status = reader(baseline_attempt, "status")

    if status.state != "completed":
        raise ValueError("Baseline attempt must be completed before improvement.")

    plan = reader(baseline_attempt, "plan")

    if plan.profile != "baseline":
        return ImprovementPreparation(
            state="not_applicable",
            baseline_attempt=baseline_attempt,
            candidate_attempt=None,
            candidate_plan_hash=None,
            reason="Only baseline attempts can start an improvement cycle.",
        )

    diagnosis = reader(baseline_attempt, "diagnose")
    score = score_diagnosis(diagnosis)

    if score.errors > 0:
        return ImprovementPreparation(
            state="not_applicable",
            baseline_attempt=baseline_attempt,
            candidate_attempt=None,
            candidate_plan_hash=None,
            reason="Baseline contains errors that require review before automatic improvement.",
        )

    if score.skating_frames == 0:
        return ImprovementPreparation(
            state="not_needed",
            baseline_attempt=baseline_attempt,
            candidate_attempt=None,
            candidate_plan_hash=None,
            reason="No foot skating was detected.",
        )

    candidate_attempt = improvement_attempt_name(baseline_attempt)

    prepared: PreparedAttempt | None = None

    try:
        existing = reader(candidate_attempt, "plan")
    except RuntimeError:
        existing = None

    if existing is not None:
        if existing.profile != "ground-contact":
            raise ValueError(
                "Existing improvement candidate has the wrong profile."
            )

        if existing.motion_id != plan.motion_id:
            raise ValueError(
                "Existing improvement candidate does not match the baseline motion."
            )

        if existing.max_frames != plan.max_frames:
            raise ValueError(
                "Existing improvement candidate does not match the baseline frame limit."
            )

        prepared = existing

    else:
        prepared = writer(
            action="prepare",
            attempt=candidate_attempt,
            motion_id=plan.motion_id,
            max_frames=plan.max_frames,
            profile="ground-contact",
        )

    return ImprovementPreparation(
        state="approval_required",
        baseline_attempt=baseline_attempt,
        candidate_attempt=prepared.attempt,
        candidate_plan_hash=prepared.plan_hash,
        reason=(
            f"Detected {score.skating_frames} foot-skating frames. "
            "A ground-contact candidate is ready and requires approval."
        ),
    )


@dataclass(frozen=True)
class ImprovementEvaluation:
    state: str
    baseline_attempt: str
    candidate_attempt: str
    winner: str
    winner_attempt: str
    reason: str
    baseline: DiagnosisScore
    candidate: DiagnosisScore


def evaluate_improvement(
    baseline_attempt: str,
    reader: Callable,
) -> ImprovementEvaluation:
    """Compare a completed baseline with its deterministic improvement candidate."""

    candidate_attempt = improvement_attempt_name(baseline_attempt)

    baseline_status = reader(baseline_attempt, "status")
    candidate_status = reader(candidate_attempt, "status")

    if baseline_status.state != "completed":
        raise ValueError("Baseline attempt must be completed before evaluation.")

    if candidate_status.state != "completed":
        raise ValueError("Candidate attempt must be completed before evaluation.")

    baseline_plan = reader(baseline_attempt, "plan")
    candidate_plan = reader(candidate_attempt, "plan")

    if baseline_plan.profile != "baseline":
        raise ValueError("Evaluation requires a baseline-profile source attempt.")

    if candidate_plan.profile != "ground-contact":
        raise ValueError("Evaluation requires a ground-contact candidate.")

    if candidate_plan.motion_id != baseline_plan.motion_id:
        raise ValueError("Candidate motion does not match baseline motion.")

    if candidate_plan.max_frames != baseline_plan.max_frames:
        raise ValueError("Candidate frame limit does not match baseline frame limit.")

    baseline_diagnosis = reader(baseline_attempt, "diagnose")
    candidate_diagnosis = reader(candidate_attempt, "diagnose")

    comparison = compare_diagnoses(
        baseline_diagnosis,
        candidate_diagnosis,
    )

    winner_attempt = (
        candidate_attempt
        if comparison.winner == "candidate"
        else baseline_attempt
    )

    return ImprovementEvaluation(
        state="evaluated",
        baseline_attempt=baseline_attempt,
        candidate_attempt=candidate_attempt,
        winner=comparison.winner,
        winner_attempt=winner_attempt,
        reason=comparison.reason,
        baseline=comparison.baseline,
        candidate=comparison.candidate,
    )
