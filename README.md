# UMR AI Agent

This repository is the implementation baseline for a safe AI-assisted workflow around the
official Unified Motion Retargeting (UMR) project. The first target is the workflow visible in
UMR Studio: validate a Unitree G1 T-pose, prepare or reuse correspondence, retarget a reference
motion, track progress, verify the resulting trajectory, and make it available for review.

The language model is deliberately not part of milestone 1. A deterministic foundation must
first prove that inputs, plans, commands, state transitions, and output evidence are controlled.

## Current milestone

Implemented in this starter:

- Typed execution-plan, robot, motion, approval, and artifact schemas.
- A strict job state machine with explicit allowed transitions.
- Path-confinement, file, hash, and asset validators.
- A UMR command builder that returns an argument list and never a shell string.
- A deterministic correspondence cache key.
- Immutable result-manifest construction and verification.
- Environment-inspection and plan-validation CLI commands.
- A bounded agent-planning layer with local Ollama and offline development providers.
- A FastAPI service and Next.js web interface for a request-to-proposal workflow.
- An adapter preview for the official Humanoid Character pipeline. See
  [the character preview boundary](docs/CHARACTER_PREVIEW_BRIDGE.md) for the verified G1
  smoke test and the remaining checks before jobs can run.
- Unit tests that run without a live UMR installation.

Not implemented yet:

- Calling the official UMR runtime.
- PostgreSQL, Redis, the worker service, and real UMR output review.
- LLM tool routing.
- UMR job submission from the agent. The current agent can propose work but cannot execute it.
- Physical-robot control. This project will not expose a hardware-control API.

## Architecture rule

The future AI layer may interpret a request and propose a typed plan. Only deterministic code
may validate, approve, queue, execute, or accept results. A human must approve the exact plan
hash before a UMR job can run.

## Prerequisites

- Python 3.12 for this repository.
- `uv` for dependency and command management.
- A separate, tested official UMR environment for native execution. The baseline documented by
  UMR uses Python 3.12 and PyTorch 2.4.1 with CUDA 12.1.
- Linux or WSL2 for the eventual local worker. The agent UI can be developed on Windows, but the
  UMR worker should run in a pinned Linux environment.
- Licensed model assets such as SMPL-X must stay outside this repository.

## Start locally

```bash
uv sync --extra dev
uv run python -m unittest discover -s tests -v
uv run umr-agent inspect --config configs/runtime.example.yaml
uv run umr-agent validate-plan examples/execution_plan.example.json \
  --project-root ./example-project
```

Try the bounded agent without an LLM:

```bash
uv run umr-agent agent-plan \
  "Retarget the spin kick to Unitree G1 using 6 workers" \
  --catalog examples/catalog.example.json \
  --provider rules
```

Use the same contract with a local Ollama model:

```bash
ollama serve
ollama pull gemma3:4b
uv run umr-agent agent-plan \
  "Retarget the spin kick to Unitree G1 using 6 workers" \
  --catalog examples/catalog.example.json \
  --provider ollama \
  --model gemma3:4b
```

The agent output is a non-executable proposal. It does not call UMR. Robot and motion assets must
be registered, validated, converted into a sealed `ExecutionPlan`, and approved before a future
worker may run them.

## Run the application

In the extracted repository, generate one random token for the local API and web server:

```bash
uv sync --extra dev
uv run python scripts/setup_local_token.py
```

This writes `.env.agent.local` and `apps/web/.env.local`. Both are ignored by Git, and the
token is never sent to the browser. Open two terminals. Terminal 1 starts the Python API:

```bash
uv run python scripts/run_local_api.py
```

Terminal 2 starts the web interface:

```bash
cd apps/web
npm install
npm run dev
```

Open http://127.0.0.1:3000. Use **Offline demo** to test the full interface without a running
model. **Local Ollama** calls the locally running `gemma3:4b` model through the API. Browser
requests stay on the Next.js origin; its server forwards catalog and proposal requests with the
local token. Direct calls to `http://127.0.0.1:8000/api/catalog` require an `Authorization:
Bearer <token>` header. The sample catalog describes motions and robots
but does not include their real asset files yet; the interface correctly warns about that.

### Register the tested G1 inputs inside Ubuntu

From `~/projects/UMR` in Ubuntu, use the Python from the official UMR `.venv`. The
registration script is stored in the new agent repository on the Windows drive:

```bash
cd ~/projects/UMR
./.venv/bin/python /mnt/c/UMR/UMR_agent/UMR_AI_Agent_PROD/UMR_AI_Agent_Starter_Repo/scripts/register_umr_assets.py \
  --umr-root . --out output/g1_asset_registration.json
./.venv/bin/python /mnt/c/UMR/UMR_agent/UMR_AI_Agent_PROD/UMR_AI_Agent_Starter_Repo/scripts/register_umr_assets.py \
  --umr-root . --out output/g1_asset_registration.json --verify
```

The script loads G1 XML with MuJoCo and records the Git revision, spin kick file,
robot config, correspondence slots, and every file in the G1 asset directory with size and SHA-256. It
never unpickles the motion. Changes make later verification fail. The manifest is
a local inventory, not an approved execution plan or proof of output quality.
The manifest is now schema version 3; register again after installing the update.
An untracked generated `spin_kick_g1.floating_mjcf.xml` is excluded from source
registration only when no other robot XML references it. Completed attempts
should record the generated viewer model separately as output provenance.
Since the planning API runs on Windows and cannot verify Ubuntu files at request
time without a bridge, the catalog still says `registered: false`.

To enable the read-only bridge from Windows CMD, run this once from the agent repo
root (the `--root` value defaults to this example Ubuntu checkout):

```bat
uv run python scripts\configure_wsl_assets.py --root /home/zubair_ahmed/projects/UMR
uv run python scripts\run_local_api.py
```

Restart the API if it was already running. The web page then has a **Verify files**
button in its Ubuntu assets section. Clicking it asks the Windows API to run the
same `--verify` check inside Ubuntu, returning a short status and file count.
The browser cannot supply a command or path, and the status endpoint requires the
existing server token. Failure to launch WSL, load MuJoCo, or match the registered
files is reported as a failed check. The catalog's `registered` flags belong to
the planning preview; the local G1 runner verifies Ubuntu files again during
preparation and execution. Do not flip catalog flags by hand.

For the private G1 workflow, ask for a supported motion and select **Use this
motion for a G1 run**. The page fills in a new attempt ID and motion. Choose
three frames or full motion, then select **Generate run files**. The worker
creates a verified configuration and exact execution plan in Ubuntu; the user
confirms the local computation before it starts. See [private G1 workstation
app](apps/web/README.md) for the full flow.

On Windows PowerShell, run the same commands from your extracted folder. Install Python 3.12,
`uv`, and Node.js first. The eventual native UMR worker belongs in Linux or WSL2.

This local token authenticates the web server to the planning API. It does not identify a
person or enforce project permissions. Keep both servers on `127.0.0.1`; add user login,
per-project authorization, and HTTPS before deployment or job execution. Running
`setup_local_token.py` again rotates the token, so restart both services afterward.

Until dependencies are synced, the tests can also run against the current interpreter:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The environment inspection is expected to report missing paths until the official UMR checkout,
its Python environment, and licensed model directory are configured.

## Repository map

```text
apps/                 web application and notes for API and worker services
configs/              runtime and robot examples
deploy/               local service definitions added in later milestones
docs/                 implementation backlog and smoke-test checklist
examples/             example typed execution plan
src/umr_agent/         API, agent, domain, validators, adapter, artifacts, CLI
tests/                 deterministic unit tests
```

## First end-to-end success condition

Milestone 0 is complete when a pinned official UMR revision retargets the included sample motion
to Unitree G1 and the result opens successfully in the official viewer. Do not add the LLM layer
before that smoke test and the deterministic adapter tests pass.

## Agent safety boundary

The model receives only the user's goal and a catalog of allowed identifiers. Its response must
match a strict schema containing an intent, robot ID, motion ID, worker count, and short
explanation. Unknown identifiers and extra fields are rejected. The model cannot provide a shell
command, filesystem path, Python code, or executable action through this contract.

## How the first application slice works

1. `apps/web/src/app/page.tsx` sends the typed request to the API.
2. `src/umr_agent/api/app.py` loads the configured catalog and chooses the requested planner.
3. `src/umr_agent/agent/service.py` checks selected IDs against catalog entries, then returns
   a clarification or review-only proposal.
4. The web interface shows the proposal and any missing-asset warnings. There is no run button.

See `docs/APP_WALKTHROUGH.md` for inputs, outputs, dependencies, and debugging steps.
