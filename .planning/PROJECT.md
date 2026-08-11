# taxi-mlops

## What This Is

A batch ML training pipeline on Kubeflow Pipelines v2, built as a 1-week hands-on mock project to gain applied experience in the exact stack a new job's JD requires — Kubeflow, pandas/numpy pipeline engineering, and production code quality (lint/test/CI) — before/while starting that role. Uses NYC TLC monthly trip records to predict trip duration (LightGBM regression), with the orchestration and engineering discipline as the actual point, not the model.

## Core Value

A fully-tested, CI-gated `lib/` of pandas feature logic, orchestrated by a real Kubeflow Pipelines v2 DAG (typed artifacts, custom component images, ParallelFor fan-out, conditional promotion, provable idempotent backfill) — the single most interview/onboarding-legible proof that the JD's "production-grade ML pipeline" skills are real, not tutorial-level.

## Business Context

- **Customer**: The user's own new employer — this is a self-directed skill-building project, not a paid engagement. Portfolio value is internal: proof of applied capability in the role's core tools.
- **Revenue model**: N/A — not monetized.
- **Success metric**: Can walk into the new job and speak concretely about having built (not just read about) a KFP v2 DAG with typed artifacts, cache-key invalidation, and idempotent backfill.
- **Strategy notes**: Scope is deliberately narrowed to what the JD emphasizes (Kubeflow pipelines, pandas/numpy, CI/CD code quality) over what it lists as secondary/nice-to-have (serving infra, front-end tooling, deep ML modeling).

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Monorepo skeleton (`components/`, `pipelines/`, `lib/`, `serving/`, `dashboard/`, `tests/`) with `uv` dependency management
- [ ] `ruff` + `mypy --strict` enforced on `lib/`
- [ ] `pytest` unit tests on `lib/` using tiny synthetic DataFrame fixtures, asserting exact output values
- [ ] GitHub Actions: lint → typecheck → test → build component images → push to GHCR, on every PR
- [ ] `pre-commit` config mirroring the CI checks
- [ ] `lib/` contains 100% of pandas/feature logic; `components/` are thin wrappers calling into `lib/`
- [ ] KFP standalone installed on k3d (not full multi-user Kubeflow/Istio)
- [ ] Training DAG: ingest(month) → validate → features → ParallelFor(months) → merge → train → evaluate → If(rmse < champion) → register
- [ ] Custom component images built in CI, referenced via `@dsl.container_component`/`@dsl.component(base_image=...)` pointing at GHCR tags (not `packages_to_install`)
- [ ] Typed artifacts (`Input[Dataset]`, `Output[Model]`, `Output[Metrics]`) passed between components — no raw S3 path strings
- [ ] `dsl.ParallelFor` fanning out ingest+validate across a month list, with parallelism capped for a 16GB laptop
- [ ] `dsl.If`/`dsl.OneOf` conditional model promotion — register only if the new model beats the MLflow-tracked champion
- [ ] `ExitHandler` for cleanup/run notification (failure path, not just happy path)
- [ ] Pipeline caching enabled, then deliberately invalidated by changing a component input — README documents what invalidates a cache key
- [ ] Backfill as a pipeline parameter (`start_month`/`end_month`); same backfill run twice produces byte-identical output (idempotency proof)
- [ ] pandera schema validation at the ingest boundary (bad month fails loudly)
- [ ] pandas/numpy optimization work at the feature stage: chunked reads, dtype downcasting, vectorized haversine distance instead of `.apply()` — before/after benchmark table in README
- [ ] Pipeline compiled to YAML in CI, attached as a release artifact
- [ ] README with architecture diagram; ADRs for non-obvious calls (why KFP over Airflow, why Parquet, why serving/dashboard were deferred)
- [ ] Dataset scoped to a 12-month window spanning a real drift event (e.g. 2019–2020, pre/post-COVID collapse) — not the full 2009–present history

### Out of Scope

- KServe InferenceService deployment, ONNX export, request batching, k6 load testing — deferred; the JD lists serving as secondary to pipeline/data engineering, and 1 week part-time doesn't fit it alongside a solid Phase 2. Document as "next steps" in README.
- Recurring cron run (`create_recurring_run`) and monthly batch-scoring pipeline — deferred with serving, since both build on the registered-model handoff that Phase 3 exists to prove.
- Streamlit/React monitoring dashboard — deferred; JD lists front-end tooling as nice-to-have only. Document as "next steps" in README.
- Full 2009–present TLC history ingestion — a 12-month window spanning a known drift event is enough to demonstrate fan-out, backfill, and drift-aware validation without the ingestion volume a 16GB laptop can't comfortably handle in a week.
- Full multi-user Kubeflow (Istio stack) — KFP standalone on k3d only; the multi-user stack teaches nothing relevant to the JD and burns a disproportionate amount of the time budget.
- Hyperparameter tuning — model is deliberately "boring" (LightGBM, no tuning theater); the orchestration is the point.
- Tip-percentage classification variant — trip-duration regression chosen as the single target to avoid splitting a 1-week budget across two framings.

## Context

- Written from an existing detailed personal plan document (`Inital_plan.txt`) covering a full 4-phase vision (repo/CI → Kubeflow core → serving → dashboard). This project starts with Phases 1–2 only; Phases 3–4 remain documented as future extension, not committed scope.
- Driven directly by a real job description the user is targeting/starting, not a hypothetical. JD core asks: production-grade ML pipeline/deployment experience, pandas/numpy, Kubeflow/batch pipelines, code quality (lint/test/CI). JD secondary asks: basic ML modeling, front-end for internal tooling.
- User knows these skills conceptually but has not hands-on applied them yet, especially Kubernetes — this project exists specifically to close that gap through building, not reading.
- Time budget: ~10-15 hours, part-time, within roughly 1 week.
- Hardware constraint: 16GB RAM laptop running k3d + KFP + MinIO + MLflow concurrently — parallelism and dataset size choices need to respect this.

## Constraints

- **Timeline**: ~1 week, ~10-15 hours part-time — scope is fixed at Phases 1-2 to fit.
- **Hardware**: 16GB RAM laptop — cap `ParallelFor` concurrency, avoid running the full Kubeflow multi-user stack, keep dataset window to 12 months.
- **Tech stack**: k3d + KFP v2 standalone + MinIO + MLflow + LightGBM; no full Kubeflow/Istio, no hyperparameter tuning frameworks.
- **Scope discipline**: Serving (KServe) and dashboard (Streamlit/React) are explicitly out of this milestone — resist pulling them back in under time pressure; they're documented as roadmap extensions instead.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Cut original 4-phase plan to Phases 1-2 only | 1-week/10-15h budget can't fit all 4 phases plus a React rebuild on a 16GB laptop; JD weights pipeline/data engineering over serving/front-end | — Pending |
| Trip-duration regression (not tip-percentage classification) | Avoids splitting a tight time budget across two framings; matches the plan doc's primary framing | — Pending |
| 12-month window spanning a drift event (not full 2009-present history) | Full history is 15+ years of monthly Parquet — infeasible to ingest/backfill on a 16GB laptop in this timeframe; a bounded window still delivers genuine drift signal | — Pending |
| KFP standalone on k3d, not full multi-user Kubeflow | Multi-user Istio stack costs a disproportionate amount of setup time and teaches nothing the JD asks for | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-11 after initialization*
