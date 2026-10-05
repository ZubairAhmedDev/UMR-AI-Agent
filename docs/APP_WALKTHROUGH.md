# Application Walkthrough

## What you can do now

Enter “Retarget the spin kick to Unitree G1 using 6 workers.” The page sends a request to
`POST /api/agent/proposals`. The API returns a non-executable proposal containing the robot,
motion, source format, worker count, and warnings about missing registered files.

The page is a planning preview. The output is **not** a robot trajectory. It does not call the
official UMR scripts yet.

## Data flow

```text
Browser text → POST /api/agent/proposals → planner model → strict ModelSelection
             → AgentService checks catalog IDs → AgentReply → browser proposal card
```

## Functions and why they exist

| Component | Input | Output | Reason |
| --- | --- | --- | --- |
| `propose()` in `apps/web/src/lib/api.ts` | Goal and mode | `AgentReply` | Centralizes browser HTTP handling. |
| `create_app()` in `src/umr_agent/api/app.py` | Configuration | FastAPI app | Owns routes, catalog dependency, and local web origin. |
| `load_catalog()` | Local catalog file | Validated `AgentCatalog` | Keeps robot/motion identifiers within one configured source. |
| `OllamaPlannerModel.select()` | Goal and catalog | `ModelSelection` | Gets structured identifiers from a local model. |
| `AgentService.handle()` | Model selection | Proposal or clarification | Rejects IDs outside the catalog and flags unregistered assets. |

The offline rules mode follows the same `AgentService` checks, making it useful to debug the
interface even when Ollama is not running.

## What can fail

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Catalog unavailable | API is stopped or catalog path is wrong | Open `http://127.0.0.1:8000/api/health` and inspect `UMR_AGENT_CATALOG`. |
| Browser network error | API is stopped or frontend origin differs | Start API and use `http://127.0.0.1:3000`. |
| Ollama unavailable | Local Ollama process/model is absent | Start Ollama, pull `gemma3:4b`, retry. |
| Agent requests clarification | Motion or robot absent/ambiguous | Use a listed catalog name or alias. |
| Missing asset warning | Example catalog contains descriptions only | Register real robot/motion files in a future milestone. |

## Next implementation dependency

First run the official UMR sample successfully in its own pinned environment. Then implement
real asset registration and validation, convert proposals into sealed plans, and connect the
isolated worker. Only after those gates pass should the UI offer approval and job submission.
