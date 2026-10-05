from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from umr_agent.agent.reviews import InputReview, ReviewRequest, build_input_review
from umr_agent.api.app import Settings, create_app
from umr_agent.api.wsl_assets import AssetStatus


def evidence() -> AssetStatus:
    return AssetStatus(
        state="verified", message="verified", file_count=144, umr_git_commit="a" * 40,
        robot_config_sha256="1" * 64, robot_xml_sha256="2" * 64,
        motion_sha256="3" * 64, manifest_sha256="4" * 64,
        correspondence_slots_sha256="5" * 64,
    )


class InputReviewTests(unittest.TestCase):
    def test_review_binds_verified_inputs_and_worker_count(self) -> None:
        request = ReviewRequest(robot_id="unitree-g1", motion_id="humanoid-spin-kick", correspondence_workers=6)
        review = build_input_review(request, evidence())
        self.assertFalse(review.executable)
        self.assertEqual(review.review_hash, review.compute_hash())
        self.assertEqual(review.correspondence_slots_sha256, "5" * 64)
        changed = build_input_review(request.model_copy(update={"correspondence_workers": 4}), evidence())
        self.assertNotEqual(review.review_hash, changed.review_hash)
        changed_slots = build_input_review(request, evidence().model_copy(
            update={"correspondence_slots_sha256": "f" * 64}))
        self.assertNotEqual(review.review_hash, changed_slots.review_hash)
        tampered = review.model_dump()
        tampered["motion_sha256"] = "f" * 64
        with self.assertRaises(ValidationError):
            InputReview.model_validate(tampered)

    def test_review_api_checks_token_and_fresh_status(self) -> None:
        client = TestClient(create_app(Settings(api_token="x" * 32)))
        body = {"robot_id": "unitree-g1", "motion_id": "humanoid-spin-kick", "correspondence_workers": 6}
        self.assertEqual(client.post("/api/agent/reviews", json=body).status_code, 401)
        client.headers["Authorization"] = f"Bearer {'x' * 32}"
        self.assertEqual(client.post("/api/agent/reviews", json=body).status_code, 409)
        with patch("umr_agent.api.app.check_assets", return_value=evidence()) as verify:
            response = client.post("/api/agent/reviews", json=body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(verify.call_count, 1)
        self.assertFalse(response.json()["executable"])
        body["motion_id"] = "unknown"
        with patch("umr_agent.api.app.check_assets") as verify:
            self.assertEqual(client.post("/api/agent/reviews", json=body).status_code, 409)
            verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
