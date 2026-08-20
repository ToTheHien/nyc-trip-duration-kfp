---
gsd_state_version: 1.0
milestone: v1.0
current_phase: 2
current_phase_name: Data & Model Engineering (lib/)
status: planning
stopped_at: Phase 2 context gathered
last_updated: "2026-08-20T04:37:15.933Z"
last_activity: 2026-08-20
last_activity_desc: Phase 1 complete, transitioned to Phase 2
state_head: e2d08fc95c67c412a070c8c3db022ba4e9f1937a
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 3
  completed_plans: 3
milestone_name: milestone
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-11)

**Core value:** A fully-tested, CI-gated `lib/` of pandas feature logic, orchestrated by a real Kubeflow Pipelines v2 DAG (typed artifacts, custom component images, ParallelFor fan-out, conditional promotion, provable idempotent backfill) — the single most interview/onboarding-legible proof that the JD's "production-grade ML pipeline" skills are real, not tutorial-level.

**Current focus:** Phase 1 — Repo Foundation & CI Quality Gates

## Current Position

Phase: 2 of 3 (Data & Model Engineering (lib/))
Plan: Not started
Status: Ready to plan
Last activity: 2026-08-20 — Phase 1 complete, transitioned to Phase 2

Progress: [███████░░░] 67%

## Performance Metrics

**Velocity:**

- Total plans completed: 3
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 35 min | 5 tasks | 16 files |
| Phase 01 P02 | 40 min | 3 tasks | 7 files |
| Phase 01 P03 | 40 min | 2 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Milestone scope cut to Phases 1-2 of the original 4-phase vision (repo/CI + Kubeflow core only) — serving and dashboard deferred, documented as roadmap extensions.
- Structure mode: horizontal layers, not vertical MVP slice — Phase 1 (repo/CI) must be fully complete and demonstrable before Phase 2 (lib/ engineering) begins, which must complete before Phase 3 (Kubeflow cluster/DAG) begins.
- Trip-duration regression via LightGBM chosen over tip-percentage classification, to avoid splitting the 1-week budget.
- 12-month window spanning a real drift event (2019-2020 pre/post-COVID) chosen over full TLC history, for laptop feasibility.
- KFP standalone on k3d chosen over full multi-user Kubeflow/Istio — the multi-user stack teaches nothing the JD asks for.
- [Phase ?]: D-05 (resolved pre-dispatch): public repo ToTheHien/nyc-trip-duration-kfp, public GHCR packages — Phase 3 needs zero registry-credential wiring; GHCR namespace ghcr.io/tothehien/nyc-trip-duration-kfp/ingest (lowercase, per GHCR requirement).
- [Phase ?]: Single-root pyproject.toml with D-04 optional-dependency groups (dev/pipeline/ml) chosen over a uv workspace, per plan 01-01.
- [Phase ?]: scripts/qa.sh is the single shared entrypoint for lint/format/typecheck/test/boundary, invoked identically by CI and pre-commit, resolving REPO_ROOT from its own path so the verdict is caller-location-independent.
- [Phase ?]: check_component_boundary.sh mechanically enforces REQ-A6 (thin-component/fat-lib) via git-tracked-file scanning with a non-vacuous-scan guard; runs in both CI's lint job and every pre-commit run.
- [Phase 1]: [Phase 1] Branching override: ci-proof/* branches created from and merged into development (not master), per repo's branching-workflow rule; ci-proof/clean merged via PR #7 (abd8249).
- [Phase 1]: [Phase 1] scripts/qa.sh boundary now echoes 'Running scripts/check_component_boundary.sh' before delegating, so a failing CI log names the script (Rule 3 fix, needed to prove REQ-A6 gate attribution).

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3 (k3d + KFP standalone install) is the highest-risk phase — research confidence on the exact install sequence is LOW (community threads only, no authoritative guide); spike early in Phase 3 to confirm the install path and whether the pinned KFP version bundles MinIO or defaults to SeaweedFS.
- 16GB RAM ceiling is tight for k3d + KFP + MinIO + MLflow + task pods — cap `ParallelFor` parallelism at 2-3 from the first version, budget ~10-11GB usable, and verify resource limits actually land on pods (KFP SDK/backend version-mismatch bug #11390 can silently drop them).
- Idempotent backfill requires deterministic, month-keyed output paths designed before the first ingest component is written (Phase 3) — retrofitting after `ParallelFor` is wired risks silent data corruption on re-run.
- PR #1 (tracer/ci-proof -> master) is open, mergeable, CI green (run 32210503873), but merge is blocked pending human action — the Claude Code auto-mode permission classifier denied gh pr merge as a mutating main-branch action. Merge via https://github.com/ToTheHien/nyc-trip-duration-kfp/pull/1 to bring the CI workflow (with its lowercase-GHCR-tag fix) onto master.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-08-20T04:37:15.911Z
Stopped at: Phase 2 context gathered
Resume file: .planning/phases/02-data-model-engineering-lib/02-CONTEXT.md
