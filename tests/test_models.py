from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from tests.helpers import make_plan, plan_data
from umr_agent.domain.models import Approval, ExecutionPlan


class ExecutionPlanTests(unittest.TestCase):
    def test_hash_is_deterministic_and_sealed_plan_validates(self) -> None:
        first = make_plan()
        second = make_plan()
        self.assertEqual(first.compute_hash(), second.compute_hash())
        sealed = first.sealed()
        self.assertEqual(sealed.plan_hash, sealed.compute_hash())
        self.assertEqual(ExecutionPlan.model_validate(sealed.model_dump()), sealed)

    def test_rejects_tampered_plan_hash(self) -> None:
        data = plan_data()
        data["plan_hash"] = "f" * 64
        with self.assertRaises(ValidationError):
            ExecutionPlan.model_validate(data)

    def test_rejects_parent_path(self) -> None:
        data = plan_data()
        data["motion"]["path"] = "../outside.npz"  # type: ignore[index]
        with self.assertRaises(ValidationError):
            ExecutionPlan.model_validate(data)

    def test_approval_binds_exact_plan_hash_and_expiry(self) -> None:
        plan = make_plan(sealed=True)
        approved_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        approval = Approval(
            approval_id="approval-001",
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            actor="reviewer",
            approved_at=approved_at,
            expires_at=approved_at + timedelta(hours=1),
        )
        self.assertTrue(approval.authorizes(plan, at=approved_at + timedelta(minutes=10)))
        self.assertFalse(approval.authorizes(plan, at=approved_at + timedelta(hours=2)))


if __name__ == "__main__":
    unittest.main()

