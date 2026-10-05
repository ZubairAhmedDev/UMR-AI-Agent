"""Export three verified UMR G1 trajectories as public, read-only body positions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np


INPUTS = {
    "spin-kick": ("g1-spin-full-002/spin_kick_g1.npz", "assets/g1/spin_kick_g1.floating_mjcf.xml"),
    "run": ("g1-run-full-001/humanoid_run_g1.npz", "assets/g1/humanoid_run_g1.floating_mjcf.xml"),
    "speed-vault": ("g1-vault-full-001/humanoid_speed_vault_g1.npz", "assets/g1/humanoid_speed_vault_g1.floating_mjcf.xml"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export(root: Path, records_path: Path) -> dict:
    records = json.loads(records_path.read_text(encoding="utf-8"))
    by_id = {record["id"]: record for record in records["runs"]}
    exported = {"schema_version": 1, "robot": "Unitree G1 (29 DoF)", "runs": {}}
    for motion_id, (result_relative, xml_relative) in INPUTS.items():
        record = by_id[motion_id]
        result_path = root / "output/agent_attempts" / result_relative
        xml_path = root / xml_relative
        result_hash = sha256(result_path)
        xml_hash = sha256(xml_path)
        if result_hash != record["result_sha256"]:
            raise ValueError(f"{motion_id}: result SHA-256 differs from completed record")
        if record.get("viewer_xml_sha256") and xml_hash != record["viewer_xml_sha256"]:
            raise ValueError(f"{motion_id}: playback XML SHA-256 differs from completed record")
        model = mujoco.MjModel.from_xml_path(str(xml_path))
        data = mujoco.MjData(model)
        with np.load(result_path, allow_pickle=False) as contents:
            qpos = contents["qpos"]
            fps = float(np.asarray(contents["fps"]).reshape(-1)[0])
            if qpos.shape != (record["frames"], model.nq) or model.nq != 36:
                raise ValueError(f"{motion_id}: unexpected G1 qpos dimensions")
            if fps != record["fps"] or not np.isfinite(qpos).all():
                raise ValueError(f"{motion_id}: fps or pose values disagree with verified record")
            links = [(int(model.body_parentid[i]), i) for i in range(1, model.nbody)
                     if int(model.body_parentid[i]) != 0]
            positions = []
            for pose in qpos:
                data.qpos[:] = pose
                mujoco.mj_forward(model, data)
                xyz = np.asarray(data.xpos).copy()
                # Keep the body centered in the viewer, while preserving height and articulation.
                xyz[:, :2] -= xyz[1, :2]
                positions.append(np.round(xyz, 4).tolist())
        exported["runs"][motion_id] = {
            "title": record["title"], "frames": record["frames"], "fps": fps,
            "result_sha256": result_hash, "viewer_xml_sha256": xml_hash,
            "center": [0, 0, 0.85], "links": links, "positions": positions,
        }
        print(f"{motion_id}: {len(positions)} frames, {model.nbody} G1 bodies")
    return exported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--umr-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--records", type=Path, default=Path(__file__).resolve().parent / "public/data/runs.json")
    args = parser.parse_args()
    result = export(args.umr_root.resolve(), args.records)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {args.out} ({args.out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
