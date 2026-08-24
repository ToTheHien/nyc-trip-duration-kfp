# Phase 3: Kubeflow Pipeline Core & Deployment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-24
**Phase:** 3-Kubeflow Pipeline Core & Deployment
**Areas discussed:** Cluster install risk handling, ExitHandler/notify task scope, MLflow deployment topology, idempotent backfill proof scope

---

## Cluster Install Risk Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Time-box + documented fallback | Attempt the install directly during execution with a firm time-box; if it overruns, fall back to ARCHITECTURE.md's documented "safe cut line" (fully-tested lib/CI + one working component-on-cluster demo = defensible partial progress). No separate spike phase. | ✓ |
| Dedicated spike first | Run /gsd-spike to validate the exact k3d+KFP install sequence (and confirm MinIO vs SeaweedFS bundling) before committing to a plan structure. | |
| No special handling | Proceed straight into normal phase planning, treat install issues as they arise mid-execution. | |

**User's choice:** Time-box + documented fallback
**Notes:** None — recommended option selected directly.

---

## ExitHandler / Notify Task Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal structured log line | A single structured log/print line (status, run id, rmse if applicable) — satisfies REQ-B9 with the least new surface area. | ✓ |
| Log line + run-summary artifact | Also writes a small human-readable summary file/artifact the README can screenshot or link. | |

**User's choice:** Minimal structured log line
**Notes:** None — research-recommended option selected directly.

---

## MLflow Deployment Topology

| Option | Description | Selected |
|--------|-------------|----------|
| In-cluster from the start | Deploy MLflow + dedicated MinIO pod inside k3d per ARCHITECTURE.md's default recommendation — more authentic "production-grade" story, more RAM pressure alongside KFP's own pods. | ✓ |
| Host process to start | Run `mlflow server` as a plain host process (SQLite backend + dedicated MinIO pod for artifacts) — same client code either way; can move in-cluster later. | |

**User's choice:** In-cluster from the start
**Notes:** User chose the more "textbook"/authentic option over the RAM-conservative fallback. STACK.md's host-process fallback remains available as a documented escape hatch if RAM pressure becomes severe during execution (captured in CONTEXT.md D-12).

---

## Idempotent Backfill Proof Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Small subset (2-3 months) | Proves determinism just as rigorously with a fraction of the wall-clock time/RAM risk — REQ-B8's acceptance criterion doesn't require the full window. | ✓ |
| Full 12-month window | Run the entire pinned window twice for the idempotency proof — more impressive as a demo, doubles real ingest+training time. | |

**User's choice:** Small subset (2-3 months)
**Notes:** None — recommended option selected directly.

---

## Claude's Discretion

- Exact k3d/KFP/MinIO/MLflow install commands and manifest choices beyond STACK.md's Installation section.
- Internal `components/` module structure (`@dsl.component(base_image=...)` vs `@dsl.container_component`).
- Whether to extend the existing tracer `components/ingest/main.py`/Dockerfile in place vs. replace it.
- Exact input changed to demonstrate cache-key invalidation (REQ-B10).
- Registered model name, MLflow experiment naming, per-component resource requests/limits.
- Notify task's exact log line format/fields.

## Deferred Ideas

None — discussion stayed within Phase 3 scope. No scope-creep suggestions arose.
