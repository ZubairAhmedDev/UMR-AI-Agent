"""Read-only status and diagnosis for a single registered G1 Character attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Expected a JSON object")
    return data


def inspect_attempt(root: Path, attempt: str, action: str = "status") -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", attempt):
        raise ValueError("Invalid attempt name")
    if action not in {"plan", "status", "diagnose"}:
        raise ValueError("Unsupported read-only action")
    root = root.resolve(strict=True)
    directory = (root / "output/agent_attempts" / attempt).resolve(strict=True)
    if directory.parent != (root / "output/agent_attempts").resolve(strict=True):
        raise ValueError("Attempt escapes the UMR output directory")
    plan = _read_json(directory / "plan.json")
    canonical = json.dumps({key: value for key, value in plan.items() if key != "plan_hash"},
                           sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = hashlib.sha256(canonical).hexdigest()
    if plan.get("attempt") != attempt or plan.get("plan_hash") != expected:
        raise ValueError("Prepared plan hash does not match the attempt")
    if action == "plan":
        return plan
    run_path = directory / "run.json"
    run = _read_json(run_path) if run_path.exists() else None
    if run is not None and run.get("plan_hash") != expected:
        raise ValueError("Run does not match the approved plan")
    state = run.get("state") if run else "prepared"
    if run is None and (directory / "launch.json").exists():
        launch = _read_json(directory / "launch.json")
        if launch.get("plan_hash") != expected:
            raise ValueError("Launch does not match the prepared plan")
        pid = launch.get("pid")
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
                state = "queued"
            except ProcessLookupError:
                state = "failed_launch"
            except PermissionError:
                state = "queued"
        else:
            state = "queued"
    if state not in {"prepared", "queued", "running", "completed", "failed", "failed_launch", "failed_verification"}:
        raise ValueError("Unknown attempt state")
    if action == "status":
        return {
            "attempt": attempt,
            "state": state,
            "plan_hash": expected,
            "motion_id": plan.get("motion_id", "spin-kick"),
            "profile": plan.get("profile", "baseline"),
            "result": run.get("result") if state == "completed" else None,
        }
    if state != "completed":
        raise ValueError("A matching completed attempt is required for diagnosis")
    # Import only for diagnosis: the status command does not require MuJoCo.
    from diagnose_character_result import diagnose

    return diagnose(root, attempt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--umr-root", type=Path, required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--action", choices=("plan", "status", "diagnose"), default="status")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_attempt(args.umr_root, args.attempt, args.action)))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Inspection failed: {exc}\n")


if __name__ == "__main__":
    main()
