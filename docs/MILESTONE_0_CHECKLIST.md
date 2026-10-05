# Milestone 0 — Official UMR Baseline

The goal is one reproducible Unitree G1 run before building agent features.

## Environment

- [ ] Use a Linux or WSL2 host with Python 3.12.
- [ ] Clone the official UMR repository into a dedicated directory.
- [ ] Record the full tested Git commit.
- [ ] Create the official UMR environment and install its pinned requirements.
- [ ] Confirm the expected PyTorch and CUDA versions.
- [ ] Place licensed SMPL/SMPL-X model assets outside source control.
- [ ] Run `umr-agent inspect` and resolve every blocking finding.

## Official sample

- [ ] Locate the included Unitree G1 robot configuration.
- [ ] Locate the provided SMPL-X/Humanoid Character sample motion.
- [ ] Run the official UMR command without this agent.
- [ ] Preserve the exact command, environment snapshot, logs, duration, and exit code.
- [ ] Open the produced NPZ with the official viewer.
- [ ] Record result array names, shapes, frame count, and timing metadata.
- [ ] Store checksums for the robot, T-pose, source motion, config, and output.

## Exit criteria

- [ ] The same command succeeds twice from a clean workspace.
- [ ] Both result manifests identify the same pinned inputs and runtime revision.
- [ ] The output passes schema, finite-number, frame-count, and robot-width checks.
- [ ] A human reviews the motion in the official viewer.

