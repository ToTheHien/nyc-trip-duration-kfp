# Requirements — nyc-trip-duration-kfp v1

Source: `PROJECT.md` (Active requirements) + `research/FEATURES.md` (MVP priority matrix).
Scope: Phases 1–2 only (repo/CI quality gates + Kubeflow training DAG). Phases 3–4 (serving, dashboard) are out of scope for this milestone — see PROJECT.md Out of Scope.

## Category A — Repo & CI Quality Gates (Phase 1)

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|----------------------|
| REQ-A1 | Monorepo skeleton: `components/`, `pipelines/`, `lib/`, `serving/`, `dashboard/`, `tests/`, managed with `uv` | P1 | `uv sync` installs cleanly; directory layout matches PROJECT.md |
| REQ-A2 | `ruff` + `mypy --strict` enforced on `lib/` | P1 | Both run clean on `lib/` locally and in CI; a deliberately broken type/lint rule fails CI |
| REQ-A3 | `pytest` unit tests on `lib/` with synthetic DataFrame fixtures | P1 | Tests assert exact output values (not just "doesn't crash"); coverage on `lib/` visibly near 100% |
| REQ-A4 | GitHub Actions: lint → typecheck → test → build component images → push to GHCR, on every PR | P1 | PR against a broken `lib/` change is blocked at the failing stage; a clean PR produces a pushed GHCR image tag |
| REQ-A5 | `pre-commit` config mirroring CI checks | P2 | `pre-commit run --all-files` matches CI pass/fail on the same commit |
| REQ-A6 | `lib/` holds 100% of pandas/feature logic; `components/` are thin wrappers | P1 | No pandas transformation logic lives inside a `@dsl.component`/`@dsl.container_component` body — grep-verifiable |

## Category B — Kubeflow Pipeline Core (Phase 2)

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|----------------------|
| REQ-B1 | KFP standalone installed on k3d (not full multi-user Istio stack) | P1 | `kubectl get pods -n kubeflow` shows KFP running; no Istio namespace present |
| REQ-B2 | Typed artifacts (`Input[Dataset]`, `Output[Model]`, `Output[Metrics]`) throughout — no raw string paths between components | P1 | Every component signature uses typed artifact params; verified by reading `pipelines/` source |
| REQ-B3 | Custom component images built in CI, referenced via `base_image=`/`ContainerSpec` pointing at GHCR tags — not `packages_to_install` | P1 | No `packages_to_install` in any component decorator; images resolve to a GHCR tag built by REQ-A4's CI job |
| REQ-B4 | Full DAG: ingest(month) → validate → features → ParallelFor(months) → merge → train → evaluate → If(rmse < champion) → register | P1 | Pipeline compiles and a full run reaches `register` (or a documented skip-branch) on real data |
| REQ-B5 | `dsl.ParallelFor` fan-out over months, parallelism capped for 16GB RAM (2–3 concurrent) | P1 | Pipeline YAML shows `parallelism` cap set; a run with ≥4 months queues rather than OOMs |
| REQ-B6 | `dsl.Collected` fan-in merging ParallelFor outputs before train stage | P1 | Merge component receives a `Collected` list input, not manual artifact stitching |
| REQ-B7 | `dsl.If`/`dsl.OneOf` conditional promotion: register only if new model beats MLflow-tracked champion | P1 | A run with a deliberately worse model does not call `register`; a better model does — both demonstrated |
| REQ-B8 | Idempotent backfill: `start_month`/`end_month` pipeline params, same range run twice produces byte-identical output | P1 | Checksum/diff of two identical backfill runs documented as matching in README |
| REQ-B9 | `ExitHandler` for failure-path cleanup/notification (not just happy path) | P2 | A deliberately failed run still triggers the exit task; visible in KFP run UI/logs |
| REQ-B10 | Pipeline caching enabled, then deliberately invalidated by changing a component input | P2 | README documents the specific input change and resulting cache-key diff |
| REQ-B11 | Pipeline compiled to versioned YAML in CI, attached as a release artifact | P1 | CI run produces a downloadable compiled pipeline YAML on tagged releases |

## Category C — Data Quality & Pandas/Numpy Engineering

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|----------------------|
| REQ-C1 | pandera schema validation at ingest boundary with real `Check`s (not passthrough) | P2 | A malformed/schema-drifted month fails validation loudly (non-zero exit, logged reason), not silently |
| REQ-C2 | Vectorized haversine distance replacing `.apply()` | P1 | `lib/` contains both implementations (or a benchmark script) showing the vectorized path is used in production code |
| REQ-C3 | dtype downcasting (float64→float32, category dtypes) | P1 | Feature-stage output dtypes documented; memory footprint measurably reduced vs naive read |
| REQ-C4 | Chunked reads for ingest | P1 | Ingest component reads via chunked/streaming API, not a single full-file `read_parquet` into memory unbounded |
| REQ-C5 | Before/after benchmark table (time + memory) in README | P1 | README contains a concrete table with numbers, not prose claims |

## Category D — Dataset & Modeling

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|----------------------|
| REQ-D1 | NYC TLC trip data, 12-month window spanning a drift event (e.g. 2019–2020 pre/post-COVID) | P1 | Ingest config pins exact month range; README states the drift rationale |
| REQ-D2 | Target: trip-duration regression via LightGBM, no hyperparameter tuning | P1 | Single fixed LightGBM config committed; no tuning framework/sweep code present |
| REQ-D3 | MLflow model registry with champion/candidate aliasing (`@champion`/`@candidate`) | P1 | `set_registered_model_alias` used; champion lookup step queries this alias, not a deprecated numeric "stage" |

## Category E — Documentation

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|----------------------|
| REQ-E1 | README with architecture diagram | P1 | Diagram present (not just prose) covering ingest→...→register flow |
| REQ-E2 | ADRs for non-obvious calls (KFP vs Airflow, Parquet, deferred serving/dashboard) | P1 | At least the 4 Key Decisions from PROJECT.md have a corresponding ADR entry |
| REQ-E3 | README documents deferred scope (KServe, dashboard, recurring runs) as "next steps" | P2 | Explicit "Next Steps" section exists, not just silence on the topic |

## Out of Scope (v1)

Unchanged from PROJECT.md: KServe serving, ONNX export, batching, k6 load testing, recurring/cron runs, Streamlit/React dashboard, full 2009–present ingestion, full multi-user Kubeflow/Istio, hyperparameter tuning, tip-percentage classification, feature store, distributed training, hand-rolled retry logic, external alerting integrations.

## Definition of Done (v1 milestone)

All P1 requirements above implemented and demonstrable; P2 requirements implemented if the 10–15h budget allows, otherwise explicitly logged as deferred (not silently dropped) in README's "Next Steps."

## Traceability

Structure mode: horizontal layers. Phase 1 (repo/CI foundation) completes fully before Phase 2 (offline `lib/` data & model engineering) begins; Phase 2 completes fully before Phase 3 (Kubeflow cluster/DAG assembly) begins. Category E (documentation/ADRs) is written incrementally across all three phases but is tracked and completed as part of Phase 3.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-A1 | Phase 1 | Complete |
| REQ-A2 | Phase 1 | Complete |
| REQ-A3 | Phase 1 | Complete |
| REQ-A4 | Phase 1 | Complete |
| REQ-A5 | Phase 1 | Complete |
| REQ-A6 | Phase 1 | Complete |
| REQ-C1 | Phase 2 | Complete |
| REQ-C2 | Phase 2 | Complete |
| REQ-C3 | Phase 2 | Complete |
| REQ-C4 | Phase 2 | Complete |
| REQ-C5 | Phase 2 | Pending |
| REQ-D1 | Phase 2 | Complete |
| REQ-D2 | Phase 2 | Complete |
| REQ-D3 | Phase 2 | Complete |
| REQ-B1 | Phase 3 | Pending |
| REQ-B2 | Phase 3 | Pending |
| REQ-B3 | Phase 3 | Pending |
| REQ-B4 | Phase 3 | Pending |
| REQ-B5 | Phase 3 | Pending |
| REQ-B6 | Phase 3 | Pending |
| REQ-B7 | Phase 3 | Pending |
| REQ-B8 | Phase 3 | Pending |
| REQ-B9 | Phase 3 | Pending |
| REQ-B10 | Phase 3 | Pending |
| REQ-B11 | Phase 3 | Pending |
| REQ-E1 | Phase 3 | Pending |
| REQ-E2 | Phase 3 | Pending |
| REQ-E3 | Phase 3 | Pending |

**Coverage:** 28/28 v1 requirements mapped. No orphans.
