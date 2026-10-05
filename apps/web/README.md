# Private G1 workstation app

The Next.js app runs on `127.0.0.1:3000`, with FastAPI on `127.0.0.1:8000`.
The browser talks only to same-origin Next.js routes; the server adds the local
token for FastAPI. FastAPI calls fixed scripts in the Ubuntu UMR checkout via WSL.
This execution workflow is private to the workstation; the Cloudflare showcase
is a separate, read-only application.

In Windows CMD, from the agent repo root, once per checkout:

```bat
uv sync --extra dev
uv run python scripts\setup_local_token.py
uv run python scripts\configure_wsl_assets.py --distro Ubuntu --root /home/zubair_ahmed/projects/UMR
cd apps\web
npm install
cd ..\..
```

Keep the three registered Ubuntu manifests and correspondence slots in place.
Start FastAPI and Next.js in separate CMD windows from their respective directories:

```bat
uv run python scripts\run_local_api.py
```

```bat
cd apps\web
npm run dev
```

Open http://127.0.0.1:3000. Ask for a supported G1 motion, such as "Retarget
the run motion to Unitree G1." Select **Use this motion for a G1 run** on the
proposal. The page fills in the selected motion and a new attempt ID. Choose
a three-frame test or full motion, then select **Generate run files**. The
Ubuntu worker verifies the registered inputs and writes `character_config.json`
and `plan.json` in a new attempt directory. Review the source, output, and
frame count, confirm that you want to start this local computation, then run it. The
UI sends the exact plan hash behind the scenes; the Ubuntu worker rechecks
that plan, runs once, and writes its status and
logs under `~/projects/UMR/output/agent_attempts/<attempt>/`. The page polls
status and invokes the read-only diagnosis after a verified completion. Use a
new attempt ID and select full motion for the full clip. You can also fill in the
run form without using chat. Only the three allowlisted Character motions are
connected to this local runner; a proposal for another motion cannot create run
files. The separate **Inspect an older run** form is collapsed because completed
runs are diagnosed automatically; open it only to look up a past attempt.
Planning catalog notes and file hashes are optional technical details. Quality warnings are
measured findings; the page does not claim foot contact or visual checks were run.

If the page refreshes, it restores the current attempt ID from this tab and
reads the verified plan and status from Ubuntu again. An older prepared attempt
can also be recovered by typing its ID and selecting **Resume existing attempt**.
Approval is never restored: review the plan and confirm it again. File hashes
are under **Advanced audit details** after the Start button; users do not need
to copy or enter them.

After copying new script files into the Windows repo, restart FastAPI. If the
Ubuntu registration changes because a generated viewer XML is updated, register
the selected motion again before preparing the next attempt. Existing attempts
remain immutable.
