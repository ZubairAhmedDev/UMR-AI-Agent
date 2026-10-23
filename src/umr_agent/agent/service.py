from __future__ import annotations

from umr_agent.agent.contracts import (
    AgentCatalog,
    AgentIntent,
    AgentReply,
    AgentRequest,
    PlanProposal,
    ReplyStatus,
)
from umr_agent.agent.models import PlannerModel, _match_catalog_id


class AgentService:
    """Bounded planning service. It can propose work but cannot execute UMR."""

    def __init__(self, model: PlannerModel, catalog: AgentCatalog) -> None:
        self._model = model
        self._catalog = catalog
        self._robots = {item.robot_id: item for item in catalog.robots}
        self._motions = {item.motion_id: item for item in catalog.motions}

    def handle(self, request: AgentRequest) -> AgentReply:
        selection = self._model.select(request, self._catalog)
        if selection.intent is not AgentIntent.PLAN_RETARGET:
            return AgentReply(
                status=ReplyStatus.CLARIFICATION,
                intent=selection.intent,
                message="I can currently help create supported robot motions.",
                questions=("Which motion would you like the robot to perform?",),
            )

        questions: list[str] = []
        # A model can return a valid catalog ID that the user never requested.
        # Require an explicit name or alias in the goal before proposing it.
        robot_id = _match_catalog_id(request.goal, self._catalog.robots, "robot_id")
        motion_id = _match_catalog_id(request.goal, self._catalog.motions, "motion_id")
        robot = self._robots.get(selection.robot_id or "") if selection.robot_id == robot_id else None
        motion = self._motions.get(selection.motion_id or "") if selection.motion_id == motion_id else None
        if robot is None:
            questions.append("Which registered target robot should I use?")
        if motion is None:
            questions.append("Which registered source motion should I use?")
        if questions:
            return AgentReply(
                status=ReplyStatus.CLARIFICATION,
                intent=selection.intent,
                message="I need more information before I can prepare a plan.",
                questions=tuple(questions),
            )

        warnings: list[str] = []
        if not robot.registered:
            warnings.append(f"Robot '{robot.name}' is not marked registered in the planning catalog. Local preparation checks the Ubuntu files separately.")
        if not motion.registered:
            warnings.append(f"Motion '{motion.name}' is not marked registered in the planning catalog. Local preparation checks the Ubuntu files separately.")

        proposal = PlanProposal(
            project_id=request.project_id,
            requested_by=request.actor,
            robot_id=robot.robot_id,
            robot_name=robot.name,
            motion_id=motion.motion_id,
            motion_name=motion.name,
            source_type=motion.source_type,
            correspondence_workers=selection.correspondence_workers,
        )
        return AgentReply(
            status=ReplyStatus.PROPOSAL,
            intent=selection.intent,
            message=(
                f"{motion.name} is available for {robot.name}. "
                "The agent is ready to prepare the motion."
            ),
            proposal=proposal,
            warnings=tuple(warnings),
        )
