"""Long-running worker for persistent UMR motion workflows."""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

from umr_agent.agent.improvement_service import evaluate_improvement
from umr_agent.agent.workflow_worker import run_worker_pass
from umr_agent.api.wsl_attempts import read_attempt, write_attempt


DEFAULT_INTERVAL_SECONDS = 2.0


def environment() -> tuple[str, str | None, str, str]:
    execution_mode = os.getenv(
        "UMR_AGENT_EXECUTION_MODE",
        "wsl",
    )

    if execution_mode not in {"wsl", "native"}:
        raise ValueError("Invalid UMR_AGENT_EXECUTION_MODE")

    distro = os.getenv("UMR_AGENT_WSL_DISTRO") or None
    root = os.getenv("UMR_AGENT_WSL_ROOT")
    script = os.getenv("UMR_AGENT_WSL_SCRIPT")

    if not root:
        raise ValueError("UMR_AGENT_WSL_ROOT is required")

    if not script:
        raise ValueError("UMR_AGENT_WSL_SCRIPT is required")

    if execution_mode == "wsl" and not distro:
        raise ValueError(
            "UMR_AGENT_WSL_DISTRO is required in WSL mode"
        )

    return execution_mode, distro, root, script


def bridge_kwargs(execution_mode: str) -> dict[str, str]:
    if execution_mode == "wsl":
        return {}

    return {
        "execution_mode": execution_mode,
    }


def run_pass(
    *,
    execution_mode: str,
    distro: str | None,
    root: str,
    script: str,
) -> tuple[int, list[str]]:
    kwargs = bridge_kwargs(execution_mode)
    root_path = Path(root)

    def reader(attempt: str, action: str):
        return read_attempt(
            distro,
            root,
            script,
            attempt,
            action,
            **kwargs,
        )

    def launcher(**values):
        return write_attempt(
            distro,
            root,
            script,
            **values,
            **kwargs,
        )

    def evaluator(baseline_attempt: str):
        return evaluate_improvement(
            baseline_attempt,
            reader,
        )

    def renderer(attempt: str) -> None:
        attempts_root = (
            root_path
            / "output"
            / "agent_attempts"
        ).resolve()

        attempt_dir = (
            attempts_root
            / attempt
        ).resolve()

        if attempt_dir.parent != attempts_root:
            raise RuntimeError(
                "Preview attempt path escapes attempt directory"
            )

        render_script = (
            Path(__file__)
            .resolve()
            .with_name("render_attempt_preview.py")
        )

        umr_python = (
            root_path
            / ".venv"
            / "bin"
            / "python"
        )

        if not umr_python.is_file():
            raise RuntimeError(
                "UMR Python environment is unavailable"
            )

        if not render_script.is_file():
            raise RuntimeError(
                "Preview renderer script is unavailable"
            )

        render_env = os.environ.copy()
        render_env["MUJOCO_GL"] = "egl"

        completed = subprocess.run(
            [
                str(umr_python),
                str(render_script),
                "--umr-root",
                str(root_path),
                "--attempt",
                attempt,
            ],
            cwd=str(
                Path(__file__).resolve().parents[1]
            ),
            env=render_env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        if completed.returncode != 0:
            message = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or "unknown preview-rendering error"
            )

            raise RuntimeError(
                f"Preview rendering failed: {message}"
            )

        for filename in (
            "preview.png",
            "preview.mp4",
            "preview.json",
        ):
            artifact = attempt_dir / filename

            if (
                not artifact.is_file()
                or artifact.stat().st_size == 0
            ):
                raise RuntimeError(
                    f"Preview artifact is missing: {filename}"
                )

    results, errors = run_worker_pass(
        root_path,
        reader,
        launcher,
        evaluator,
        renderer,
    )

    for workflow in results:
        print(
            f"{workflow.workflow_id}: {workflow.state}",
            flush=True,
        )

    for error in errors:
        print(
            f"workflow error: {error}",
            file=sys.stderr,
            flush=True,
        )

    return len(results), errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one worker pass and exit.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
    )
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be positive")

    try:
        execution_mode, distro, root, script = environment()

        root_path = Path(root).resolve(strict=True)

        lock_dir = (
            root_path
            / "output"
            / "agent_workflows"
        )
        lock_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        lock_path = lock_dir / ".worker.lock"

        with lock_path.open("w", encoding="utf-8") as lock:
            try:
                fcntl.flock(
                    lock.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except BlockingIOError:
                print(
                    "Another workflow worker is already running.",
                    file=sys.stderr,
                )
                return 1

            while True:
                run_pass(
                    execution_mode=execution_mode,
                    distro=distro,
                    root=root,
                    script=script,
                )

                if args.once:
                    return 0

                time.sleep(args.interval)

    except (OSError, ValueError) as exc:
        print(
            f"Workflow worker failed: {exc}",
            file=sys.stderr,
        )
        return 1

    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
