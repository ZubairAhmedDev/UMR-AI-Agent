# Run the registered G1 spin kick from Ubuntu

This is the first controlled execution path. The existing web app proposes and
reviews inputs. This CLI worker takes the same registered G1, spin kick, and
correspondence slots and performs one attempt. It does not accept a model-selected
file path. The exact plan is saved and must be approved by supplying its hash.

## Data flow

1. `prepare` rereads and verifies `output/g1_asset_registration.json`, checks
   the UMR checkout for tracked changes, and checks the exact G1 config, motion,
   XML, and slots.
2. It writes `output/agent_attempts/<name>/character_config.json` with absolute
   input paths and a unique output NPZ path. It writes `plan.json` with hashes of
   the registered manifest, generated config, UMR Character entrypoint, defaults,
   and worker code. No UMR command runs at this step.
3. A person reviews `plan.json` and supplies its `plan_hash` to `execute`. The
   worker rechecks the inputs and plan immediately before starting UMR. It uses
   `--stage retarget --skip-view`, reusing the registered slots; the six requested
   correspondence workers do not apply to this stage.
4. It writes stdout and stderr logs and inspects the NPZ for a nonempty 36-wide
   finite `qpos` array and a positive fps value. It records the generated viewer
   XML SHA-256 as output provenance. `run.json` reports completion
   or failure. Joint limits, contact, and temporal motion quality are not judged.

Run these commands in **Ubuntu**, from the official UMR checkout. Use a new
attempt name each time. The first attempt uses three frames for a quick proof:

```bash
cd ~/projects/UMR
./.venv/bin/python /mnt/c/UMR/UMR_agent/UMR_AI_Agent_PROD/UMR_AI_Agent_Starter_Repo/scripts/run_character_attempt.py \
  prepare --umr-root . --attempt g1-spin-smoke-001 --max-frames 3
```

Read `output/agent_attempts/g1-spin-smoke-001/plan.json`. Check its `argv`,
`output`, `max_frames`, and hashes. Only after that review, copy its complete
`plan_hash` into the following command (replace `<HASH>`):

```bash
./.venv/bin/python /mnt/c/UMR/UMR_agent/UMR_AI_Agent_PROD/UMR_AI_Agent_Starter_Repo/scripts/run_character_attempt.py \
  execute --umr-root . --attempt g1-spin-smoke-001 --approve-plan-hash <HASH>
```

Read `output/agent_attempts/g1-spin-smoke-001/run.json`. If it says `completed`,
the file named by `plan.json` exists and passed basic contract checks. If it
says `failed`, inspect `stderr.log`; for a verification failure, inspect both
logs and the output. An attempt cannot be run twice.

For the **entire spin kick**, use a new name and `--max-frames 0`, prepare and
review again, then approve that new plan hash. The full run could take much
longer on CPU. The worker times out after 30 minutes. Do not reuse the smoke
hash for the full run.

This is a local trusted-input demonstration, not a deployed multiuser worker.
The web app does not yet show the execution controls or output report. The
quality agent and robot-general execution path are subsequent work.
