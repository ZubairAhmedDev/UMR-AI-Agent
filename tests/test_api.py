from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from umr_agent.api.app import Settings, create_app


class PlanningApiTests(unittest.TestCase):
    TOKEN = "test-only-secret-token-with-at-least-32-chars"

    def setUp(self) -> None:
        self.client = TestClient(create_app(Settings(api_token=self.TOKEN)))
        self.client.headers["Authorization"] = f"Bearer {self.TOKEN}"

    def test_message_to_proposal_in_one_request(self) -> None:
        response = self.client.post(
            "/api/agent/proposals",
            json={"goal": "Retarget the spin kick to Unitree G1 using 6 workers", "provider": "rules"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "proposal")
        self.assertEqual(body["proposal"]["robot_id"], "unitree-g1")
        self.assertEqual(body["proposal"]["motion_id"], "humanoid-spin-kick")
        self.assertFalse(body["proposal"]["executable"])
        self.assertTrue(body["warnings"])

    def test_missing_motion_returns_clarification(self) -> None:
        response = self.client.post(
            "/api/agent/proposals", json={"goal": "Retarget a motion to Unitree G1"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "clarification")

    def test_unknown_provider_and_extra_field_rejected(self) -> None:
        response = self.client.post(
            "/api/agent/proposals",
            json={"goal": "Retarget a motion", "provider": "shell", "command": "echo unsafe"},
        )
        self.assertEqual(response.status_code, 422)

    def test_api_rejects_missing_or_invalid_token(self) -> None:
        self.client.headers.pop("Authorization")
        self.assertEqual(self.client.get("/api/catalog").status_code, 401)
        self.client.headers["Authorization"] = "Bearer wrong-token"
        self.assertEqual(self.client.post("/api/agent/proposals", json={"goal": "test"}).status_code, 401)

    def test_plan_recovery_is_read_only_and_requires_token(self) -> None:
        self.client.headers.pop("Authorization")
        with patch("umr_agent.api.app.read_attempt") as reader:
            self.assertEqual(self.client.get("/api/attempts/run-001/plan").status_code, 401)
            reader.assert_not_called()
        self.client.headers["Authorization"] = f"Bearer {self.TOKEN}"
        with patch("umr_agent.api.app.read_attempt", side_effect=RuntimeError("bridge unavailable")) as reader:
            self.assertEqual(self.client.get("/api/attempts/run-001/plan").status_code, 503)
            self.assertEqual(reader.call_args.args[-2:], ("run-001", "plan"))

    def test_api_fails_closed_without_configured_token(self) -> None:
        client = TestClient(create_app(Settings()))
        self.assertEqual(client.get("/api/catalog").status_code, 503)
        self.assertEqual(client.post("/api/agent/proposals", json={"goal": "test"}).status_code, 503)

    def test_browser_cors_is_not_enabled_on_private_api(self) -> None:
        response = self.client.get("/api/catalog", headers={"Origin": "http://127.0.0.1:3000"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_catalog_failure_is_service_unavailable(self) -> None:
        with TemporaryDirectory() as root:
            app = create_app(Settings(catalog_path=Path(root) / "missing.json", api_token=self.TOKEN))
            response = TestClient(app).get(
                "/api/catalog", headers={"Authorization": f"Bearer {self.TOKEN}"}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Agent catalog is unavailable.")

    def test_improve_attempt_returns_prepared_candidate(self) -> None:
        fake_result = type(
            "FakeImprovement",
            (),
            {
                "state": "approval_required",
                "baseline_attempt": "spin-main",
                "candidate_attempt": "spin-main-gc",
                "candidate_plan_hash": "a" * 64,
                "reason": "Detected 7 foot-skating frames.",
            },
        )()

        with patch(
            "umr_agent.api.app.prepare_improvement",
            return_value=fake_result,
        ) as service:
            response = self.client.post(
                "/api/agent/attempts/spin-main/improve"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "approval_required")
        self.assertEqual(body["baseline_attempt"], "spin-main")
        self.assertEqual(body["candidate_attempt"], "spin-main-gc")
        self.assertEqual(body["candidate_plan_hash"], "a" * 64)

        self.assertEqual(service.call_count, 1)
        self.assertEqual(service.call_args.args[0], "spin-main")


    def test_improve_attempt_returns_not_needed(self) -> None:
        fake_result = type(
            "FakeImprovement",
            (),
            {
                "state": "not_needed",
                "baseline_attempt": "spin-main",
                "candidate_attempt": None,
                "candidate_plan_hash": None,
                "reason": "No foot skating was detected.",
            },
        )()

        with patch(
            "umr_agent.api.app.prepare_improvement",
            return_value=fake_result,
        ):
            response = self.client.post(
                "/api/agent/attempts/spin-main/improve"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "not_needed")
        self.assertIsNone(body["candidate_attempt"])
        self.assertIsNone(body["candidate_plan_hash"])


    def test_improve_attempt_rejects_incomplete_attempt(self) -> None:
        with patch(
            "umr_agent.api.app.prepare_improvement",
            side_effect=ValueError(
                "Baseline attempt must be completed before improvement."
            ),
        ):
            response = self.client.post(
                "/api/agent/attempts/spin-main/improve"
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Baseline attempt must be completed before improvement.",
        )


    def test_improve_attempt_reports_bridge_failure(self) -> None:
        with patch(
            "umr_agent.api.app.prepare_improvement",
            side_effect=RuntimeError("Ubuntu inspection failed"),
        ):
            response = self.client.post(
                "/api/agent/attempts/spin-main/improve"
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Ubuntu inspection failed",
        )


    def test_evaluate_attempt_returns_candidate_winner(self) -> None:
        score_type = type(
            "FakeScore",
            (),
            {
                "errors": 0,
                "skating_frames": 7,
                "velocity_warning_groups": 10,
            },
        )

        baseline_score = score_type()

        candidate_score = type(
            "FakeCandidateScore",
            (),
            {
                "errors": 0,
                "skating_frames": 6,
                "velocity_warning_groups": 10,
            },
        )()

        fake_result = type(
            "FakeEvaluation",
            (),
            {
                "state": "evaluated",
                "baseline_attempt": "spin-main",
                "candidate_attempt": "spin-main-gc",
                "winner": "candidate",
                "winner_attempt": "spin-main-gc",
                "reason": "Candidate reduced foot-skating frames without adding errors.",
                "baseline": baseline_score,
                "candidate": candidate_score,
            },
        )()

        with patch(
            "umr_agent.api.app.evaluate_improvement",
            return_value=fake_result,
        ) as service:
            response = self.client.post(
                "/api/agent/attempts/spin-main/evaluate"
            )

        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["winner"], "candidate")
        self.assertEqual(body["winner_attempt"], "spin-main-gc")
        self.assertEqual(body["baseline"]["skating_frames"], 7)
        self.assertEqual(body["candidate"]["skating_frames"], 6)

        service.assert_called_once()
        self.assertEqual(service.call_args.args[0], "spin-main")


    def test_evaluate_attempt_rejects_incomplete_candidate(self) -> None:
        with patch(
            "umr_agent.api.app.evaluate_improvement",
            side_effect=ValueError(
                "Candidate attempt must be completed before evaluation."
            ),
        ):
            response = self.client.post(
                "/api/agent/attempts/spin-main/evaluate"
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Candidate attempt must be completed before evaluation.",
        )


    def test_evaluate_attempt_reports_bridge_failure(self) -> None:
        with patch(
            "umr_agent.api.app.evaluate_improvement",
            side_effect=RuntimeError("Ubuntu inspection failed"),
        ):
            response = self.client.post(
                "/api/agent/attempts/spin-main/evaluate"
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Ubuntu inspection failed",
        )


    def test_invalid_catalog_is_rejected(self) -> None:
        with TemporaryDirectory() as root:
            catalog_path = Path(root) / "catalog.json"
            catalog_path.write_text(json.dumps({"robots": [{}], "motions": []}), encoding="utf-8")
            response = TestClient(create_app(Settings(catalog_path=catalog_path, api_token=self.TOKEN))).get(
                "/api/catalog", headers={"Authorization": f"Bearer {self.TOKEN}"}
            )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
