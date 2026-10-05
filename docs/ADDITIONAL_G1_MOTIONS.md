# Add run and speed vault to the G1 Character demo

The bundled UMR sample includes `humanoid_spinkick.pkl`. MimicKit also names
`humanoid_run.pkl` and `humanoid_speed_vault.pkl` as motions for its humanoid
character. Download the **motion assets** from the link in the official
[MimicKit README](https://github.com/xbpeng/MimicKit#installation). The GitHub
source checkout alone does not include these binary clips. Use the files under
`data/motions/humanoid/`, not clips from other characters such as Go2 or G1.

In Ubuntu, copy the two downloaded files into:

```
~/projects/UMR/sample_data/humanoid_character/humanoid_run.pkl
~/projects/UMR/sample_data/humanoid_character/humanoid_speed_vault.pkl
```

Do not open a downloaded pickle to inspect it. Only use motion files from a
source you trust; Python pickle loading can execute code. Registration hashes
the bytes without deserializing them. The fixed UMR retarget process opens the
pickle after you approve a specific attempt.

From `~/projects/UMR`, with the updated scripts installed in your Windows
agent project, register each clip separately. Substitute the agent project path
if you installed it elsewhere:

```bash
AGENT=/mnt/c/UMR/UMR_agent/UMR_AI_Agent_PROD/UMR_AI_Agent_Starter_Repo
./.venv/bin/python "$AGENT/scripts/register_umr_assets.py" --umr-root . --motion sample_data/humanoid_character/humanoid_run.pkl --seq-key humanoid_run --out output/g1_asset_registration_run.json
./.venv/bin/python "$AGENT/scripts/register_umr_assets.py" --umr-root . --motion sample_data/humanoid_character/humanoid_speed_vault.pkl --seq-key humanoid_speed_vault --out output/g1_asset_registration_speed-vault.json
./.venv/bin/python "$AGENT/scripts/register_umr_assets.py" --umr-root . --out output/g1_asset_registration_run.json --verify --json
./.venv/bin/python "$AGENT/scripts/register_umr_assets.py" --umr-root . --out output/g1_asset_registration_speed-vault.json --verify --json
```

Prepare a three frame smoke attempt for run:

```bash
./.venv/bin/python "$AGENT/scripts/run_character_attempt.py" prepare --umr-root . --attempt g1-run-smoke-001 --motion-id run --max-frames 3
```

Review the printed plan, then pass **its own** `plan_hash` to execute:

```bash
./.venv/bin/python "$AGENT/scripts/run_character_attempt.py" execute --umr-root . --attempt g1-run-smoke-001 --approve-plan-hash THE_PRINTED_PLAN_HASH
```

Use `--motion-id speed-vault` and another attempt name for the vault. After a
smoke test succeeds, prepare a new attempt with `--max-frames 0` to process
all frames. Diagnose a completed attempt with
`./.venv/bin/python "$AGENT/scripts/diagnose_character_result.py" --umr-root . --attempt ATTEMPT_NAME`.

The example web catalog contains both names as `registered: false`. Change
that flag only in your own catalog after the clip is present, its manifest
verifies, and a smoke attempt succeeds. The web UI still proposes plans; this
local command is the controlled execution path. The exact output and generated
viewer XML names for new clips must be confirmed by their first UMR run. If
that run fails verification, check its `stderr.log` and the produced files in
`output/agent_attempts/ATTEMPT_NAME/` before changing the mapping.
