from __future__ import annotations

import unittest

from umr_agent.domain.states import InvalidTransition, JobState, transition


class StateMachineTests(unittest.TestCase):
    def test_happy_path(self) -> None:
        state = JobState.DRAFT
        for target in (
            JobState.VALIDATED,
            JobState.APPROVED,
            JobState.QUEUED,
            JobState.RUNNING,
            JobState.VERIFYING,
            JobState.COMPLETED,
        ):
            state = transition(state, target)
        self.assertEqual(state, JobState.COMPLETED)

    def test_cannot_skip_approval(self) -> None:
        with self.assertRaises(InvalidTransition):
            transition(JobState.VALIDATED, JobState.RUNNING)

    def test_failed_verification_is_not_completed(self) -> None:
        self.assertEqual(
            transition(JobState.VERIFYING, JobState.FAILED_VERIFICATION),
            JobState.FAILED_VERIFICATION,
        )
        with self.assertRaises(InvalidTransition):
            transition(JobState.FAILED_VERIFICATION, JobState.COMPLETED)


if __name__ == "__main__":
    unittest.main()

