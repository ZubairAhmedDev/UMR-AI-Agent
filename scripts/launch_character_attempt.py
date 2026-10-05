"""Launch one approved Character attempt in Ubuntu without holding an HTTP request open."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from run_character_attempt import MOTIONS, attempt_dir, canonical, evidence, planned


def launch(root: Path, attempt: str, approved_hash: str) -> dict:
    root = root.resolve(strict=True)
    if not re.fullmatch(r"[0-9a-f]{64}", approved_hash):
        raise ValueError("Approval must be the exact 64-character plan hash")
    directory = attempt_dir(root, attempt).resolve(strict=True)
    record = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
    motion_id = record.get("motion_id")
    if motion_id not in MOTIONS:
        raise ValueError("Unsupported registered motion")
    manifest, manifest_hash = evidence(root, motion_id)
    profile = record.get("profile", "baseline")
    plan, config = planned(
        root,
        manifest,
        manifest_hash,
        attempt,
        record["max_frames"],
        motion_id,
        profile,
    )
    expected = hashlib.sha256(canonical(plan)).hexdigest()
    if (record != {**plan, "plan_hash": expected} or approved_hash != expected
            or (directory / "character_config.json").read_bytes() != config):
        raise ValueError("Approval does not match the current exact attempt plan")
    if (directory / "run.json").exists() or Path(plan["output"]).exists():
        raise ValueError("Attempt has already run or produced an output")
    marker = directory / "launch.json"
    # Exclusive creation is the cross-process guard against two approval clicks.
    with marker.open("x", encoding="utf-8") as stream:
        json.dump({"plan_hash": expected, "state": "launching"}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    command = [sys.executable, str(Path(__file__).with_name("run_character_attempt.py")),
               "execute", "--umr-root", str(root), "--attempt", attempt,
               "--approve-plan-hash", approved_hash]
    try:
        with (directory / "launch_stdout.log").open("wb") as stdout, \
                (directory / "launch_stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
    except OSError:
        marker.unlink()
        raise
    marker.write_text(json.dumps({"plan_hash": expected, "state": "queued",
                                  "pid": process.pid}) + "\n", encoding="utf-8")
    return {"attempt": attempt, "state": "queued", "plan_hash": expected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--umr-root", type=Path, required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--approve-plan-hash", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(launch(args.umr_root, args.attempt, args.approve_plan_hash)))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Launch failed: {exc}\n")


if __name__ == "__main__":
    main()
