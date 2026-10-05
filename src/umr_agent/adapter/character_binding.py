"""Read-only binding check for the pinned UMR Humanoid Character pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from umr_agent.domain.models import ExecutionPlan
from umr_agent.validation.assets import confine_path, sha256_file

CHARACTER_DEFAULTS = "humanoid_retarget_defaults_humanoid_character.json"


def _json_object(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Character configuration is unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Character configuration must be a JSON object: {path}")
    return value


def verify_character_motion_binding(
    plan: ExecutionPlan, *, config_path: Path, umr_repository: Path
) -> None:
    """Require UMR's merged config to select the plan's exact registered motion.

    The pinned Character script merges a built-in defaults JSON with the robot
    configuration before reading motion.data and motion.seq_key. This check
    implements that merge for the motion section only. It never loads a pickle.
    """
    defaults = _json_object(confine_path(umr_repository, CHARACTER_DEFAULTS))
    override = _json_object(config_path)
    if "extends" in defaults or "extends" in override:
        raise ValueError("Character config inheritance needs an explicit binding check")
    default_motion = defaults.get("motion")
    override_motion = override.get("motion", {})
    if not isinstance(default_motion, dict) or not isinstance(override_motion, dict):
        raise ValueError("Character motion configuration must be a JSON object")
    effective = {**default_motion, **override_motion}
    selected = effective.get("data")
    if not isinstance(selected, str) or not selected or Path(selected).is_absolute():
        raise ValueError("Character motion.data must be a project-relative path")
    effective_path = confine_path(umr_repository, selected)
    intended_path = confine_path(umr_repository, plan.motion.path)
    if effective_path != intended_path:
        raise ValueError("Character configuration selects a different motion than the plan")
    if not plan.motion.sequence_key or effective.get("seq_key") != plan.motion.sequence_key:
        raise ValueError("Character configuration selects a different sequence than the plan")
    if not intended_path.is_file() or intended_path.suffix.lower() != ".pkl":
        raise ValueError("Selected Character motion is not an available .pkl file")
    if sha256_file(intended_path) != plan.motion.sha256:
        raise ValueError("Selected Character motion does not match its registered SHA-256")
