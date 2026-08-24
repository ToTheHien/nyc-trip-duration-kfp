# Phase 3: Kubeflow Pipeline Core & Deployment - Context

**Gathered:** 2026-08-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Stand up KFP v2 standalone on a local k3d cluster and wire the full training DAG end-to-end: `ingest(month) → validate → features → ParallelFor(months) → merge → train → evaluate → If(rmse < champion) → register`, using typed artifacts throughout (no raw string paths), custom CI-built/GHCR-hosted component images (no `packages_to_install`), `ParallelFor` fan-out capped at 2-3 concurrent months with `dsl.Collected` fan-in, `dsl.If` conditional promotion demonstrated both directions, an `ExitHandler` covering the failure path, caching enabled and deliberately invalidated once, and a provable idempotent backfill. Ends with the pipeline compiled to versioned YAML as a CI release artifact, and README/ADRs covering architecture, the 4 PROJECT.md Key Decisions, and deferred scope (KServe, dashboard, recurring runs). No new pandas/feature logic — `lib/` is already 100% complete from Phase 2; this phase is orchestration, cluster infrastructure, and proof-of-behavior only.

</domain>

<decisions>
## Implementation Decisions

### Cluster Install Risk Handling
- **D-10:** No dedicated `/gsd-spike` before planning, and no forced early-checkpoint gate. Attempt the k3d + KFP standalone install directly during phase execution with a firm time-box; if it overruns, fall back to `research/ARCHITECTURE.md`'s already-documented "safe cut line" — a fully-tested `lib/` + CI + at least one component proven end-to-end on the cluster is treated as defensible partial progress, not a failed phase. The plan should structure work so steps 1-5 of `ARCHITECTURE.md`'s Suggested Build Order (component image build/push proof) land before the riskiest step (full cluster install), matching that doc's own ordering rationale. — **Reversibility:** reversible — if the time-box is blown, the fallback is already fully specified; no rework needed to invoke it, just a scope-cut decision at execution time.

### ExitHandler / Notify Task Scope
- **D-11:** The `ExitHandler`'s notify component is intentionally minimal: a single structured log/print line (run status, run id, RMSE if applicable) satisfying REQ-B9. No run-summary artifact file, no webhook/desktop notification, no extra image beyond what's needed to prove the exit-path wiring works on both success and failure branches. Matches `research/ARCHITECTURE.md`'s explicit "don't over-invest here" guidance.

### MLflow Deployment Topology
- **D-12:** MLflow (tracking server + registry) deploys **in-cluster** on k3d from the start, per `research/ARCHITECTURE.md`'s default recommendation — not the RAM-pressure fallback (`mlflow server` as a host process) noted in `research/STACK.md`. Backed by a dedicated MinIO pod (its own bucket, not a second store, not KFP's internal SeaweedFS — per `research/PITFALLS.md` Pitfall 7 and `research/STACK.md`'s explicit "don't assume KFP bundles MinIO past 2.15" note) and a SQLite backend store (no separate Postgres pod, per `research/STACK.md`'s Installation guidance). If RAM pressure becomes severe during execution, `research/STACK.md`'s host-process fallback remains available as a documented escape hatch — same MLflow client code talks to either topology over a tracking URI, so this is a deployment-only change if invoked. — **Reversibility:** reversible — the fallback path is pre-researched and swapping topology is a deployment change only, not a code change.

### Idempotent Backfill Proof Scope
- **D-13:** REQ-B8's "run the same `start_month`/`end_month` range twice, prove byte-identical output" is demonstrated on a **small 2-3 month subset** of the pinned 12-month window, not the full window. A subset proves determinism just as rigorously (same code path, same checksum/diff methodology) while costing a fraction of the wall-clock time and RAM exposure of a full 12-month double-run on a 16GB laptop. — **Reversibility:** reversible — extending the proof to the full window later is additive, not a rework.

### Claude's Discretion
- Exact k3d/KFP/MinIO/MLflow install commands and manifest choices beyond what `research/STACK.md`'s Installation section already specifies (KFP 2.17.0, k3d v5.9.0, dedicated MinIO pod, `mlflow==3.15.1`) — executor follows STACK.md directly.
- Internal `components/` module structure and whether each stage uses `@dsl.component(base_image=...)` vs `@dsl.container_component` — planner's call per `research/ARCHITECTURE.md` Pattern 1/2 guidance.
- Whether the existing tracer component (`components/ingest/main.py`, `components/ingest/Dockerfile` — a CLI wrapper around `lib.months.month_range` from Phase 1's tracer slice, already CI-built and GHCR-published) is extended in place to become the real `ingest` component, or replaced — extending it is the obvious low-risk choice (preserves the proven Dockerfile/CI wiring) but left to planner/executor since it's a mechanical decision, not a vision one.
- Exact input changed to demonstrate cache-key invalidation (REQ-B10) — e.g. a LightGBM hyperparameter value, a component image tag bump, or a pipeline parameter — any documented single change satisfies the requirement; planner picks whichever is cleanest to demonstrate.
- Registered model name, MLflow experiment naming convention, exact resource `requests`/`limits` per component — left to executor, grounded in `research/PITFALLS.md`'s guidance to set explicit memory limits on every component (not just ParallelFor branches).
- Notify task's exact log line format/fields (D-11 sets scope, not exact shape).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Scope
- `.planning/REQUIREMENTS.md` §Category B (REQ-B1–B11), §Category E (REQ-E1–E3) — the locked requirements this phase implements
- `.planning/PROJECT.md` — project vision, constraints (10-15h/1 week, 16GB RAM), Key Decisions table (the 4 ADR-worthy decisions REQ-E2 requires write-ups for)

### Research
- `.planning/research/ARCHITECTURE.md` — full system architecture, the 4 architectural patterns (thin component/fat lib, typed artifacts, ParallelFor+Collected, If/OneOf+ExitHandler), data flow, anti-patterns, and the Suggested Build Order (§steps 1-10) this phase's plan structure should follow, including the explicit "safe cut line" fallback referenced by D-10
- `.planning/research/STACK.md` — pinned versions (KFP SDK/backend 2.17.0 matched pair, k3d v5.9.0, MLflow 3.15.1, MinIO dedicated pod), full Installation quick-start commands, the KFP-2.15-dropped-MinIO-default correction, and the RAM-pressure fallback options referenced by D-12
- `.planning/research/PITFALLS.md` — Pitfall 1 (k3d memory is advisory not a hard cgroup limit — budget ~10-11GB usable), Pitfall 2 (KFP SDK/backend version mismatch silently drops resource limits), Pitfall 7 (MinIO/MLflow storage-collision trap — reuse KFP's namespace pattern but a dedicated MinIO instance, use in-cluster service DNS never `localhost`), Pitfall 8 (business logic must not leak into `@dsl.component` bodies), plus the Integration Gotchas / Performance Traps tables
- `.planning/research/FEATURES.md` — MVP priority context (already consumed in Phase 1/2, re-check if scope questions arise)

### Prior Phase Decisions
- `.planning/phases/02-data-model-engineering-lib/02-CONTEXT.md` — D-06 (zone-centroid lookup table, not live shapefile geocoding), D-08 (chronological train/test split), D-09/D-09a (two-tier pandera validation: structural checks hard-fail, row-level quality checks pre-filter+log)
- `.planning/phases/01-repo-foundation-ci-quality-gates/01-CONTEXT.md` — D-01 (GHCR build+push runs on every PR), D-04 (pyproject.toml `pipeline`/`ml` optional-dependency groups already reserved)

### Roadmap
- `.planning/ROADMAP.md` §Phase 3 — goal statement and the 5 success criteria this phase must satisfy

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `components/ingest/main.py` + `components/ingest/Dockerfile` — an existing tracer CLI component (wraps `lib.months.month_range`) from Phase 1's tracer slice, already CI-built and pushed to GHCR (`.github/workflows/ci.yml` build-push job, tags `ghcr.io/<repo>/ingest:<sha>`). This is the proven pattern for "component image → CI build → GHCR push" that the rest of `components/` should replicate; see Claude's Discretion above re: extending it in place for the real `ingest` stage.
- All six `lib/` modules (`ingest.py`, `schemas.py`, `features.py`, `train.py`, `evaluate.py`, `registry.py`) are complete, 100%-tested, and zero-KFP-import — this phase only wraps them in thin `components/` bodies per `research/ARCHITECTURE.md` Pattern 1. `lib/registry.py`'s `ModelRegistry` class already implements alias-based promotion (`get_champion_rmse`, `tag_version_rmse`, `set_candidate`) against an injectable `MlflowClient` — Phase 3 is the first phase to inject a *real* client instead of a mock.
- `scripts/qa.sh` and `scripts/check_component_boundary.sh` — the existing lint/format/typecheck/test/boundary gate continues to apply; `check_component_boundary.sh` already enforces that no pandas logic lives under `components/`, directly backing D-11's constraint and Pitfall 8's guidance.

### Established Patterns
- Thin-component/fat-lib boundary (Phase 1/2) — `components/` bodies must stay I/O-glue only (read artifact `.path`, call one `lib/` function, write artifact `.path`/`.metadata`), mechanically enforced by `check_component_boundary.sh`.
- GHCR image tagging by commit SHA (`.github/workflows/ci.yml`, established in Phase 1) — Phase 3's `pipelines/train_pipeline.py` should reference the same tag scheme via `base_image=`/`ContainerSpec(image=...)`, never `packages_to_install`.

### Integration Points
- `.github/workflows/ci.yml` — needs new component-image build jobs (validate, features, train, evaluate, register, notify) alongside the existing `ingest` job, plus a new step compiling `pipelines/train_pipeline.py` to versioned YAML and attaching it as a release artifact (REQ-B11).
- `lib/registry.py` ↔ real MLflow tracking server — first real integration point; Phase 2 only exercised this against a mocked client.

</code_context>

<specifics>
## Specific Ideas

No additional specific implementation ideas beyond the four decisions above — the user confirmed a recommended or clearly-reasoned option for each of the four gray areas discussed (install-risk handling, notify-task scope, MLflow topology, backfill-proof scope), with no deviations or extra constraints raised during discussion.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 3 scope. No scope-creep suggestions arose.

</deferred>

---

*Phase: 3-Kubeflow Pipeline Core & Deployment*
*Context gathered: 2026-08-24*
