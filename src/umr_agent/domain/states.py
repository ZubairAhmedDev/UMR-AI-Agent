from __future__ import annotations

from enum import StrEnum


class InvalidTransition(ValueError):
    pass


class JobState(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    FAILED_VERIFICATION = "failed_verification"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"
    REJECTED = "rejected"
    EXPIRED = "expired"


ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.DRAFT: frozenset({JobState.VALIDATED, JobState.REJECTED}),
    JobState.VALIDATED: frozenset({JobState.APPROVED, JobState.REJECTED}),
    JobState.APPROVED: frozenset({JobState.QUEUED, JobState.EXPIRED, JobState.CANCELLED}),
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLED, JobState.FAILED}),
    JobState.RUNNING: frozenset(
        {JobState.VERIFYING, JobState.CANCELLING, JobState.FAILED, JobState.ORPHANED}
    ),
    JobState.CANCELLING: frozenset({JobState.CANCELLED, JobState.FAILED}),
    JobState.VERIFYING: frozenset({JobState.COMPLETED, JobState.FAILED_VERIFICATION}),
    JobState.ORPHANED: frozenset({JobState.RUNNING, JobState.FAILED, JobState.CANCELLED}),
}

TERMINAL_STATES = frozenset(
    {
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.FAILED_VERIFICATION,
        JobState.CANCELLED,
        JobState.REJECTED,
        JobState.EXPIRED,
    }
)


def transition(current: JobState, target: JobState) -> JobState:
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransition(f"cannot transition from {current.value} to {target.value}")
    return target

