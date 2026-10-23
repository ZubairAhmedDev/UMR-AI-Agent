"""Render a read-only PNG and MP4 preview for one completed UMR attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np

from inspect_character_attempt import inspect_attempt
from run_character_attempt import attempt_dir


WIDTH = 640
HEIGHT = 480
MAX_RESULT_BYTES = 1024 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def inside(parent: Path, child: Path) -> Path:
    parent = parent.resolve(strict=True)
    child = child.resolve(strict=True)

    if child != parent and parent not in child.parents:
        raise ValueError("Preview input escapes the expected directory")

    return child


def load_motion(
    result_path: Path,
) -> tuple[np.ndarray, float]:
    if (
        not result_path.is_file()
        or result_path.stat().st_size > MAX_RESULT_BYTES
    ):
        raise ValueError(
            "Motion result is missing or too large"
        )

    with np.load(
        result_path,
        allow_pickle=False,
    ) as archive:
        qpos = np.asarray(
            archive["qpos"],
        ).copy()

        fps_values = np.asarray(
            archive["fps"],
        ).reshape(-1)

    if (
        qpos.ndim != 2
        or qpos.shape[0] < 1
        or not np.issubdtype(qpos.dtype, np.number)
        or not np.isfinite(qpos).all()
    ):
        raise ValueError(
            "Motion qpos is invalid"
        )

    if fps_values.size != 1:
        raise ValueError(
            "Motion FPS is invalid"
        )

    fps = float(fps_values[0])

    if not math.isfinite(fps) or fps <= 0:
        raise ValueError(
            "Motion FPS must be positive"
        )

    return qpos, fps


def render_preview(
    root: Path,
    attempt: str,
) -> dict:
    root = root.resolve(strict=True)

    # inspect_attempt validates the existing plan hash
    # before we trust paths from plan.json.
    plan = inspect_attempt(
        root,
        attempt,
        "plan",
    )

    status = inspect_attempt(
        root,
        attempt,
        "status",
    )

    if status["state"] != "completed":
        raise ValueError(
            "Preview requires a completed attempt"
        )

    if status["plan_hash"] != plan["plan_hash"]:
        raise ValueError(
            "Completed attempt does not match its plan"
        )

    directory = attempt_dir(
        root,
        attempt,
    ).resolve(strict=True)

    result_path = inside(
        directory,
        Path(plan["output"]),
    )

    viewer_xml = inside(
        root,
        root / plan["viewer_xml"],
    )

    qpos, fps = load_motion(
        result_path,
    )

    model = mujoco.MjModel.from_xml_path(
        str(viewer_xml),
    )

    if model.nq != qpos.shape[1]:
        raise ValueError(
            f"Motion width {qpos.shape[1]} "
            f"does not match model nq {model.nq}"
        )

    data = mujoco.MjData(model)

    preview_png = directory / "preview.png"
    preview_mp4 = directory / "preview.mp4"
    preview_json = directory / "preview.json"

    temp_png = directory / "preview.tmp.png"
    temp_mp4 = directory / "preview.tmp.mp4"
    temp_json = directory / "preview.json.tmp"

    for path in (
        temp_png,
        temp_mp4,
        temp_json,
    ):
        path.unlink(missing_ok=True)

    preview_frame = qpos.shape[0] // 2

    # Use a free camera that follows the humanoid root.
    # This keeps locomotion motions such as running in frame instead
    # of leaving the robot behind as it translates through the scene.
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(camera)
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.azimuth = 135.0
    camera.elevation = -15.0
    camera.distance = 3.0

    renderer = None
    writer = None

    try:
        renderer = mujoco.Renderer(
            model,
            height=HEIGHT,
            width=WIDTH,
        )

        writer = imageio.get_writer(
            temp_mp4,
            fps=fps,
        )

        for frame_index, positions in enumerate(qpos):
            data.qpos[:] = positions
            mujoco.mj_forward(
                model,
                data,
            )

            # qpos[0:3] is the floating-base root XYZ for this
            # verified G1 model. Follow it so translating motions remain
            # visible throughout the preview.
            camera.lookat[0] = float(positions[0])
            camera.lookat[1] = float(positions[1])
            camera.lookat[2] = float(positions[2])

            renderer.update_scene(
                data,
                camera=camera,
            )

            frame = renderer.render()

            if frame_index == preview_frame:
                imageio.imwrite(
                    temp_png,
                    frame,
                )

            writer.append_data(
                frame,
            )

    finally:
        if writer is not None:
            writer.close()

        if renderer is not None:
            renderer.close()

    if not temp_png.is_file():
        raise ValueError(
            "Preview PNG was not created"
        )

    if not temp_mp4.is_file():
        raise ValueError(
            "Preview MP4 was not created"
        )

    temp_png.replace(
        preview_png,
    )

    temp_mp4.replace(
        preview_mp4,
    )

    metadata = {
        "schema_version": 1,
        "attempt": attempt,
        "plan_hash": plan["plan_hash"],
        "motion_id": plan["motion_id"],
        "profile": plan.get(
            "profile",
            "baseline",
        ),
        "frames": int(
            qpos.shape[0],
        ),
        "fps": fps,
        "width": WIDTH,
        "height": HEIGHT,
        "preview_frame": preview_frame,
        "result_sha256": (
            status.get("result") or {}
        ).get("sha256"),
        "preview_png": preview_png.name,
        "preview_mp4": preview_mp4.name,
        "preview_png_sha256": sha256(
            preview_png,
        ),
        "preview_mp4_sha256": sha256(
            preview_mp4,
        ),
    }

    temp_json.write_text(
        json.dumps(
            metadata,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temp_json.replace(
        preview_json,
    )

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--umr-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--attempt",
        required=True,
    )

    args = parser.parse_args()

    try:
        result = render_preview(
            args.umr_root,
            args.attempt,
        )

        print(
            json.dumps(
                result,
                indent=2,
            )
        )

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        parser.exit(
            1,
            f"Preview failed: {exc}\n",
        )


if __name__ == "__main__":
    main()
