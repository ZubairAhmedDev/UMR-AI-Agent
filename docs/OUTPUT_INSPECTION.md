# Retargeted output: first validation slice

`quality.metrics.inspect_motion_npz(path, expected_width=36)` reads a **known local**
NPZ output and returns an `OutputInspection` report. Its inputs are the selected file
and the G1 `qpos` width established by the three-frame smoke test. It reports archive
keys, frame count, width, optional FPS, and file-contract errors. It never invents
FPS when that key is absent. Object arrays cannot be loaded as Python objects.

The caller must select the file under a verified attempt directory and check its
manifest first. Do not let an LLM supply this path. The inspector does not authorize
jobs, judge motion quality, or infer joint limits, root speed, or foot contact.
Its `checks_not_run` field makes these gaps visible.

Before implementing temporal metrics, inspect the actual UMR retarget output keys,
qpos layout, and time-base metadata in Ubuntu. Bind a longer trajectory to the
robot model and verified result manifest. The three-frame CPU smoke result only
proves an output was produced, not that the motion is good.

Run the new tests with `PYTHONPATH=src python -m unittest tests.test_output_inspection -v`.
After installing dependencies, run the complete project suite.
