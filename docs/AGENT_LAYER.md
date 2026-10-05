# Bounded AI Agent Layer

## Current responsibility

The agent currently converts one natural-language goal into a validated, non-executable plan
proposal. It does not have a submission tool and cannot start UMR.

```text
User goal
  -> planner model
  -> strict ModelSelection schema
  -> catalog resolution
  -> non-executable PlanProposal
  -> asset registration and validation (next)
  -> sealed ExecutionPlan and human approval (next)
  -> worker submission (later)
```

## Providers

- `RuleBasedPlannerModel` is an offline development provider. It matches catalog names and aliases
  so the complete policy path can be tested without an LLM.
- `OllamaPlannerModel` calls a local Ollama `/api/chat` endpoint and requests JSON matching the
  `ModelSelection` schema. The default example model is `gemma3:4b`.

Both providers feed the same `AgentService`, so provider output receives identical validation and
policy checks.

## Model output contract

The model may return only:

- intent;
- robot ID;
- motion ID;
- correspondence worker count from 1 through 12; and
- a short explanation.

The schema forbids extra fields. A command, filesystem path, code fragment, or arbitrary tool name
therefore cannot pass validation as an agent action.

## Catalog boundary

The model can select only identifiers already present in `AgentCatalog`. Unknown identifiers are
treated as unresolved and cause a clarification response. Catalog presence does not mean an asset
is ready: each item has a separate `registered` flag, and the agent warns when selected assets are
not registered.

## Approval boundary

`PlanProposal.executable` is always false. The later plan-builder must resolve registered asset
hashes and runtime configuration into an `ExecutionPlan`, seal its SHA-256 plan hash, and collect a
matching, unexpired human approval. Only the future worker-submission tool will accept that sealed
and approved plan.

## Local demonstration

```bash
uv run umr-agent agent-plan \
  "Retarget the spin kick to Unitree G1 using 6 workers" \
  --catalog examples/catalog.example.json \
  --provider rules
```

Replace `rules` with `ollama` after starting Ollama and installing the selected local model.

