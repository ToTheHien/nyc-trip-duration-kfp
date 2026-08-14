# Roadmap: taxi-mlops

## Overview

This milestone builds a batch ML training pipeline on Kubeflow Pipelines v2 as a hands-on skill-proof for a real job description, using horizontal-layer sequencing to de-risk the stated skill gap (Kubernetes) last. Phase 1 lays down the monorepo skeleton and CI quality gates so every later line of code is lint/type/test-gated from day one. Phase 2 writes and proves 100% of the pandas/numpy/LightGBM/MLflow logic in `lib/` — ingest, schema validation, vectorized feature engineering, training, evaluation, registry client — entirely offline, with a benchmark table as evidence. Phase 3 is the highest-risk, least-familiar work: standing up k3d + KFP standalone + MinIO + MLflow, wrapping the proven `lib/` logic in thin CI-built components, and assembling the full DAG with typed artifacts, capped `ParallelFor` fan-out, conditional champion/candidate promotion, a provable idempotent backfill, failure-path `ExitHandler`, cache-invalidation demo, and final documentation (architecture diagram, ADRs, benchmark table, "Next Steps"). Each phase is independently demoable, so if the 10-15h/1-week budget runs tight, work can stop after any phase and still leave a defensible, working artifact.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Repo Foundation & CI Quality Gates** - Monorepo skeleton, `uv`, `ruff`/`mypy --strict`/`pytest`, GitHub Actions CI, `pre-commit`, and the thin-component/fat-lib architectural boundary — all provable before any pandas or Kubernetes work begins.
- [ ] **Phase 2: Data & Model Engineering (lib/)** - 100% of pandas/numpy feature logic, pandera schema validation, vectorized haversine + dtype downcasting + benchmark table, LightGBM training, and an MLflow registry client wrapper — written and unit-tested entirely offline, no cluster required.
- [ ] **Phase 3: Kubeflow Pipeline Core & Deployment** - k3d + KFP standalone + MinIO + MLflow stood up; `lib/` wrapped in CI-built thin components; full DAG assembled with typed artifacts, capped `ParallelFor` fan-out, conditional promotion, idempotent backfill, `ExitHandler`, cache-invalidation demo, and final README/ADRs.

## Phase Details

### Phase 1: Repo Foundation & CI Quality Gates
**Goal**: A reviewer can clone the repo, install with one command, and see automated quality gates protecting `lib/` on every PR — before a single line of pandas or KFP logic exists.
**Depends on**: Nothing (first phase)
**Requirements**: REQ-A1, REQ-A2, REQ-A3, REQ-A4, REQ-A5, REQ-A6
**Success Criteria** (what must be TRUE):
  1. `uv sync` installs cleanly from a fresh clone, with the full directory layout (`components/`, `pipelines/`, `lib/`, `serving/`, `dashboard/`, `tests/`) in place.
  2. `ruff` and `mypy --strict` run clean on `lib/` both locally and in CI; a deliberately broken lint/type rule fails the CI job at that stage.
  3. `pytest` runs against `lib/` using synthetic DataFrame fixtures asserting exact output values; GitHub Actions blocks a PR with a broken `lib/` change at the failing stage, while a clean PR produces a pushed GHCR-tagged component image.
  4. `pre-commit run --all-files` produces the same pass/fail result as CI on the same commit.
  5. No pandas/DataFrame transformation logic exists inside any `components/` module (grep-verifiable) — 100% of such logic lives in `lib/`.
**Plans**: TBD

Plans:
- [ ] 01-01: TBD (refined during planning)

### Phase 2: Data & Model Engineering (lib/)
**Goal**: 100% of the pandas/numpy/modeling logic is written, correctness-proven via unit tests, and speed-proven via a benchmark table — all without touching Kubernetes, de-risking "is the math right" independently of the harder Kubernetes unknown.
**Depends on**: Phase 1
**Requirements**: REQ-C1, REQ-C2, REQ-C3, REQ-C4, REQ-C5, REQ-D1, REQ-D2, REQ-D3
**Success Criteria** (what must be TRUE):
  1. Ingest logic reads the pinned 12-month NYC TLC window (spanning a documented pre/post-COVID drift event) via chunked/streaming reads, never a single unbounded `read_parquet` into memory.
  2. A pandera schema with real `Check`s validates the ingest boundary and fails loudly (non-zero exit, logged reason) on a malformed/schema-drifted month.
  3. Feature engineering uses a vectorized haversine implementation (not `.apply()`) and downcasts dtypes (float64→float32, category dtypes); README contains a concrete before/after benchmark table with time and memory numbers.
  4. A single, fixed LightGBM config trains a trip-duration regression model, with no tuning framework or sweep code present anywhere in the repo.
  5. An MLflow registry client wrapper in `lib/` uses `set_registered_model_alias` (`@champion`/`@candidate`) and is independently unit-testable with a mocked client.
**Plans**: TBD

Plans:
- [ ] 02-01: TBD (refined during planning)

### Phase 3: Kubeflow Pipeline Core & Deployment
**Goal**: A real KFP v2 DAG runs end-to-end on a local k3d cluster — typed artifacts throughout, capped fan-out, conditional champion/candidate promotion, a provable idempotent backfill, and a documented failure path — with the architecture and key decisions fully written up.
**Depends on**: Phase 2
**Requirements**: REQ-B1, REQ-B2, REQ-B3, REQ-B4, REQ-B5, REQ-B6, REQ-B7, REQ-B8, REQ-B9, REQ-B10, REQ-B11, REQ-E1, REQ-E2, REQ-E3
**Success Criteria** (what must be TRUE):
  1. KFP standalone runs on k3d (`kubectl get pods -n kubeflow` shows it running, no Istio namespace present); every component image is CI-built, GHCR-hosted, and verified pull-able from inside the cluster (not via `packages_to_install`).
  2. The full DAG (ingest→validate→features→ParallelFor(months)→merge→train→evaluate→If(rmse<champion)→register) compiles and a real run reaches `register` or a documented skip-branch, using typed artifacts (`Input[Dataset]`/`Output[Model]`/`Output[Metrics]`) throughout with no raw string paths, `ParallelFor` fan-out capped at 2-3 concurrent months, and `dsl.Collected` fan-in before training.
  3. Conditional promotion works both directions: a deliberately worse model is not registered, and a genuinely better one is — both demonstrated.
  4. Running the same `start_month`/`end_month` backfill twice produces byte-identical, diffable output (documented in README); a deliberately failed run still triggers the `ExitHandler` cleanup/notification task; pipeline caching invalidation is documented with the specific input change and resulting cache-key diff.
  5. The pipeline compiles to versioned YAML attached as a CI release artifact; README includes an architecture diagram, the Phase 2 benchmark table, ADRs covering the 4 Key Decisions from PROJECT.md, and an explicit "Next Steps" section documenting deferred scope (KServe, dashboard, recurring runs).
**Plans**: TBD

Plans:
- [ ] 03-01: TBD (refined during planning)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Repo Foundation & CI Quality Gates | 0/TBD | Not started | - |
| 2. Data & Model Engineering (lib/) | 0/TBD | Not started | - |
| 3. Kubeflow Pipeline Core & Deployment | 0/TBD | Not started | - |
