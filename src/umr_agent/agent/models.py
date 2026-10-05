from __future__ import annotations

import re
from typing import Protocol

from umr_agent.agent.contracts import AgentCatalog, AgentIntent, AgentRequest, ModelSelection


class PlannerModel(Protocol):
    def select(self, request: AgentRequest, catalog: AgentCatalog) -> ModelSelection:
        """Return only a typed selection; never execute a tool or command."""


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _match_catalog_id(goal: str, items: tuple[object, ...], id_field: str) -> str | None:
    normalized_goal = f" {_normalize(goal)} "
    candidates: list[tuple[int, str]] = []
    for item in items:
        item_id = str(getattr(item, id_field))
        terms = (item_id, str(item.name), *item.aliases)
        for term in terms:
            normalized_term = _normalize(term)
            if normalized_term and f" {normalized_term} " in normalized_goal:
                candidates.append((len(normalized_term), item_id))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    longest = candidates[0][0]
    best_ids = {item_id for length, item_id in candidates if length == longest}
    return next(iter(best_ids)) if len(best_ids) == 1 else None


class RuleBasedPlannerModel:
    """Offline development model used to exercise the safe agent loop without an LLM."""

    def select(self, request: AgentRequest, catalog: AgentCatalog) -> ModelSelection:
        goal = request.goal
        normalized = _normalize(goal)
        intent = (
            AgentIntent.PLAN_RETARGET
            if any(term in normalized for term in ("retarget", "motion", "animate"))
            else AgentIntent.UNKNOWN
        )
        worker_match = re.search(r"\b(\d{1,2})\s+(?:correspondence\s+)?workers?\b", normalized)
        workers = int(worker_match.group(1)) if worker_match else 6
        return ModelSelection(
            intent=intent,
            robot_id=_match_catalog_id(goal, catalog.robots, "robot_id"),
            motion_id=_match_catalog_id(goal, catalog.motions, "motion_id"),
            correspondence_workers=workers,
            explanation="Selection was derived from registered catalog names and aliases.",
        )

