# Verified input review: G1 spin kick

## Purpose and boundaries

The user describes a motion request. The planner selects catalog identifiers and a worker
count. The user can then request a verified input review for the **specific tested pair**:
Unitree G1 and Humanoid Character Spin Kick. A fresh WSL subprocess loads the G1 model,
rechecks registered file hashes (144 in the tested checkout), including correspondence
slots, and reports the UMR commit and source hashes.

The API accepts only the IDs and bounded worker count, never a client-supplied filesystem
path, command, or source hash. It checks the expected G1 XML, robot config, motion path,
sequence key, and slots path before composing an `InputReview`. The review digest is SHA-256 of a
canonical JSON representation of the returned fields. Changing the motion bytes, the
registered mesh inventory, slots bytes, commit, or worker count changes the review digest.

The review is returned to the browser for inspection only. It has `executable: false`.
It is neither a sealed `ExecutionPlan` nor a human approval, and it is not persisted.
Another robot or motion cannot be reviewed with the current binding. A worker must
reverify assets immediately before future execution even when an earlier review passed.

## Execution-plan schema and remaining work

`RobotSpec.tpose_qpos_path` can now be null for the tested G1 layout. In that case
the plan requires a registered SHA-256 for the entire robot config. Validation reads
`robot.tpose_qpos` and `robot.xml` from that config, checks the pose hash and MJCF
binding, and fails if either file changes. The example plan now describes the tested
Character layout; its SHA-256 values are placeholders, not registered assets.
Before creating an executable plan, replace those values with verified evidence,
bind correspondence slots/training settings, define runtime resource limits that fit
the CPU-only host, and enforce all preconditions in the Ubuntu worker.

## Input and output

| Input | Where it comes from |
| --- | --- |
| Robot ID, motion ID, worker count | Catalog proposal returned to browser |
| File checksums and Git commit | Newly verified Ubuntu registration manifest |
| Fixed G1 paths and source format | Server allowlist |

Output is an `InputReview` with file paths, key checksums, UMR commit, file count,
requested worker count, a review SHA-256, and `executable: false`. If WSL is unavailable,
the hashes change, or the IDs do not match the tested pair, the request fails closed.

This check does not judge the quality of the one-epoch training result or motion preview.
