"""Record and recheck local UMR inputs inside the Linux UMR environment.

This manifest is evidence for a future worker, not permission to execute a job.
Never load the untrusted motion pickle during registration.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

SLOTS = "output/g1_cpu_smoke_512/correspondence_slots_final.npz"
GENERATED_VIEWER_XML = "assets/g1/spin_kick_g1.floating_mjcf.xml"
GENERATED_VIEWER_XMLS = (
    GENERATED_VIEWER_XML,
    "assets/g1/humanoid_run_g1.floating_mjcf.xml",
    "assets/g1/humanoid_speed_vault_g1.floating_mjcf.xml",
)


def inside(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"asset escapes UMR checkout: {path}")
    if not resolved.is_file():
        raise ValueError(f"not a regular file: {path}")
    return resolved


def record(root: Path, path: Path) -> dict[str, object]:
    file = inside(root, path)
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        first = stream.read(128)
        if first.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError(f"Git LFS pointer needs checkout: {file}")
        digest.update(first)
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {"path": file.relative_to(root).as_posix(), "sha256": digest.hexdigest(), "size": file.stat().st_size}


def create(root: Path, config_path: Path, motion_path: Path, sequence_key: str,
           slots_path: Path | None = None) -> dict[str, object]:
    config_path = inside(root, config_path)
    motion_path = inside(root, motion_path)
    slots_path = inside(root, slots_path or root / SLOTS)
    if slots_path.suffix.lower() != ".npz":
        raise ValueError("correspondence slots must be an .npz file")
    if motion_path.suffix.lower() != ".pkl":
        raise ValueError("Humanoid Character sample must be a .pkl file")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    xml_path = inside(root, config_path.parent / config["robot"]["xml"])
    if xml_path.suffix.lower() != ".xml":
        raise ValueError("robot XML must have .xml extension")

    # MuJoCo resolves XML includes and visual mesh dependencies. Its model load
    # catches missing or unexpanded LFS meshes before registration succeeds.
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(xml_path))
    if model.nbody < 2:
        raise ValueError("MuJoCo loaded no robot bodies")

    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
        raise ValueError("invalid UMR Git commit")

    # Hash the whole local robot asset directory because XML may indirectly
    # reference meshes, textures, and included XML from that directory.
    robot_files = sorted(p for p in xml_path.parent.rglob("*") if p.is_file())
    for generated_name in GENERATED_VIEWER_XMLS:
        generated = root / generated_name
        if generated in robot_files and generated != xml_path:
            tracked = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", generated_name],
                capture_output=True, text=True, check=False,
            ).returncode == 0
            referenced = any(
                generated.name in path.read_text(encoding="utf-8", errors="ignore")
                for path in robot_files if path.suffix.lower() == ".xml" and path != generated
            )
            if not tracked and not referenced:
                robot_files.remove(generated)
    files = sorted(
        (record(root, path) for path in {config_path, motion_path, slots_path, *robot_files}),
        key=lambda item: str(item["path"]),
    )
    return {
        "schema_version": 3,
        "umr_git_commit": commit,
        "umr_root": str(root),
        "robot_config": config_path.relative_to(root).as_posix(),
        "robot_xml": xml_path.relative_to(root).as_posix(),
        "motion": motion_path.relative_to(root).as_posix(),
        "correspondence_slots": slots_path.relative_to(root).as_posix(),
        "sequence_key": sequence_key,
        "mujoco_bodies": model.nbody,
        "files": files,
    }


def verify(root: Path, manifest: dict[str, object]) -> None:
    if manifest.get("schema_version") != 3:
        raise ValueError("unsupported registration manifest")
    fresh = create(
        root,
        root / str(manifest["robot_config"]),
        root / str(manifest["motion"]),
        str(manifest["sequence_key"]),
        root / str(manifest["correspondence_slots"]),
    )
    if fresh != manifest:
        raise ValueError("registered files, Git commit, or MuJoCo model changed; register again")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--umr-root", type=Path, required=True)
    parser.add_argument("--robot-config", default="robot_configs/humanoid_retarget_unitree_g1_example.json")
    parser.add_argument("--motion", default="sample_data/humanoid_character/humanoid_spinkick.pkl")
    parser.add_argument("--seq-key", default="humanoid_spinkick")
    parser.add_argument("--slots", default=SLOTS)
    parser.add_argument("--out", type=Path, default=Path("output/g1_asset_registration.json"))
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable verification result")
    args = parser.parse_args()
    root = args.umr_root.resolve(strict=True)
    try:
        if args.verify:
            manifest = json.loads(args.out.read_text(encoding="utf-8"))
            verify(root, manifest)
            if args.json:
                file_hashes = {item["path"]: item["sha256"] for item in manifest["files"]}
                canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                print(json.dumps({
                    "verified": True,
                    "robot_config": manifest["robot_config"],
                    "robot_xml": manifest["robot_xml"],
                    "motion": manifest["motion"],
                    "correspondence_slots": manifest["correspondence_slots"],
                    "sequence_key": manifest["sequence_key"],
                    "umr_git_commit": manifest["umr_git_commit"],
                    "file_count": len(manifest["files"]),
                    "mujoco_bodies": manifest["mujoco_bodies"],
                    "robot_config_sha256": file_hashes[manifest["robot_config"]],
                    "robot_xml_sha256": file_hashes[manifest["robot_xml"]],
                    "motion_sha256": file_hashes[manifest["motion"]],
                    "correspondence_slots_sha256": file_hashes[manifest["correspondence_slots"]],
                    "manifest_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                }))
            else:
                print(f"Verified {len(manifest['files'])} files for UMR {manifest['umr_git_commit'][:8]}")
        else:
            manifest = create(root, root / args.robot_config, root / args.motion,
                              args.seq_key, root / args.slots)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(f"Registered {len(manifest['files'])} files; MuJoCo bodies: {manifest['mujoco_bodies']}")
            print(f"Manifest: {args.out.resolve()}")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, ImportError) as exc:
        parser.exit(1, f"Registration failed: {exc}\n")


if __name__ == "__main__":
    main()
