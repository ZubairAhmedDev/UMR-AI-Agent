# Implementation Backlog

## M0 — Pin and prove UMR

1. Complete the official Unitree G1 smoke-test checklist.
2. Capture one successful command and output contract as a golden fixture.
3. Document licensed-model placement and machine requirements.

## M1 — Deterministic domain foundation

1. Maintain versioned schemas for assets, plans, approvals, attempts, and manifests.
2. Complete validators for MJCF, T-pose dimensions, motion schema, units, and paths.
3. Complete state-transition, idempotency, cache-key, and manifest tests.
4. Add golden and malformed fixtures without committing licensed assets.

## M2 — UMR adapter and verifier

1. Pin an allowlist of official UMR entry points for the tested revision.
2. Materialize a sealed attempt workspace.
3. Execute without a shell, stream normalized events, and support cancellation.
4. Discover only declared output files under the attempt output root.
5. Verify NPZ arrays, numerical finiteness, time base, model width, and provenance.

## M3 — Durable service

1. Add PostgreSQL 16 migrations and repositories.
2. Add Redis 7 queueing, worker leases, reconciliation, and retry lineage.
3. Add FastAPI endpoints for projects, assets, plans, approvals, jobs, and results.
4. Add authentication, project authorization, quotas, audit events, and SSE progress.

## M4 — User interface and AI layer

1. Build the guided T-pose, motion, approval, progress, and result-review UI.
2. Extend the implemented provider-neutral planning client and structured output contract.
3. Expose typed read, plan, approval-request, submit, monitor, compare, and explain tools.
4. Add prompt-injection, authorization, traversal, and command-injection tests.

## M5 — Research workflow expansion

1. Add correspondence reuse, run comparison, batch operation, and custom robots.
2. Add MuJoCo or Viser viewer sessions for verified results.
3. Add regression dashboards and resource/cost reporting.
