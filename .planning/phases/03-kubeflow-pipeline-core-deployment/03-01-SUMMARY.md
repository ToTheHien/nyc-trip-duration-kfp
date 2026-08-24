---
phase: 03-kubeflow-pipeline-core-deployment
plan: 01
subsystem: infra
tags: [kfp, kubeflow-pipelines, kfp-kubernetes, boto3, docker, github-actions, uv, lightgbm]

# Dependency graph
requires:
  - phase: 02-data-model-engineering-lib
    provides: "lib/ingest.py, lib/schemas.py, lib/features.py, lib/train.py, lib/evaluate.py, lib/registry.py - 100%-tested, zero-KFP-import pandas/LightGBM/MLflow logic"
provides:
  - "pipeline dependency group (kfp==2.17.0, kfp-kubernetes==2.17.0, boto3)"
  - "lib/artifacts.py: the path-in/path-out adapter every thin components/ body calls"
  - "components/ingest/component.py: the first real @dsl.component, CI-built and GHCR-published"
  - "pipelines/train_pipeline.py + pipelines/compile.py: the DAG skeleton and compiled-YAML CLI plan 03-02 extends"
  - "CI: discover-components matrix build-push + compile-pipeline job publishing dist/train_pipeline.yaml"
affects: [03-02-training-dag-assembly, 03-03-readme-adrs, 03-04-cluster-deployment, 03-05-pipeline-run-evidence]

actuals:
  tokens: 19200
  tasks: 3
  commits: 2

tech-stack:
  added: ["kfp==2.17.0", "kfp-kubernetes==2.17.0", "boto3", "PyYAML (transitive via kfp)"]
  patterns:
    - "lib/artifacts.py path-in/path-out adapter layer between typed KFP artifacts and Phase 2 lib/ functions - components/ never imports pandas directly"
    - "components/__init__.py::image_for(name) - git-SHA-only GHCR image references, never a floating tag"
    - "pipelines/train_pipeline.py::_harden(task, mem_req, mem_limit) - shared caching+resource-limit helper reused across every DAG task"

key-files:
  created:
    - lib/artifacts.py
    - tests/lib/test_artifacts.py
    - components/ingest/component.py
    - pipelines/__init__.py
    - pipelines/train_pipeline.py
    - pipelines/compile.py
    - tests/pipelines/test_pipeline_compiles.py
  modified:
    - pyproject.toml
    - uv.lock
    - .gitignore
    - scripts/qa.sh
    - scripts/check_component_boundary.sh
    - .github/workflows/ci.yml
    - components/__init__.py
    - components/ingest/Dockerfile

key-decisions:
  - "build_features_parquet carries tpep_pickup_datetime through as a passthrough column beyond lib.features's locked FEATURE_COLUMNS/TARGET_COLUMN contract, so train_from_parquet/evaluate_from_parquet can chronological_split the merged features artifact without widening lib/features.py's Phase-2-locked signature."
  - "Parquet does not round-trip int-keyed pandas Categorical dtype automatically in this pinned pandas==2.3.3/pyarrow==25.0.1 combo (string-keyed categoricals do); every real consumer (lib.train's fit-time cast, evaluate_from_parquet's predict-time cast) re-establishes the dtype explicitly at the point of use rather than trusting the round trip."
  - "components/ingest/Dockerfile installs libgomp1 - LightGBM's compiled extension dynamically links it and python:3.12-slim does not ship it; found by locally building and running the image."
  - "Sequential dispatch skips this task's own branch/PR step: the orchestrator's phase-level branch already satisfies the repo's branching rule, and the orchestrator owns the eventual push/PR once the whole phase is verified."

patterns-established:
  - "Deterministic backfill key: lib.artifacts.artifact_key(month, stage, version) = f'{version}/{stage}/{month}.parquet', re-validated via lib.months.month_range and empty/separator checks on stage and version."
  - "merge_feature_parquets sorts input paths by str(path) before concatenating, making the merged row order independent of dsl.Collected's unspecified fan-in order (REQ-B8 prerequisite)."

requirements-completed: [REQ-B2, REQ-B3, REQ-B8, REQ-B11]

coverage:
  - id: D1
    description: "pipeline dependency group installs kfp 2.17.0, kfp-kubernetes 2.17.0, boto3 from a committed uv.lock; scripts/qa.sh test runs green with --extra pipeline"
    requirement: REQ-B3
    verification:
      - kind: unit
        ref: "scripts/qa.sh test (129 passed, 100% lib/ coverage)"
        status: pass
      - kind: other
        ref: "uv run --extra dev --extra ml --extra pipeline python -c \"import kfp, kfp.kubernetes, boto3; print(kfp.__version__)\" -> 2.17.0"
        status: pass
    human_judgment: false
  - id: D2
    description: "lib/artifacts.py path-in/path-out adapter layer at 100% coverage and clean mypy --strict, including the deterministic backfill key and order-independent merge"
    requirement: REQ-B8
    verification:
      - kind: unit
        ref: "tests/lib/test_artifacts.py (25 tests, 100% coverage of lib/artifacts.py)"
        status: pass
    human_judgment: false
  - id: D3
    description: "ingest component compiles into a KFP DAG referencing a git-SHA-tagged GHCR image, with typed-artifact/scalar-only parameters and no packages_to_install"
    requirement: REQ-B2
    verification:
      - kind: unit
        ref: "tests/pipelines/test_pipeline_compiles.py (4 tests: non-empty compile, typed params, git-SHA image tag, no packages_to_install)"
        status: pass
    human_judgment: false
  - id: D4
    description: "CI builds every component image via a non-vacuous discover-components matrix and publishes the compiled pipeline YAML as a downloadable artifact (and to the GitHub Release on a tag push)"
    requirement: REQ-B11
    verification: []
    human_judgment: true
    rationale: "This plan's dispatch is sequential/no-push (orchestrator owns the eventual push/PR for the whole phase); a green GitHub Actions run of discover-components/build-push/compile-pipeline has not executed yet. Verified locally instead: YAML syntax valid, discover-components' vacuous-matrix guard proven by hand (Dockerfile temporarily removed and restored), and a local docker build + docker run of the ingest image confirms it imports both kfp and lib.artifacts (this local run is what surfaced and fixed the libgomp1 gap). A human must confirm the actual CI run once the branch is pushed."

duration: 40min
completed: 2026-08-25
status: complete
---

# Phase 3 Plan 1: Pipeline Foundation & End-to-End Ingest Tracer Summary

**kfp 2.17.0 pipeline dependency group, a 100%-tested `lib/artifacts.py` path-in/path-out adapter layer, and one real `@dsl.component` (`ingest`) compiling into a git-SHA-tagged GHCR-referenced KFP DAG with matrixed CI image builds and a compiled-YAML release artifact job.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-08-25
- **Tasks:** 3 (1 checkpoint, 2 executed)
- **Files modified:** 17 (7 created, 8 modified, 2 deleted)

## Accomplishments

- Package-legitimacy checkpoint (kfp, kfp-kubernetes, boto3) reviewed and approved by the coordinator before any install.
- `pyproject.toml`'s `pipeline` extra populated (`kfp==2.17.0`, `kfp-kubernetes==2.17.0`, `boto3`), `uv.lock` regenerated, `scripts/qa.sh` and all CI jobs sync it.
- `lib/artifacts.py`: every path-in/path-out adapter the nine Phase 3 components need (`artifact_key`, `default_s3_client`, `download_object`, `upload_object`, `publish_deterministic`, `ingest_month_to_parquet`, `validate_parquet`, `build_features_parquet`, `build_and_publish_features`, `merge_feature_parquets`, `train_from_parquet`, `evaluate_from_parquet`), 100% coverage, clean `mypy --strict`.
- The Phase 1 tracer CLI (`components/ingest/main.py`) replaced by the real `components/ingest/component.py` `@dsl.component`, wired through `pipelines/train_pipeline.py` into a single-task DAG that compiles to IR YAML via `pipelines/compile.py`.
- `.github/workflows/ci.yml` reworked: tag-push trigger, a non-vacuous `discover-components` matrix job feeding matrixed `build-push`, and a `compile-pipeline` job uploading `dist/train_pipeline.yaml` (and, on a tag push, attaching it to the GitHub Release).
- `scripts/check_component_boundary.sh` now scans `pipelines/` alongside `components/`, still refuses to pass vacuously.

## Task Commits

Each task was committed atomically:

1. **Task 1: Package legitimacy verification for kfp/kfp-kubernetes/boto3** - checkpoint (no commit; coordinator approved, no code changed before this point)
2. **Task 2: Populate the pipeline dependency group and build the lib path-adapter layer** - `9a39a55` (feat)
3. **Task 3: End-to-end "one month ingested through a compiled, CI-built KFP DAG"** - `7ff9fa9` (feat)

## Files Created/Modified

- `lib/artifacts.py` - path-in/path-out adapter layer (deterministic key, S3 I/O, ingest/validate/features/merge/train/evaluate)
- `tests/lib/test_artifacts.py` - 25 tests, 100% coverage, mocked S3 client
- `components/__init__.py` - `IMAGE_REGISTRY`/`IMAGE_TAG`/`image_for()`
- `components/ingest/component.py` - the real ingest `@dsl.component` (replaces `main.py`)
- `components/ingest/Dockerfile` - installs locked `ml`+`pipeline` extras via `uv export`/`uv pip install`, plus `libgomp1`
- `pipelines/__init__.py`, `pipelines/train_pipeline.py`, `pipelines/compile.py` - DAG skeleton + compile CLI
- `tests/pipelines/test_pipeline_compiles.py` - 4 compile-time DAG shape assertions
- `pyproject.toml`, `uv.lock`, `.gitignore`, `scripts/qa.sh` - `pipeline` extra wiring, `dist/` ignored
- `scripts/check_component_boundary.sh` - `SCAN_PATHS` covers `components/` + `pipelines/`
- `.github/workflows/ci.yml` - tag trigger, `discover-components`, matrixed `build-push`, `compile-pipeline`

## Decisions Made

- **`tpep_pickup_datetime` passthrough in `build_features_parquet`'s output.** The plan's `train_from_parquet`/`evaluate_from_parquet` spec calls `chronological_split` directly on the features Parquet, but `lib.features.build_features`'s locked (Phase 2) `FEATURE_COLUMNS`/`TARGET_COLUMN` contract drops `tpep_pickup_datetime`, which `chronological_split` requires. Fixed inside `lib/artifacts.py` (in scope for this plan) by carrying the timestamp through as an extra column on write, rather than widening `lib/features.py`'s locked public signature (out of scope).
- **Int-keyed categorical dtype does not survive a plain Parquet round trip** in this repo's pinned `pandas==2.3.3`/`pyarrow==25.0.1` (string-keyed categoricals do restore automatically; int-keyed ones - `PULocationID`/`DOLocationID`/`VendorID` - come back as plain `int64`). Documented in `lib/artifacts.py`; every real reader already re-casts explicitly at the point of use (`lib.train.train_trip_duration_model`, `evaluate_from_parquet`), so no round-trip-preservation code was added - the dtype-preservation test verifies the honest contract (reapplying `downcast_features` after read restores it) rather than a false claim about the storage format.
- **`libgomp1` added to `components/ingest/Dockerfile`.** LightGBM's compiled extension (imported transitively via `lib.evaluate`) dynamically links `libgomp.so.1`, which `python:3.12-slim` does not ship - found by locally building and running the image and reproducing the exact `import lib.artifacts` the component performs at pod start.
- **Skipped this task's own branch/PR step.** The orchestrator dispatched this plan on a phase-level branch (`feature/phase-3-kubeflow-pipeline-core-deployment`, already checked out from `development` per the repo's branching rule) and explicitly directed no push/merge until the whole phase is verified. The plan's `<action>` text assumed a per-plan branch+PR flow; the orchestrator's phase-level flow supersedes it without contradicting the underlying branching rule.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `train_from_parquet`/`evaluate_from_parquet` couldn't split the features artifact as literally specified**
- **Found during:** Task 2, writing `tests/lib/test_artifacts.py`'s train/evaluate tests
- **Issue:** `chronological_split` requires `tpep_pickup_datetime`; `build_features`'s locked output (`FEATURE_COLUMNS` + `TARGET_COLUMN`) never carries it, so a `KeyError` was raised the first time the real read-through-adapter path was exercised.
- **Fix:** `build_features_parquet` now writes `tpep_pickup_datetime` as an extra passthrough column sourced from its `in_path` input (the validated frame, which still has it). `train_from_parquet`/`evaluate_from_parquet` are unchanged - the fix lives entirely at the point the column is dropped.
- **Files modified:** `lib/artifacts.py`, `tests/lib/test_artifacts.py`
- **Commit:** `9a39a55`

**2. [Rule 1 - Bug] `components/ingest/Dockerfile` built but failed to import at container runtime**
- **Found during:** Task 3, local `docker build` + `docker run` verification (substituting for the CI-run acceptance criteria this sequential dispatch cannot execute)
- **Issue:** `import lib.artifacts` (transitively `lightgbm`) raised `OSError: libgomp.so.1: cannot open shared object file` - `python:3.12-slim` does not ship OpenMP's runtime library, which LightGBM's compiled extension requires.
- **Fix:** Added `apt-get install -y --no-install-recommends libgomp1` before the dependency-install layer.
- **Files modified:** `components/ingest/Dockerfile`
- **Verification:** Rebuilt locally; `docker run --rm --entrypoint python <image> -c "import kfp, lib.artifacts; print(kfp.__version__)"` now prints `2.17.0`; `from components.ingest.component import ingest` also succeeds inside the container.
- **Commit:** `7ff9fa9`

**3. [Rule 1 - Bug] `grep -c 'load_month' lib/artifacts.py` acceptance criterion tripped by a docstring reference**
- **Found during:** Task 2, running the plan's own acceptance-criteria checks after writing `lib/artifacts.py`
- **Issue:** `ingest_month_to_parquet`'s docstring named `lib.ingest.load_month` in prose (explaining why it composes primitives instead of reusing that orchestrator), which the literal `grep -c` check counted as 2, not the required 0.
- **Fix:** Reworded the docstring to describe the same design decision without the literal substring `load_month`.
- **Files modified:** `lib/artifacts.py`
- **Commit:** `9a39a55`

---

**Total deviations:** 3 auto-fixed (all Rule 1 - bugs discovered during implementation/verification, not scope changes)
**Impact on plan:** All three are correctness fixes required for the plan's own acceptance criteria and must-have truths to actually hold; no scope creep, no architectural changes.

## Issues Encountered

- Confirmed empirically (not assumed) that pandas' `to_parquet`/`read_parquet` round trip preserves string-keyed Categorical dtype automatically via embedded pandas metadata, but silently degrades int-keyed Categorical columns to plain `int64` on read, in this repo's pinned `pandas==2.3.3`/`pyarrow==25.0.1`. This is a real, load-bearing gap in `RESEARCH.md`'s "byte-identical" verification (which checked byte-determinism, not dtype-identity across a fresh read). Resolved by design decision above; no further action needed since every real consumer already re-casts.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `lib/artifacts.py`'s full adapter surface (all 12 exported symbols) is ready for plan 03-02's eight remaining components (`months`, `validate`, `features`, `merge`, `train`, `evaluate`, `register`, `notify`) to call directly - no new adapter functions should be needed.
- `pipelines/train_pipeline.py`'s `_harden()` helper and `s3_endpoint_url` parameter are designed to survive plan 03-02's full-DAG replacement unchanged.
- **Blocker for full phase verification:** this plan's branch has not been pushed (sequential, orchestrator-owned push per dispatch). The CI-run-only acceptance criteria for Task 3 (`gh run watch`/`view`/`download`, `docker pull` from GHCR) are unverified until the orchestrator pushes and CI runs - local `docker build`/`docker run` and local `pipelines.compile` substitute for now and already surfaced and fixed the one real defect (`libgomp1`) a CI-only build would also have hit.
- Plan 03-04 (cluster deployment) depends on the GHCR image actually being pullable from a real k3d pod - not yet exercised, since no image has been pushed.

---
*Phase: 03-kubeflow-pipeline-core-deployment*
*Completed: 2026-08-25*

## Self-Check: PASSED

All 16 files created/modified this plan verified present on disk; both task commits (`9a39a55`, `7ff9fa9`) verified present in `git log --oneline --all`.
