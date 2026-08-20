---
phase: 02-data-model-engineering-lib
plan: 01
subsystem: data-model-engineering
tags: [pandas, numpy, pyarrow, pandera, lightgbm, mlflow, tracer-slice]

requires:
  - phase: 01-repo-foundation-ci-quality-gates
    provides: "scripts/qa.sh single entrypoint, pyproject.toml D-04 dev/pipeline/ml optional-dependency groups (ml pre-declared empty), lib/months.month_range, 100%-branch-coverage pytest gate"
provides:
  - "pyproject.toml ml group populated: pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1, pandera 0.32.1, lightgbm 4.7.0, mlflow 3.15.1"
  - "scripts/qa.sh and CI (.github/workflows/ci.yml lint/typecheck/test jobs) install --extra dev --extra ml"
  - "lib/ingest.py: DEFAULT_BATCH_SIZE, TLC_START_MONTH, TLC_END_MONTH, TLC_DATA_DIR, month_parquet_path, read_month_chunked, add_trip_duration"
  - "lib/schemas.py: trip_schema, validate_trips"
  - "lib/features.py: EARTH_RADIUS_KM, ZONE_CENTROID_PATH, load_zone_centroids, haversine_km, build_features, FEATURE_COLUMNS, TARGET_COLUMN"
  - "lib/train.py: LGBM_PARAMS, CATEGORICAL_FEATURES, train_trip_duration_model"
  - "lib/evaluate.py: rmse"
  - "lib/registry.py: ModelRegistry, CHAMPION_ALIAS, RMSE_TAG"
  - "tests/lib/test_tracer_end_to_end.py: regression harness proving the full chain end to end"
  - "data/ directory (with .gitkeep) for plan 02-02's committed data/zone_centroids.csv"
affects: [02-02, 02-03, 02-04, 02-05]

actuals:
  tokens: 59411
  tasks: 3
  commits: 2

tech-stack:
  added: [pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1, pandera 0.32.1, lightgbm 4.7.0, mlflow 3.15.1, pandas-stubs, pyshp 3.1.6, pyproj 3.7.2]
  patterns:
    - "Thin, mockable MLflow client wrapper (dependency-injected client, no real server until Phase 3)"
    - "D-09a two-tier pandera enforcement: structural schema only in this plan; row-level pre-filter deferred to 02-04"
    - "Vectorized haversine with arcsin-argument clamping to avoid NaN on identical coordinates"
    - "In-place categorical dtype casting on the training frame (not a defensive copy) so predict-time dtype matches train-time, per LightGBM's category-alignment requirement"

key-files:
  created:
    - lib/ingest.py
    - lib/schemas.py
    - lib/features.py
    - lib/train.py
    - lib/evaluate.py
    - lib/registry.py
    - tests/lib/test_tracer_end_to_end.py
    - data/.gitkeep
  modified:
    - pyproject.toml
    - uv.lock
    - scripts/qa.sh
    - .github/workflows/ci.yml
    - .gitignore
    - README.md

key-decisions:
  - "Task 1 package-legitimacy checkpoint (pyshp, pyproj) treated as pre-approved: the user independently verified both packages against pypi.org earlier in this session (pyshp: MIT, GeospatialPython org, established since 2013; pyproj: MIT, official PROJ binding, used internally by geopandas itself) during Phase 2 research/planning review, before this execution run started. No new red flags surfaced during execution — packages, versions, and registry pages matched what RESEARCH.md's Package Legitimacy Audit and the checkpoint prompt described. See 'Task 1 Checkpoint Verdict' below for the full record."
  - "lib/train.py's train_trip_duration_model mutates x in place (astype('category') assigns back into the caller's frame, not a defensive copy) — matches RESEARCH.md Pattern 4 exactly. A defensive copy was tried first and broke predict(), because LightGBM requires predict-time categorical dtype/category-set to match train-time exactly; the caller's x must carry the cast forward."
  - "Added a [[tool.mypy.overrides]] for pyarrow.* (ignore_missing_imports = true) — pyarrow ships no py.typed marker, so mypy --strict flagged every attribute access as untyped. Standard practice for this specific library, not a general strictness relaxation."

patterns-established:
  - "lib/ modules stay pure-function/module-level except where external-client state needs holding (ModelRegistry is the one justified class)"
  - "Row-level DataFrame join for zone-centroid lookup happens twice (once per PU/DO zone) with column-renamed centroid frames, avoiding a self-join"

requirements-completed: [REQ-C1, REQ-C2, REQ-C3, REQ-C4, REQ-D1, REQ-D2, REQ-D3]

coverage:
  - id: D1
    description: "ml optional-dependency group populated; scripts/qa.sh and all three CI checking jobs install --extra dev --extra ml"
    requirement: "REQ-C1"
    verification:
      - kind: unit
        ref: "scripts/qa.sh lint && scripts/qa.sh format && scripts/qa.sh typecheck && scripts/qa.sh test && scripts/qa.sh boundary — full local run"
        status: pass
    human_judgment: false
  - id: D2
    description: "Chunked Parquet ingest (pyarrow.parquet.ParquetFile.iter_batches) never loads a whole month at once"
    requirement: "REQ-C4"
    verification:
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_read_month_chunked_returns_all_rows_in_order"
        status: pass
    human_judgment: false
  - id: D3
    description: "pandera structural schema validates the ingest boundary, raises loudly on a missing/malformed column"
    requirement: "REQ-C1"
    verification:
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_validate_trips_returns_clean_frame_unchanged"
        status: pass
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_validate_trips_raises_on_missing_required_column"
        status: pass
    human_judgment: false
  - id: D4
    description: "Vectorized haversine distance (no .apply()) with dtype-safe arcsin clamping"
    requirement: "REQ-C2"
    verification:
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_haversine_km_zero_for_identical_coordinates"
        status: pass
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_build_features_haversine_is_zero_for_identical_zones"
        status: pass
    human_judgment: false
  - id: D5
    description: "Fixed, untuned LightGBM regression config trains and predicts finite values"
    requirement: "REQ-D2"
    verification:
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_train_trip_duration_model_predicts_finite_values"
        status: pass
    human_judgment: false
  - id: D6
    description: "Mockable MLflow registry wrapper returns None with no champion, float RMSE when tagged"
    requirement: "REQ-D3"
    verification:
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_get_champion_rmse_returns_none_when_no_champion"
        status: pass
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_get_champion_rmse_returns_float_when_champion_tagged"
        status: pass
    human_judgment: false
  - id: D7
    description: "Full chain (read -> duration -> validate -> features -> fit -> rmse -> champion lookup) produces a finite, strictly positive RMSE"
    requirement: "REQ-D1"
    verification:
      - kind: unit
        ref: "tests/lib/test_tracer_end_to_end.py#test_full_chain_produces_finite_positive_rmse"
        status: pass
    human_judgment: false
  - id: D8
    description: "REQ-D1/D-07 backfill window pinned once (lib.ingest.TLC_START_MONTH/TLC_END_MONTH = 2019-07/2020-06), enumerates to 12 months, contains 2020-03"
    requirement: "REQ-D1"
    verification:
      - kind: unit
        ref: "python -c window-ok check (see Verification section below)"
        status: pass
    human_judgment: false

duration: ~55min
completed: 2026-08-20
status: complete
---

# Phase 2 Plan 1: Foundation + End-to-End Tracer Summary

**Populated the `ml` dependency group (pandas/numpy/pyarrow/pandera/lightgbm/mlflow at RESEARCH.md-verified pins), taught `scripts/qa.sh`/CI the extra, and proved the whole Phase 2 architecture with one real synthetic-month RMSE flowing through all six new `lib/` modules.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3/3 (Task 1 checkpoint pre-approved, Task 2 + Task 3 executed and committed)
- **Files modified:** 14
- **Commits:** 2

## Accomplishments

- `pyproject.toml`'s `ml` group holds the six RESEARCH.md-pinned packages (resolved via `uv.lock`: pandas 2.3.3, numpy 2.5.2, pyarrow 25.0.1, pandera 0.32.1, lightgbm 4.7.0, mlflow 3.15.1); `dev` gained `pandas-stubs`, `pyshp` 3.1.6, `pyproj` 3.7.2.
- `scripts/qa.sh` (both `UV_RUN` branches) and all three checking CI jobs (`lint`, `typecheck`, `test`) now install `--extra dev --extra ml`; `build-push` untouched.
- Six `lib/` modules exist with exactly the `[02-01]`-tagged public symbol set, pass `mypy --strict`, and hold 100% branch coverage.
- `tests/lib/test_tracer_end_to_end.py` (20 tests) drives one synthetic month through `read_month_chunked -> add_trip_duration -> validate_trips -> build_features -> train_trip_duration_model -> rmse -> ModelRegistry.get_champion_rmse`, asserting a real, computed, finite, strictly positive RMSE — not a hardcoded constant.
- `data/tlc/` gitignored; `data/` directory created with `.gitkeep` so `data/zone_centroids.csv` (plan 02-02) has a home; `data/zone_centroids.csv` itself remains trackable.
- REQ-D1/D-07's 12-month backfill window pinned once at `lib.ingest.TLC_START_MONTH`/`TLC_END_MONTH` = `2019-07`/`2020-06`, verified to enumerate to 12 months via `lib.months.month_range` and to contain `2020-03`.

## Task 1 Checkpoint Verdict

**Type:** `checkpoint:human-verify`, `gate="blocking-human"` (package-legitimacy gate for `pyshp` and `pyproj`)

**Verdict: approved** (both packages).

This checkpoint was resolved by the user **prior to this execution dispatch**, during the Phase 2 research/planning review earlier in the same session — not re-verified fresh during this run, but explicitly confirmed as still valid by the orchestrator before Task 2 began. Verification basis recorded by the user:

- **`pyshp`** — MIT licensed, GeospatialPython org, established since 2013 (independently checked against pypi.org/project/pyshp/).
- **`pyproj`** — MIT licensed, official PROJ binding (pyproj4/pyproj), used internally by `geopandas` itself (independently checked against pypi.org/project/pyproj/).

This matches `02-RESEARCH.md`'s own Package Legitimacy Audit finding: both packages were flagged `[SUS]` only because the automated checker had no PyPI download-count telemetry available in this environment (`unknown-downloads` fired on every package checked, including pandas/numpy/lightgbm/mlflow — a data-availability gap, not a legitimacy signal), and RESEARCH.md's own live cross-check against `pip index versions` and each package's GitHub source repo reached the same "legitimate, approved" conclusion independently.

No install command ran before this verdict was recorded; nothing about the checkpoint (package identity, version, registry page) differed from what was reviewed earlier in the session, so per the orchestrator's explicit instruction, execution proceeded to Task 2 on the strength of this pre-approval, documented here for the audit trail.

## Task Commits

Each task was committed atomically:

1. **Task 1: Package-legitimacy gate** — no commit (checkpoint verdict recorded in this SUMMARY; no code/dependency changes happen at this task)
2. **Task 2: Populate the `ml` dependency group, teach `qa.sh`/CI** — `6ef9381` (feat)
3. **Task 3: End-to-end tracer (six `lib/` modules + test)** — `6956adb` (feat)

_Note: Task 3 is `tdd="true"` but lands as a single commit rather than separate `test(...)`/`feat(...)` commits — see "TDD Gate Compliance" below for why._

## Files Created/Modified

- `pyproject.toml` — `ml` group populated (pandas/numpy/pyarrow/pandera/lightgbm/mlflow); `dev` gained `pandas-stubs`/`pyshp`/`pyproj`; added `[[tool.mypy.overrides]]` for `pyarrow.*`
- `uv.lock` — regenerated, ~1700 lines of new transitive-dependency resolution
- `scripts/qa.sh` — both `UV_RUN` branches (CI and local) now pass `--extra ml` alongside `--extra dev`
- `.github/workflows/ci.yml` — `lint`/`typecheck`/`test` jobs' `uv sync` steps gained `--extra ml`
- `.gitignore` — `data/tlc/` added
- `README.md` — corrected the `--extra dev`-only sentence and quick-start command to name both extras
- `data/.gitkeep` — new `data/` directory for plan 02-02's `data/zone_centroids.csv`
- `lib/ingest.py` — chunked TLC Parquet read, trip-duration derivation, REQ-D1/D-07 window constants
- `lib/schemas.py` — pandera structural schema (D-09a tier 1), `validate_trips`
- `lib/features.py` — vectorized haversine, zone-centroid join, `FEATURE_COLUMNS`/`TARGET_COLUMN` contract
- `lib/train.py` — fixed LightGBM config, `train_trip_duration_model`
- `lib/evaluate.py` — `rmse`
- `lib/registry.py` — `ModelRegistry`, mockable MLflow wrapper
- `tests/lib/test_tracer_end_to_end.py` — 20 tests: 12 covering the `<behavior>` spec, 8 additional small unit tests closing branch-coverage gaps (`month_parquet_path`, `load_zone_centroids`) the end-to-end chain doesn't reach

## Final Public Symbol List Per Module (locked for waves 2-4)

**`lib/ingest.py`:** `DEFAULT_BATCH_SIZE`, `TLC_START_MONTH`, `TLC_END_MONTH`, `TLC_DATA_DIR`, `month_parquet_path(month, data_dir=TLC_DATA_DIR) -> Path`, `read_month_chunked(path, batch_size=DEFAULT_BATCH_SIZE) -> pd.DataFrame`, `add_trip_duration(df) -> pd.DataFrame`

**`lib/schemas.py`:** `VALID_ZONE_MIN`, `VALID_ZONE_MAX`, `PLACEHOLDER_ZONE_IDS`, `PASSENGER_COUNT_MIN`, `PASSENGER_COUNT_MAX`, `trip_schema` (pandera `DataFrameSchema`), `validate_trips(df) -> pd.DataFrame`

**`lib/features.py`:** `EARTH_RADIUS_KM`, `ZONE_CENTROID_PATH`, `FEATURE_COLUMNS`, `TARGET_COLUMN`, `load_zone_centroids(path=ZONE_CENTROID_PATH) -> pd.DataFrame`, `haversine_km(lat1, lon1, lat2, lon2) -> pd.Series`, `build_features(df, centroids) -> pd.DataFrame`

**`lib/train.py`:** `CATEGORICAL_FEATURES`, `LGBM_PARAMS`, `train_trip_duration_model(x, y) -> lgb.LGBMRegressor`

**`lib/evaluate.py`:** `rmse(y_true, y_pred) -> float`

**`lib/registry.py`:** `CHAMPION_ALIAS`, `RMSE_TAG`, `ModelRegistry` (`__init__(client, model_name)`, `get_champion_rmse() -> float | None`)

## Resolved `ml`-Package Versions (from `uv.lock`)

| Package | Version |
|---|---|
| pandas | 2.3.3 |
| numpy | 2.5.2 |
| pyarrow | 25.0.1 |
| pandera | 0.32.1 |
| lightgbm | 4.7.0 |
| mlflow | 3.15.1 |
| pandas-stubs (dev) | 3.0.5.260730 |
| pyshp (dev) | 3.1.6 |
| pyproj (dev) | 3.7.2 |

## Decisions Made

- **Task 1 checkpoint** treated as pre-approved based on the user's earlier-this-session PyPI verification of both `pyshp` and `pyproj` — see "Task 1 Checkpoint Verdict" above.
- **`train_trip_duration_model` mutates `x` in place** (categorical dtype cast, not a defensive copy) — matches RESEARCH.md Pattern 4 exactly and is required for LightGBM predict-time category-set consistency (see Deviations below).
- **`[[tool.mypy.overrides]]` for `pyarrow.*`** added to `pyproject.toml` — `pyarrow` ships no `py.typed` marker, so `mypy --strict` otherwise flags every attribute access as untyped; this is standard practice for this specific library, not a general strictness relaxation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `train_trip_duration_model` defensive copy broke predict-time categorical alignment**
- **Found during:** Task 3, first `pytest` run of `test_train_trip_duration_model_predicts_finite_values` and `test_full_chain_produces_finite_positive_rmse`.
- **Issue:** Initial implementation defensively copied `x` inside `train_trip_duration_model` before casting `CATEGORICAL_FEATURES` to `category` dtype, to avoid mutating the caller's frame. LightGBM records the exact category set seen during `fit` and requires the `predict`-time frame to carry an identically-typed categorical column; because the cast only happened on the internal copy, calling `model.predict(x)` with the caller's original (still-`int`-typed) `x` raised `ValueError: train and valid dataset categorical_feature do not match.`
- **Fix:** Removed the defensive copy; the function now casts categorical columns on `x` in place, matching RESEARCH.md's Pattern 4 exactly, so the caller's own `x` (used for both `fit` and later `predict`) carries the correct dtype forward.
- **Files modified:** `lib/train.py`
- **Commit:** `6956adb` (Task 3 commit — caught and fixed before commit, not a separate follow-up)

**2. [Rule 3 - Blocking issue] `mypy --strict` failures on `pyarrow` stub gap, `Any`-return, and `dict[str, object]` unpack**
- **Found during:** Task 3, running `scripts/qa.sh typecheck` before committing.
- **Issue:** Three unrelated `mypy --strict` failures blocked the commit: (a) `pyarrow`/`pyarrow.parquet` have no `py.typed` marker, so every attribute resolved to an untyped-import error; (b) `read_month_chunked`'s `pd.concat(...)` call inferred `Any` because its input list's element type traced back to the untyped `pyarrow` batch objects, triggering `no-any-return` against the declared `pd.DataFrame` return type; (c) `LGBM_PARAMS`'s inferred `dict[str, object]` type couldn't satisfy `LGBMRegressor`'s heterogeneously-typed keyword parameters when unpacked with `**`.
- **Fix:** Added `[[tool.mypy.overrides]]` for `module = "pyarrow.*"` with `ignore_missing_imports = true` (standard practice for stub-less libraries); wrapped the `pd.concat` return in `typing.cast(pd.DataFrame, ...)`; explicitly annotated `LGBM_PARAMS: dict[str, Any]` so the `**`-unpack type-checks against `Any`-compatible keyword slots.
- **Files modified:** `lib/ingest.py`, `lib/train.py`, `lib/registry.py` (also fixed `ANN401` on `ModelRegistry.__init__`'s `client` param by typing it as `mlflow.MlflowClient` instead of `Any`), `pyproject.toml`
- **Commit:** `6956adb` (Task 3 commit — caught and fixed before commit)

**3. [Rule 3 - Blocking issue] `E501` line-length violation in `lib/features.py` docstring**
- **Found during:** Task 3, running `scripts/qa.sh lint` before committing.
- **Issue:** `load_zone_centroids`'s docstring exceeded the 100-character line-length limit by 1 character.
- **Fix:** Shortened the docstring wording (no meaning lost).
- **Files modified:** `lib/features.py`
- **Commit:** `6956adb` (Task 3 commit — caught and fixed before commit)

**4. [Rule 1 - Bug] `SettingWithCopyWarning` in test fixtures feeding `train_trip_duration_model`**
- **Found during:** Task 3, first green `pytest` run (warnings, not failures).
- **Issue:** After fixing Deviation 1 (in-place categorical cast inside `train_trip_duration_model`), the test's `x = features[FEATURE_COLUMNS]` produced a pandas view/slice rather than an independent frame; mutating it in place inside `train_trip_duration_model` triggered `SettingWithCopyWarning`.
- **Fix:** Changed the two call sites in `tests/lib/test_tracer_end_to_end.py` to `x = features[FEATURE_COLUMNS].copy()` — the correct caller-side hygiene practice when a function is documented to mutate its argument in place.
- **Files modified:** `tests/lib/test_tracer_end_to_end.py`
- **Commit:** `6956adb` (Task 3 commit — caught and fixed before commit)

---

**Total deviations:** 4 auto-fixed (2 Rule 1 bugs, 2 Rule 3 blocking issues), all caught and resolved before the Task 3 commit landed — none shipped in a broken state.
**Impact on plan:** All four were necessary for correctness (Deviation 1, 4) or for the pre-existing quality gates to pass (Deviation 2, 3). No scope creep — nothing outside Task 3's six modules and one test file was touched beyond the `pyproject.toml` mypy-override addition (a one-block config addition, not a rewrite).

## TDD Gate Compliance

Task 3 (`type="tracer" tdd="true"`) does **not** show separate `test(...)` (RED) and `feat(...)` (GREEN) commits in `git log` — both land in the single commit `6956adb`.

**Why:** This repository's `.pre-commit-config.yaml` (installed in Phase 1, plan 01-02) wires a `pytest` hook (`entry: scripts/qa.sh test`) that runs the **full** test suite with a `--cov-fail-under=100` gate on every `git commit`. A literal RED-phase commit — the test file staged alone, intentionally failing because the six `lib/` modules don't exist yet — would be blocked by this same hook (`ModuleNotFoundError`), and skipping pre-commit hooks (`--no-verify` or pre-commit's own `SKIP=` mechanism) without explicit user request is prohibited by this executor's own operating constraints.

**What was actually done to satisfy the spirit of RED/GREEN:** the test file (`tests/lib/test_tracer_end_to_end.py`) was written first, against the six modules' intended public interfaces per `## Artifacts this phase produces` and RESEARCH.md's verified patterns. Before writing any `lib/` module, all six were temporarily moved out of the `lib/` directory and `pytest tests/lib/test_tracer_end_to_end.py` was run — confirmed **RED**: `ModuleNotFoundError: No module named 'lib.evaluate'` (the first import in dependency order). The six modules were then restored/implemented and the same test run reached **GREEN** (all 12 behavior tests + 8 coverage-closing tests passing, 100% branch coverage). Both the RED verification and the GREEN implementation are real — only the git-commit-level separation was collapsed into one commit, for the pre-commit-hook reason above.

## Issues Encountered

None beyond the four auto-fixed deviations documented above — no unresolved problems.

## User Setup Required

None — no external service configuration required. `lib/registry.py`'s `ModelRegistry` is used only against a mocked `MlflowClient` in this phase; no real MLflow server exists until Phase 3.

## Verification

All ran clean on the final tree:

- `scripts/qa.sh lint && scripts/qa.sh format && scripts/qa.sh typecheck && scripts/qa.sh test && scripts/qa.sh boundary` → exit 0, 100% branch coverage (109/109 statements, 12/12 branches), 20/20 tests passing.
- `pre-commit run --all-files` → all five hooks Passed, matching CI verdict (README.md's parity claim holds).
- Symbol-presence check (all seven `[02-01]`-tagged symbols per module) → `symbols-ok`.
- Window check (`month_range(TLC_START_MONTH, TLC_END_MONTH)` has 12 entries, contains `2020-03`) → `window-ok`.
- No-cluster-import AST scan across `lib/*.py` → `no-cluster-imports-ok`.
- `pyshp`/`pyproj` confirmed present only under `dev`, never under `ml` (`toml` assertion script) → `ok`.

## Known Stubs

None. All six `lib/` modules are real, working implementations against the `[02-01]`-tagged symbol subset — narrow (only the symbols this plan owns), not stubbed. The "plus" symbols listed in `## Artifacts this phase produces` (e.g. `FilterReport`, `filter_trip_quality`, `chronological_split`, `save_model`, `load_booster`, `CANDIDATE_ALIAS`, `promote_to_champion`) are intentionally out of scope for this plan — they belong to plans 02-03 and 02-04 per the phase's wave assignment, not omissions from this one.

## Threat Flags

None beyond what the plan's own `<threat_model>` already covers. T-02-SC (package tampering via `pyshp`/`pyproj` install) was mitigated by the Task 1 checkpoint verdict recorded above. T-02-01 (untrusted Parquet structure/dtypes) is mitigated by `lib/schemas.py`'s pandera validation running before any downstream module trusts the frame. T-02-05 (ingest memory footprint) is mitigated by `read_month_chunked`'s `iter_batches` bounding. T-02-02 (registry credential handling) remains `accept`-dispositioned as planned — this phase injects a mocked client only, no real MLflow URI/token/credential exists yet.

## Next Phase Readiness

- The six `lib/` module interfaces are locked and proven end-to-end — plans 02-02 (data acquisition scripts), 02-03 (modelling tail: split/train/evaluate/registry expansion), 02-04 (ingest gate: row-level pre-filter + full schema), and 02-05 (features/benchmark/README) can now expand these modules in their assigned waves without renegotiating signatures.
- `data/` directory exists (empty except `.gitkeep`) — plan 02-02 will populate `data/zone_centroids.csv`.
- No blockers. `scripts/qa.sh test`'s 100%-branch-coverage gate is satisfied on the current tree; later plans must keep it satisfied as they add row-level filtering, the real MLflow-backed alias promotion, and the download/precompute scripts.

## Self-Check: PASSED

- `lib/ingest.py` exists: FOUND
- `lib/schemas.py` exists: FOUND
- `lib/features.py` exists: FOUND
- `lib/train.py` exists: FOUND
- `lib/evaluate.py` exists: FOUND
- `lib/registry.py` exists: FOUND
- `tests/lib/test_tracer_end_to_end.py` exists: FOUND
- `.planning/phases/02-data-model-engineering-lib/02-01-SUMMARY.md` exists: FOUND
- Commit `6ef9381` (Task 2 — ml dependency group + qa.sh/CI): FOUND in `git log --oneline --all`
- Commit `6956adb` (Task 3 — end-to-end tracer): FOUND in `git log --oneline --all`
- Task 1 automated verify (`grep -qiE 'pyshp.*(approved|rejected)'` against this SUMMARY): PASSED
- `scripts/qa.sh lint/format/typecheck/test/boundary` on the final tree: all exit 0
- Working tree clean except pre-existing untracked `.gsd/` (present before this plan started, out of this plan's scope)

---
*Phase: 02-data-model-engineering-lib*
*Completed: 2026-08-20*
