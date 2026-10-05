from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from umr_agent.domain.models import ExecutionPlan, SourceType
from umr_agent.adapter.character_binding import verify_character_motion_binding
from umr_agent.validation.assets import confine_path

ENTRYPOINT_FOR_SOURCE = {
    SourceType.SMPLX: "scripts/humanoid_retarget_pipeline.py",
    SourceType.HUMANOID_CHARACTER: "scripts/humanoid_retarget_pipeline_character.py",
}


@dataclass(frozen=True, slots=True)
class CommandSpec:
    executable: Path
    argv: tuple[str, ...]
    cwd: Path

    def as_process_args(self) -> list[str]:
        return [str(self.executable), *self.argv]


def build_umr_command(
    plan: ExecutionPlan,
    *,
    python_executable: Path,
    umr_repository: Path,
    project_root: Path,
) -> CommandSpec:
    """Map a sealed plan to fixed executable + argv; never construct shell text."""
    if plan.plan_hash is None or plan.plan_hash != plan.compute_hash():
        raise ValueError("execution plan must be sealed with a valid plan_hash")
    expected_entrypoint = ENTRYPOINT_FOR_SOURCE.get(plan.motion.source_type)
    if plan.pipeline.entrypoint != expected_entrypoint:
        raise ValueError("entrypoint is not allowlisted for this motion source")
    if plan.motion.source_type == SourceType.HUMANOID_CHARACTER and plan.pipeline.defaults_path:
        raise ValueError("the character pipeline does not accept --defaults")

    repository = umr_repository.resolve(strict=False)
    executable = python_executable.resolve(strict=False)
    entrypoint = confine_path(repository, plan.pipeline.entrypoint)
    config_path = confine_path(project_root, plan.pipeline.robot_config_path)

    if plan.motion.source_type == SourceType.HUMANOID_CHARACTER:
        verify_character_motion_binding(
            plan, config_path=config_path, umr_repository=repository
        )

    argv = [str(entrypoint), "--config", str(config_path)]
    if plan.pipeline.defaults_path:
        defaults_path = confine_path(project_root, plan.pipeline.defaults_path)
        argv.extend(["--defaults", str(defaults_path)])
    if plan.motion.source_type == SourceType.HUMANOID_CHARACTER:
        argv.extend(["--skip-view", "--dry-run"])

    return CommandSpec(executable=executable, argv=tuple(argv), cwd=repository)
