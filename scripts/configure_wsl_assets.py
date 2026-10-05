"""Set the local Ubuntu checkout for asset checks and approved attempts."""

import argparse
import os
from pathlib import Path, PurePosixPath

from setup_local_token import update_env


def windows_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive or len(drive) != 1 or not drive.isalpha():
        raise ValueError("Agent repo must be located on a Windows drive")
    return str(PurePosixPath("/mnt", drive, *resolved.parts[1:]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/home/zubair_ahmed/projects/UMR")
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Run this configuration command in Windows CMD")
    linux_root = PurePosixPath(args.root)
    if not linux_root.is_absolute() or ".." in linux_root.parts or "\n" in args.root:
        parser.error("--root must be an absolute Ubuntu path without '..'")
    if not args.distro or any(ch in args.distro for ch in "\r\n="):
        parser.error("--distro is invalid")
    repo = Path(__file__).resolve().parents[1]
    token_file = repo / ".env.agent.local"
    if not token_file.is_file():
        parser.error("Run scripts/setup_local_token.py first")
    update_env(token_file, {
        "UMR_AGENT_WSL_DISTRO": args.distro,
        "UMR_AGENT_WSL_ROOT": str(linux_root),
        "UMR_AGENT_WSL_SCRIPT": windows_to_wsl(Path(__file__).with_name("register_umr_assets.py")),
    })
    print("Ubuntu bridge configured. Restart the Windows API; keep the web server running.")
