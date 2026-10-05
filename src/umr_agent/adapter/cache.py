from __future__ import annotations

import hashlib
import json

from umr_agent.domain.models import ExecutionPlan


def derive_correspondence_key(plan: ExecutionPlan) -> str:
    """Create the only supported cache identity for correspondence reuse."""
    payload = {
        "source_type": plan.motion.source_type.value,
        "source_template_id": plan.motion.template_id,
        "robot_asset_sha256": plan.robot.asset_sha256,
        "tpose_sha256": plan.robot.tpose_sha256,
        "root_body": plan.robot.root_body,
        "correspondence_settings_sha256": plan.correspondence_settings_sha256,
        "umr_git_commit": plan.umr_git_commit,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

