# Private G1 attempt inspection

This update connects the local Next.js interface to the existing Ubuntu G1
attempt records. It does not change the Cloudflare site and cannot prepare,
approve, execute, or rerun a job.

## Data flow

1. The operator enters an existing attempt ID such as `g1-run-full-001` in the
   local web app at `http://127.0.0.1:3000`.
2. Next.js validates the ID and forwards it with the existing private API token.
3. FastAPI calls the fixed `inspect_character_attempt.py` script inside Ubuntu.
   The script reads `plan.json` and `run.json` and validates the plan hash.
4. For a completed attempt only, the loop requests `diagnose_result`. The
   Ubuntu script uses the existing MuJoCo diagnosis, which checks the output
   file hash against the recorded result and reads the correct playback XML.
5. The loop finishes in at most three decisions: status, diagnosis, summary.
   The response includes the underlying measurement report and tool trace.

The default **Measured summary** uses deterministic rules. **Local Ollama**
requests schema-constrained JSON from `gemma3:4b` at the API's configured local
Ollama URL. Even if Ollama proposes an action, the stage gate rejects skipping
the status or diagnosis. An unfinished attempt is reported without diagnosis.
The LLM's explanation is advisory; use the attached measured report for facts.

## Install and check

Extract the patch ZIP at the **root** of the Windows agent repository. The ZIP
contains only the files changed for this update; it does not contain `.env`,
assets, NPZ results, or node_modules. In Windows CMD:

```cmd
cd /d "C:\UMR\UMR_agent\UMR_AI_Agent_PROD\UMR_AI_Agent_Starter_Repo"
uv run python -m unittest discover -s tests -v
uv run python scripts\configure_wsl_assets.py --root /home/zubair_ahmed/projects/UMR
uv run python scripts\run_local_api.py
```

Keep the API terminal running. In a second Windows CMD:

```cmd
cd /d "C:\UMR\UMR_agent\UMR_AI_Agent_PROD\UMR_AI_Agent_Starter_Repo\apps\web"
npm run typecheck
npm run dev
```

Open `http://127.0.0.1:3000` and use **Inspect completed G1 attempt** with
`g1-run-full-001`. Try `g1-vault-full-001` and `g1-spin-full-002` too. The
status and diagnosis are re-read from Ubuntu every request. To test the
Ollama choice, start Ollama on the API machine and make sure `gemma3:4b` is
available. Leave the mode on **Measured summary** if Ollama is unavailable.

## Limits

- The local API and Next.js are bound to localhost. Do not expose either to the
  internet using a tunnel; the token is service authentication, not user login.
- Diagnosis reads completed results only. No foot contact, skating, or visual
  quality verdict is produced.
- The public Cloudflare bot remains a separate read-only explainer over
  deliberately published run records. It does not access the private API.
- New attempts still require the existing local `prepare` / exact plan hash
  approval / `execute` workflow. A durable job queue and user authorization
  are future integration work.
