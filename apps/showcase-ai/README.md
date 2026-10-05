# G1 showcase with read-only AI assistant

This release replaces the static showcase with a Cloudflare Worker that serves
the same verified run records, a G1 pose viewer, and a Workers AI explanation
endpoint. The AI endpoint has no connection to the private UMR worker or job
runner. The robot viewer uses **computed MuJoCo body positions**, not a full
MJCF mesh renderer. Root translation is centered per frame; articulation and
height are preserved. It is a kinematic visual aid, not a contact or hardware
safety assessment.

## Install and export the actual G1 motion

Extract the supplied ZIP at the root of the Windows agent repository so that
`apps/showcase-ai/wrangler.jsonc` exists. Then open your Ubuntu terminal:

```bash
cd ~/projects/UMR
AGENT=/mnt/c/UMR/UMR_agent/UMR_AI_Agent_PROD/UMR_AI_Agent_Starter_Repo
./.venv/bin/python "$AGENT/apps/showcase-ai/export_g1_motions.py" \
  --umr-root . \
  --out "$AGENT/apps/showcase-ai/public/data/motions.json"
```

The exporter checks the three NPZ hashes against the published run records,
checks the run/vault playback XML hashes, and refuses unexpected frame counts,
FPS, non-finite poses, or qpos widths. Spin kick's playback XML hash was not
recorded with the completed run, so its current XML hash is included in the
export but cannot be compared to an earlier run record. It emits only body
positions, link indices, frame rate, and hashes. Run this again if the outputs
or the source records change.

If a hash check fails, do not replace the expected hashes by hand. Inspect the
result file and the completed `run.json` first.

## Test and deploy to the existing Worker

In **Windows PowerShell**, open the AI release directory:

```powershell
cd 'C:\UMR\UMR_agent\UMR_AI_Agent_PROD\UMR_AI_Agent_Starter_Repo\apps\showcase-ai'
node --test
npm install
npx wrangler login
npx wrangler deploy
```

`wrangler.jsonc` targets Worker `red-poetry-5c21`, matching the currently
shared URL. Confirm this is the Worker name in your Cloudflare dashboard before
deploying. Wrangler uploads both the public assets and the Worker script; a
static ZIP upload cannot attach the Workers AI binding. The Worker uses the
account's AI service and two rate limiting bindings. The free usage allowance
and available models depend on the Cloudflare account; watch usage in the
dashboard. The per-visitor limit is 5 questions/minute and the shared limit is
20 questions/minute per Cloudflare location; those limits reduce casual abuse
but are not a global quota guarantee.

Open the public URL and confirm the viewer has all three motions, the result
tabs work, and one assistant question receives a grounded answer. If the
viewer says the export is missing, check that `public/data/motions.json` was
written before deploying. If the assistant says it is unavailable, inspect
Workers AI entitlement, the bindings, and Worker logs. Keep `.env` files,
source pickles, raw NPZs, and your UMR checkout out of this release.

## Local checks

`node --test` tests the Worker with a mocked model and asset binding. It does
not test Cloudflare inference or MuJoCo on your Ubuntu installation. The
exporter runs through the actual motion and MuJoCo model when you execute the
Ubuntu command above. The site renders AI text with `textContent` and does not
retain chat history in the browser or Worker code.
