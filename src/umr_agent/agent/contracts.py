from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from umr_agent.domain.models import SourceType, StrictModel


class AgentIntent(StrEnum):
    PLAN_RETARGET = "plan_retarget"
    INSPECT_ENVIRONMENT = "inspect_environment"
    GET_JOB_STATUS = "get_job_status"
    UNKNOWN = "unknown"


class ReplyStatus(StrEnum):
    PROPOSAL = "proposal"
    CLARIFICATION = "clarification"
    INFORMATION = "information"
    REJECTED = "rejected"


class CatalogRobot(StrictModel):
    robot_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    aliases: tuple[str, ...] = ()
    registered: bool = False


class CatalogMotion(StrictModel):
    motion_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    aliases: tuple[str, ...] = ()
    source_type: SourceType
    registered: bool = False


class AgentCatalog(StrictModel):
    schema_version: str = "1.0"
    robots: tuple[CatalogRobot, ...]
    motions: tuple[CatalogMotion, ...]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> AgentCatalog:
        robot_ids = [item.robot_id for item in self.robots]
        motion_ids = [item.motion_id for item in self.motions]
        if len(robot_ids) != len(set(robot_ids)):
            raise ValueError("robot IDs must be unique")
        if len(motion_ids) != len(set(motion_ids)):
            raise ValueError("motion IDs must be unique")
        return self


class AgentRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=100)
    actor: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=2000)

    @field_validator("goal")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in "\n\t" for character in value):
            raise ValueError("goal contains unsupported control characters")
        return value.strip()


class ModelSelection(StrictModel):
    intent: AgentIntent
    robot_id: str | None = Field(default=None, max_length=100)
    motion_id: str | None = Field(default=None, max_length=100)
    correspondence_workers: int = Field(default=6, ge=1, le=12)
    explanation: str = Field(default="", max_length=500)


class PlanProposal(StrictModel):
    project_id: str
    requested_by: str
    robot_id: str
    robot_name: str
    motion_id: str
    motion_name: str
    source_type: SourceType
    correspondence_workers: int = Field(ge=1, le=12)
    requires_human_approval: bool = True
    executable: bool = False


class AgentReply(StrictModel):
    status: ReplyStatus
    message: str
    intent: AgentIntent
    proposal: PlanProposal | None = None
    questions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

