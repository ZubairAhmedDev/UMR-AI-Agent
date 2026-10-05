from __future__ import annotations

from datetime import UTC, datetime

from umr_agent.domain.models import ExecutionPlan


def plan_data() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "plan_id": "plan-001",
        "project_id": "project-001",
        "robot": {
            "robot_id": "unitree-g1",
            "name": "Unitree G1",
            "mjcf_path": "assets/robot.xml",
            "root_body": "waist_yaw_link",
            "tpose_qpos_path": "assets/tpose.npy",
            "asset_sha256": "1" * 64,
            "tpose_sha256": "2" * 64,
        },
        "motion": {
            "motion_id": "motion-001",
            "source_type": "smplx",
            "path": "assets/motion.npz",
            "sha256": "3" * 64,
            "frames": 100,
            "fps": 30,
            "template_id": "smplx-neutral-v1",
        },
        "pipeline": {
            "entrypoint": "scripts/humanoid_retarget_pipeline.py",
            "robot_config_path": "configs/robot.json",
            "defaults_path": "configs/defaults.json",
        },
        "resources": {
            "cpus": 6,
            "memory_gib": 24,
            "gpu_ids": [0],
            "timeout_seconds": 14400,
        },
        "cache_policy": "reuse_if_exact",
        "requested_outputs": ["robot_motion_npz", "manifest", "quality_report", "logs"],
        "umr_git_commit": "a" * 40,
        "correspondence_settings_sha256": "4" * 64,
        "created_by": "test-user",
        "created_at": datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
    }


def make_plan(*, sealed: bool = False) -> ExecutionPlan:
    plan = ExecutionPlan.model_validate(plan_data())
    return plan.sealed() if sealed else plan

