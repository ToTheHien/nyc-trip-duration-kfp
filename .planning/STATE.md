---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 1
current_phase_name: Repo Foundation & CI Quality Gates
status: planning
stopped_at: Phase 1 context gathered
last_updated: "2026-08-14T07:05:09.777Z"
last_activity: 2026-08-14
last_activity_desc: ROADMAP.md and STATE.md created (3 phases, 28/28 requirements mapped)
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-11)

**Core value:** A fully-tested, CI-gated `lib/` of pandas feature logic, orchestrated by a real Kubeflow Pipelines v2 DAG (typed artifacts, custom component images, ParallelFor fan-out, conditional promotion, provable idempotent backfill) — the single most interview/onboarding-legible proof that the JD's "production-grade ML pipeline" skills are real, not tutorial-level.

**Current focus:** Phase 1 — Repo Foundation & CI Quality Gates

## Current Position

Phase: 1 of 3 (Repo Foundation & CI Quality Gates)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-08-14 — ROADMAP.md and STATE.md created (3 phases, 28/28 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Milestone scope cut to Phases 1-2 of the original 4-phase vision (repo/CI + Kubeflow core only) — serving and dashboard deferred, documented as roadmap extensions.
- Structure mode: horizontal layers, not vertical MVP slice — Phase 1 (repo/CI) must be fully complete and demonstrable before Phase 2 (lib/ engineering) begins, which must complete before Phase 3 (Kubeflow cluster/DAG) begins.
- Trip-duration regression via LightGBM chosen over tip-percentage classification, to avoid splitting the 1-week budget.
- 12-month window spanning a real drift event (2019-2020 pre/post-COVID) chosen over full TLC history, for laptop feasibility.
- KFP standalone on k3d chosen over full multi-user Kubeflow/Istio — the multi-user stack teaches nothing the JD asks for.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3 (k3d + KFP standalone install) is the highest-risk phase — research confidence on the exact install sequence is LOW (community threads only, no authoritative guide); spike early in Phase 3 to confirm the install path and whether the pinned KFP version bundles MinIO or defaults to SeaweedFS.
- 16GB RAM ceiling is tight for k3d + KFP + MinIO + MLflow + task pods — cap `ParallelFor` parallelism at 2-3 from the first version, budget ~10-11GB usable, and verify resource limits actually land on pods (KFP SDK/backend version-mismatch bug #11390 can silently drop them).
- Idempotent backfill requires deterministic, month-keyed output paths designed before the first ingest component is written (Phase 3) — retrofitting after `ParallelFor` is wired risks silent data corruption on re-run.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-08-14T07:05:09.770Z
Stopped at: Phase 1 context gathered
Resume file: /home/thehien/Projects/qai/mlops/.planning/phases/01-repo-foundation-ci-quality-gates/01-CONTEXT.md
