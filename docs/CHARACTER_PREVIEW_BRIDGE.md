# Character pipeline preview boundary

The official UMR repository and the agent app are separate projects. On the tested Ubuntu
checkout (`c56b630`), the Humanoid Character example successfully loaded the Unitree G1
model, built two 4,096-point clouds, produced correspondence slots, and retargeted three
spin-kick frames to a finite `(3, 36)` `qpos` array. The one-epoch CPU training result is a
workflow test; motion quality has not been established.

## Current adapter behavior

`build_umr_command` accepts sealed plans and maps a `humanoid_character` source to
`scripts/humanoid_retarget_pipeline_character.py`. It returns executable, argument-list,
and working-directory data; it does not start a process. The character arguments include
`--skip-view --dry-run`, so the returned command previews the official pipeline. This
entry point does not accept `--defaults`; character source defaults are selected by the
official character pipeline. A SMPL-X plan still maps to the existing generic pipeline.

The command builder now reads the pinned Character defaults and robot configuration,
merges their `motion` sections, and requires the resulting `motion.data` and
`motion.seq_key` to match the plan. It checks the selected `.pkl` bytes against the
plan's registered SHA-256 before returning a preview command. A different selected
motion needs a derived configuration that explicitly selects it. This is a read-only
guard, not an execution authorization. The worker still needs to bind config hashes,
resolve Windows/Ubuntu paths, reverify inputs, and check approval immediately before
running UMR.

`validate_motion_asset` now accepts `.pkl` for registered Humanoid Character motions. It
confines the path and compares file bytes to the registered SHA-256 checksum. It does not
deserialize the pickle or establish that the motion schema is valid; content parsing must
only occur in a trusted isolated worker after the input provenance is checked.

## Next implementation slice

1. Register a trusted Unitree G1 robot config and the exact source motion, including file
   checksums, UMR commit, and canonical Ubuntu paths. Bind the selected motion to the
   actual config input instead of relying on an unrelated default.
2. Resolve cross-OS paths through a configured Ubuntu/WSL worker; never pass a Windows
   `C:\\...` path to Linux Python.
3. Validate assets and preview output, then seal a plan and collect an approval for that
   plan hash and expiry.
4. Execute an allowlisted argv without a shell in an isolated attempt folder. Preserve
   stdout, stderr, exit status, and the produced NPZ file.
5. Verify `qpos` shape, numerical finiteness, frame rate, robot width, and input provenance
   before showing a result in the UI. Require a human to review motion in the viewer.

The verified manual smoke test used `sample_data/humanoid_character/humanoid_spinkick.pkl`,
`robot_configs/humanoid_retarget_unitree_g1_example.json`, and
`output/g1_cpu_smoke_512/correspondence_slots_final.npz` under `~/projects/UMR`. Those
outputs remain in the user's Ubuntu checkout and are not included in this starter package.

`prepare_character_preview` accepts a read-only input review whose hash includes
the registered slots file. It verifies config, XML, motion, and slots bytes, then
writes one derived config in `output/agent_attempts/<attempt>/`. That config sets
`robot.xml` to its verified absolute path, selects the reviewed motion and sequence,
pins `correspondence.slots`, and chooses an attempt-specific `retarget.out`. It
returns an argv with `--stage retarget --skip-view --dry-run`; it never starts UMR.
Requested correspondence workers apply when rebuilding slots. This retarget-only
preview reuses the registered slots.
