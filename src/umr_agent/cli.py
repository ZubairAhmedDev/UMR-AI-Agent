from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

import yaml

from umr_agent.adapter.cache import derive_correspondence_key
from umr_agent.agent.contracts import AgentCatalog, AgentRequest
from umr_agent.agent.models import RuleBasedPlannerModel
from umr_agent.agent.providers.ollama import ModelUnavailable, OllamaPlannerModel
from umr_agent.agent.service import AgentService
from umr_agent.domain.models import ExecutionPlan
from umr_agent.validation.assets import Severity, validate_motion_asset, validate_robot_asset


def _load_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        if path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(stream)
        else:
            data = json.load(stream)
    if not isinstance(data, dict):
        raise TypeError(f"expected an object in {path}")
    return data


def inspect_environment(config_path: Path) -> tuple[dict[str, Any], bool]:
    config = _load_mapping(config_path)
    checks: list[dict[str, Any]] = []

    python_ok = sys.version_info[:2] == (3, 12)
    checks.append(
        {
            "name": "agent_python",
            "status": "pass" if python_ok else "fail",
            "observed": platform.python_version(),
            "expected": "3.12.x",
        }
    )

    path_fields = {
        "umr_repository": "directory",
        "umr_python": "file",
        "smpl_model_root": "directory",
        "artifact_root": "directory",
    }
    for field, expected_type in path_fields.items():
        raw = config.get(field)
        path = Path(raw).expanduser() if isinstance(raw, str) else None
        exists = bool(path and path.exists())
        type_ok = bool(
            path
            and exists
            and ((expected_type == "file" and path.is_file()) or (expected_type == "directory" and path.is_dir()))
        )
        checks.append(
            {
                "name": field,
                "status": "pass" if type_ok else "fail",
                "observed": str(path) if path else None,
                "expected": f"existing {expected_type}",
            }
        )

    commit = config.get("umr_git_commit")
    commit_ok = isinstance(commit, str) and 40 <= len(commit) <= 64 and all(
        ch in "0123456789abcdef" for ch in commit.lower()
    )
    checks.append(
        {
            "name": "umr_git_commit",
            "status": "pass" if commit_ok else "fail",
            "observed": commit,
            "expected": "pinned full hexadecimal commit",
        }
    )

    network_ok = config.get("network_enabled") is False
    checks.append(
        {
            "name": "worker_network",
            "status": "pass" if network_ok else "fail",
            "observed": config.get("network_enabled"),
            "expected": False,
        }
    )

    passed = all(item["status"] == "pass" for item in checks)
    return {"ok": passed, "config": str(config_path), "checks": checks}, passed


def validate_plan(plan_path: Path, project_root: Path) -> tuple[dict[str, Any], bool]:
    plan = ExecutionPlan.model_validate(_load_mapping(plan_path))
    robot_findings = validate_robot_asset(plan.robot, project_root, plan.pipeline)
    motion_findings = validate_motion_asset(plan.motion, project_root)
    findings = robot_findings + motion_findings
    blocked = any(item.severity == Severity.BLOCKING for item in findings)
    result = {
        "ok": not blocked,
        "plan_id": plan.plan_id,
        "computed_plan_hash": plan.compute_hash(),
        "sealed": plan.plan_hash == plan.compute_hash(),
        "correspondence_key": derive_correspondence_key(plan),
        "findings": [item.to_dict() for item in findings],
    }
    return result, not blocked


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="umr-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect the configured UMR runtime")
    inspect_parser.add_argument("--config", type=Path, required=True)

    validate_parser = subparsers.add_parser(
        "validate-plan", help="Validate a typed execution plan and its registered assets"
    )
    validate_parser.add_argument("plan", type=Path)
    validate_parser.add_argument("--project-root", type=Path, required=True)

    agent_parser = subparsers.add_parser(
        "agent-plan", help="Convert a natural-language goal into a bounded plan proposal"
    )
    agent_parser.add_argument("goal")
    agent_parser.add_argument("--catalog", type=Path, required=True)
    agent_parser.add_argument("--project-id", default="project-umr-demo")
    agent_parser.add_argument("--actor", default="local-user")
    agent_parser.add_argument("--provider", choices=("rules", "ollama"), default="rules")
    agent_parser.add_argument("--model", default="gemma3:4b")
    agent_parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    return parser


def run_agent_plan(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    catalog = AgentCatalog.model_validate(_load_mapping(args.catalog))
    model = (
        RuleBasedPlannerModel()
        if args.provider == "rules"
        else OllamaPlannerModel(model=args.model, base_url=args.ollama_url)
    )
    service = AgentService(model=model, catalog=catalog)
    reply = service.handle(
        AgentRequest(project_id=args.project_id, actor=args.actor, goal=args.goal)
    )
    return reply.model_dump(mode="json"), True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result, ok = inspect_environment(args.config)
        elif args.command == "validate-plan":
            result, ok = validate_plan(args.plan, args.project_root)
        else:
            result, ok = run_agent_plan(args)
    except (OSError, TypeError, ValueError, yaml.YAMLError, ModelUnavailable) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
