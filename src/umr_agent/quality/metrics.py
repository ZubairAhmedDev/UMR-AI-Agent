"""File-contract checks for a known NPZ; motion metrics need robot and timing metadata."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from umr_agent.quality.contracts import Finding, OutputInspection, Severity


def inspect_motion_npz(path: str | Path, *, expected_width: int | None = None) -> OutputInspection:
    """Inspect a trusted local output file without deserializing Python objects.

    The caller must choose the file from a confined, verified output directory.
    In particular, never pass a path supplied by a model directly to this function.
    """
    if expected_width is not None and expected_width < 1:
        raise ValueError("expected_width must be positive")
    source = Path(path)
    findings: list[Finding] = []
    keys: tuple[str, ...]
    frames: int | None = None
    width: int | None = None
    fps: float | None = None
    with np.load(source, allow_pickle=False) as archive:
        keys = tuple(sorted(archive.files))
        if "qpos" not in archive:
            findings.append(Finding(check="qpos", severity=Severity.ERROR,
                                    message="Missing qpos array."))
        else:
            qpos = archive["qpos"]
            if qpos.ndim != 2 or qpos.shape[0] < 1 or qpos.shape[1] < 1:
                findings.append(Finding(check="qpos_shape", severity=Severity.ERROR,
                                        message="qpos must be a nonempty 2D array."))
            elif not np.issubdtype(qpos.dtype, np.floating) and not np.issubdtype(
                qpos.dtype, np.integer
            ):
                findings.append(Finding(check="qpos_dtype", severity=Severity.ERROR,
                                        message="qpos must contain numeric values."))
            else:
                frames, width = map(int, qpos.shape)
                if expected_width is not None and width != expected_width:
                    findings.append(Finding(check="qpos_width", severity=Severity.ERROR,
                                            message=f"Expected width {expected_width}; got {width}."))
                bad = np.flatnonzero(~np.isfinite(qpos).all(axis=1))
                if bad.size:
                    findings.append(Finding(
                        check="finite", severity=Severity.ERROR,
                        message=f"{bad.size} frame(s) contain non-finite qpos values.",
                        frame_indices=tuple(int(i) for i in bad[:20]),
                    ))
        if "fps" in archive:
            value = archive["fps"]
            if value.size != 1 or not np.issubdtype(value.dtype, np.number):
                findings.append(Finding(check="fps", severity=Severity.ERROR,
                                        message="fps must be one positive numeric value."))
            else:
                fps_candidate = float(value.reshape(-1)[0])
                if np.isfinite(fps_candidate) and fps_candidate > 0:
                    fps = fps_candidate
                else:
                    findings.append(Finding(check="fps", severity=Severity.ERROR,
                                            message="fps must be finite and positive."))
    return OutputInspection(
        npz_path=str(source), keys=keys, frame_count=frames, qpos_width=width, fps=fps,
        findings=tuple(findings),
        checks_not_run=("temporal_motion", "joint_limits", "foot_ground_contact"),
    )
