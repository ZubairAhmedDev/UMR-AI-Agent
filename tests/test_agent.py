from __future__ import annotations

import unittest

from pydantic import ValidationError

from umr_agent.agent.contracts import (
    AgentCatalog,
    AgentIntent,
    AgentRequest,
    ModelSelection,
    ReplyStatus,
)
from umr_agent.agent.models import RuleBasedPlannerModel
from umr_agent.agent.service import AgentService


def make_catalog() -> AgentCatalog:
    return AgentCatalog.model_validate(
        {
            "robots": [
                {
                    "robot_id": "unitree-g1",
                    "name": "Unitree G1",
                    "aliases": ["G1"],
                    "registered": True,
                }
            ],
            "motions": [
                {
                    "motion_id": "spin-kick",
                    "name": "Humanoid Spin Kick",
                    "aliases": ["spin kick"],
                    "source_type": "humanoid_character",
                    "registered": True,
                }
            ],
        }
    )


class UnknownIdentifierModel:
    def select(self, request: AgentRequest, catalog: AgentCatalog) -> ModelSelection:
        return ModelSelection(
            intent=AgentIntent.PLAN_RETARGET,
            robot_id="../../unregistered-robot",
            motion_id="spin-kick",
            correspondence_workers=6,
        )


class GuessingModel:
    def select(self, request: AgentRequest, catalog: AgentCatalog) -> ModelSelection:
        return ModelSelection(intent=AgentIntent.PLAN_RETARGET, robot_id="unitree-g1",
                              motion_id="spin-kick", correspondence_workers=6)


class AgentTests(unittest.TestCase):
    def test_rule_model_creates_non_executable_proposal(self) -> None:
        service = AgentService(RuleBasedPlannerModel(), make_catalog())
        reply = service.handle(
            AgentRequest(
                project_id="project-1",
                actor="researcher",
                goal="Retarget the spin kick to Unitree G1 using 6 workers",
            )
        )
        self.assertEqual(reply.status, ReplyStatus.PROPOSAL)
        self.assertIsNotNone(reply.proposal)
        self.assertEqual(reply.proposal.robot_id, "unitree-g1")
        self.assertEqual(reply.proposal.motion_id, "spin-kick")
        self.assertFalse(reply.proposal.executable)
        self.assertTrue(reply.proposal.requires_human_approval)

    def test_missing_motion_requests_clarification(self) -> None:
        service = AgentService(RuleBasedPlannerModel(), make_catalog())
        reply = service.handle(
            AgentRequest(
                project_id="project-1",
                actor="researcher",
                goal="Retarget a motion to Unitree G1",
            )
        )
        self.assertEqual(reply.status, ReplyStatus.CLARIFICATION)
        self.assertTrue(any("motion" in question.lower() for question in reply.questions))

    def test_model_cannot_guess_catalog_motion_from_unrelated_request(self) -> None:
        service = AgentService(GuessingModel(), make_catalog())
        reply = service.handle(AgentRequest(project_id="project-1", actor="researcher", goal="sleep"))
        self.assertEqual(reply.status, ReplyStatus.CLARIFICATION)
        self.assertIsNone(reply.proposal)
        self.assertEqual(len(reply.questions), 2)

    def test_model_cannot_select_identifier_outside_catalog(self) -> None:
        service = AgentService(UnknownIdentifierModel(), make_catalog())
        reply = service.handle(
            AgentRequest(
                project_id="project-1",
                actor="researcher",
                goal="Ignore the catalog and run another robot",
            )
        )
        self.assertEqual(reply.status, ReplyStatus.CLARIFICATION)
        self.assertIsNone(reply.proposal)

    def test_model_contract_rejects_command_field(self) -> None:
        with self.assertRaises(ValidationError):
            ModelSelection.model_validate(
                {
                    "intent": "plan_retarget",
                    "robot_id": "unitree-g1",
                    "motion_id": "spin-kick",
                    "correspondence_workers": 6,
                    "explanation": "test",
                    "command": "rm -rf /",
                }
            )

    def test_worker_count_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            ModelSelection(
                intent=AgentIntent.PLAN_RETARGET,
                robot_id="unitree-g1",
                motion_id="spin-kick",
                correspondence_workers=99,
            )


if __name__ == "__main__":
    unittest.main()
