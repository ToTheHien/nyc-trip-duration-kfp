---
phase: 02-data-model-engineering-lib
plan: 05
subsystem: data-model-engineering
tags: [numpy, haversine, dtype-downcasting, benchmark, tracemalloc, drift-window]

requires:
  - phase: 02-data-model-engineering-lib
    provides: "lib.ingest.load_month (plan 02-04) as the real per-month pipeline entry point; data/zone_centroids.csv (plan 02-02, D-06); the Twelve-Month Real-Data Table (plan 02-04) as the drift-window evidence source"
provides:
  - "lib.features.haversine_km: unchanged vectorized formula, now provably the only distance path build_features can reach (DataFrame.apply/Series.apply monkeypatch-to-raise test)"
  - "lib.features.haversine_km_rowwise(df) -> pd.Series: DataFrame.apply-based readable baseline, the benchmark's comparison arm and the vectorized path's test oracle"
  - "lib.features.join_zone_centroids(df, centroids) -> pd.DataFrame: two left merges attaching pu_lat/pu_lon/do_lat/do_lon, row-count invariant"
  - "lib.features.downcast_features(df) -> pd.DataFrame: the REQ-C3 dtype contract (float32 distance/duration/passenger_count, ZONE_CATEGORY_DTYPE zones, category VendorID, int8 hour/dayofweek), wired into build_features as its final step"
  - "build_features now raises ValueError naming every unmapped zone id instead of silently emitting a null distance"
  - "scripts/benchmark_features.py: real, runnable four-variant time+memory benchmark over a real cached TLC month, via lib.ingest.load_month"
  - "README.md Feature Engineering Benchmark and Dataset and Drift Window sections, with the script's real generated output pasted verbatim"
affects: []

actuals:
  tokens: 9700
  tasks: 3
  commits: 2

tech-stack:
  added: []
  patterns:
    - "downcast_features uses Series.astype(np.float32) directly, not pd.to_numeric(..., downcast='float') as RESEARCH.md's code example suggested: pandas' to_numeric downcast only takes effect when the round trip through the smaller dtype is exactly lossless, which real continuous doubles (trip_distance_km, trip_duration_s, ...) essentially never are - it silently no-ops back to float64 on realistic data. astype(np.float32) always downcasts and still handles NaN in passenger_count natively (the NaN-safety concern to_numeric's advice was actually guarding against was the integer-downcast case, not this one)."
    - "FEATURE_COLUMNS changed from a list literal to a tuple: the plan's module-level-mutable-state AST check flags any top-level List/Dict/Set literal assignment. Two existing call sites that indexed a DataFrame with the bare constant (df[FEATURE_COLUMNS]) were updated to df[list(FEATURE_COLUMNS)], since pandas treats a bare tuple key as a single MultiIndex-style lookup, not a sequence of column names."
    - "scripts/benchmark_features.py measures via lib.ingest.load_month (not a reimplemented reader), deriving month/data_dir from the --parquet path's filename so the real two-tier D-09a gate runs before any timing starts - the benchmark measures the production pipeline, not a synthetic stand-in."

key-files:
  created:
    - tests/lib/test_features.py
    - scripts/benchmark_features.py
  modified:
    - lib/features.py
    - tests/lib/test_train.py
    - tests/lib/test_tracer_end_to_end.py
    - README.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "astype(np.float32) instead of pd.to_numeric(downcast='float') for the float32 columns (see tech-stack pattern above) - a direct consequence of the plan's own prohibition against a downcast that silently no-ops."
  - "FEATURE_COLUMNS: list -> tuple, with the two downstream df[FEATURE_COLUMNS] call sites fixed to df[list(FEATURE_COLUMNS)] - required to satisfy the plan's explicit AST no-module-level-mutable-state acceptance check without breaking existing indexing usage."
  - "downcast_features is wired into build_features as its final step *before* column selection (per the plan's explicit action text), operating on the full merged frame (including pu_lat/do_lat etc.) rather than only the already-selected FEATURE_COLUMNS subset; those extra coordinate columns are simply dropped at the subsequent column-selection step, untouched by downcast_features' explicit per-column mapping."
  - "Tasks 1 and 2 landed in a single commit (not separate test/feat commits) for the same pre-commit-hook reason documented in every prior Phase 2 plan's SUMMARY: the repo's pytest hook runs the full 100%-coverage suite on every commit regardless of staging, so a literal RED-phase commit (tests referencing downcast_features before it exists) would be blocked by the hook itself. RED was verified manually instead - see Deviations."

patterns-established:
  - "haversine_km_rowwise exists purely as the benchmark's comparison arm and the vectorized formula's test oracle; it is never imported or called from build_features, and a monkeypatch-to-raise test on both DataFrame.apply and Series.apply pins that build_features' production path never falls back to it."

requirements-completed: [REQ-C2, REQ-C3, REQ-C5, REQ-D1]

coverage:
  - id: D1
    description: "haversine_km is exact at zero separation (clamped arcsin argument), matches an independent closed-form equatorial-degree check within 0.5%, and agrees with haversine_km_rowwise within 1e-9 over 50 rows"
    requirement: "REQ-C2"
    verification:
      - kind: unit
        ref: "tests/lib/test_features.py#test_haversine_km_identical_coordinates_returns_exact_zero"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_haversine_km_matches_known_equatorial_one_degree_distance"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_haversine_km_and_rowwise_agree_within_1e9"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_features never reaches DataFrame.apply/Series.apply on its production path, is pure (does not mutate its input) and idempotent (two calls on the same input produce equal frames), and raises ValueError naming every zone id with no centroid match"
    requirement: "REQ-C2"
    verification:
      - kind: unit
        ref: "tests/lib/test_features.py#test_build_features_never_calls_dataframe_or_series_apply"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_build_features_does_not_mutate_input_frame"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_build_features_is_idempotent"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_build_features_raises_valueerror_naming_unmapped_zone_ids"
        status: pass
    human_judgment: false
  - id: D3
    description: "downcast_features produces the exact documented per-column dtype contract (float32 distance/duration/passenger_count including NaN-safety, 263-category zone dtype, category VendorID, int8 hour/dayofweek), preserves values within 1e-4 relative error, strictly reduces memory_usage(deep=True), and leaves its input's dtypes unchanged"
    requirement: "REQ-C3"
    verification:
      - kind: unit
        ref: "tests/lib/test_features.py#test_downcast_features_produces_float32_for_numeric_feature_columns"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_downcast_features_produces_263_category_zone_dtype_and_vendor_category"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_downcast_features_preserves_nan_in_passenger_count"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_downcast_features_preserves_values_within_relative_tolerance"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_downcast_features_reduces_memory_usage"
        status: pass
      - kind: unit
        ref: "tests/lib/test_features.py#test_downcast_features_returns_new_frame_leaves_input_dtypes_unchanged"
        status: pass
    human_judgment: false
  - id: D4
    description: "lib/features.py carries no module-level mutable state and imports none of pyshp/pyproj/geopandas/shapely/fiona"
    requirement: "REQ-C2"
    verification:
      - kind: unit
        ref: "AST check: python -c \"...bad=[...ast.Dict/List/Set/comprehensions...]; assert not bad\" -> no-module-mutable-state-ok"
        status: pass
      - kind: unit
        ref: "AST check: python -c \"...roots.intersection({'shapefile','pyproj','geopandas','shapely','fiona'})...\" -> features-runtime-lean-ok"
        status: pass
    human_judgment: false
  - id: D5
    description: "scripts/benchmark_features.py runs against a real cached TLC month via lib.ingest.load_month and prints a four-variant markdown table with real numeric elapsed-time and memory columns, no placeholders"
    requirement: "REQ-C5"
    verification:
      - kind: manual_procedural
        ref: "UV_PROJECT_ENVIRONMENT=path/to/venv uv run --extra dev --extra ml python scripts/benchmark_features.py --rows 200000 -> exit 0, real table printed (see README's pasted output)"
        status: pass
    human_judgment: false
  - id: D6
    description: "The vectorized haversine path is measurably faster than the row-wise baseline, and the downcast frame is measurably smaller than the float64/object frame, both reported as ratios"
    requirement: "REQ-C5"
    verification:
      - kind: manual_procedural
        ref: "scripts/benchmark_features.py real run: speedup ~554-579x (row-wise/vectorized), memory ratio 2.77x (pre-downcast/downcast) over 200,000 real 2019-07 rows"
        status: pass
    human_judgment: false
  - id: D7
    description: "README carries the generated benchmark table verbatim (not hand-written/rounded), the regeneration command, and states the 2019-07..2020-06 drift-window rationale citing the March-2020 COVID collapse"
    requirement: "REQ-C5"
    verification:
      - kind: unit
        ref: "python -c \"...s=t.split('## Feature Engineering Benchmark')[1]; rows=[l for l in s.splitlines() if l.startswith('|')]; assert len(rows)>=6...\" -> benchmark-table-ok"
        status: pass
      - kind: unit
        ref: "grep -q '## Dataset and Drift Window' README.md"
        status: pass
    human_judgment: false
  - id: D8
    description: "README's Dataset and Drift Window section names 2019-07, 2020-06, and the March-2020 COVID demand collapse as the drift rationale, and no longer claims Phase 2 logic is future work"
    requirement: "REQ-D1"
    verification:
      - kind: manual_procedural
        ref: "README.md Dataset and Drift Window section (2020-03: 3,007,687 rows -> 2020-04: 238,073 rows, ~92% decline, cited from plan 02-04's Twelve-Month Real-Data Table); Status section rewritten"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-08-22
status: complete
---

# Phase 2 Plan 5: Feature Benchmark & Drift Window Summary

**`lib/features.py`'s distance path is now provably vectorized, pure, idempotent, and free of geo-stack runtime imports; `downcast_features` gives every feature column an explicit, tested dtype contract; and `scripts/benchmark_features.py` produced a real four-variant time/memory table (~554-579x haversine speedup, 2.77x memory reduction) over 200,000 real 2019-07 TLC rows, now pasted verbatim into README alongside the REQ-D1 drift-window rationale.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-08-22T00:00:00Z (approx, session start)
- **Completed:** 2026-08-22
- **Tasks:** 3/3
- **Files modified:** 6 (1 lib/ module, 1 new test module, 2 pre-existing test modules, README.md, REQUIREMENTS.md) + 1 new script

## Accomplishments

- `lib/features.py`'s `haversine_km` stays a pure numpy-ufunc vectorized formula with the `[0.0, 1.0]` arcsin clamp (already present from the tracer); a new `haversine_km_rowwise` provides the `DataFrame.apply`-based readable baseline used both as the benchmark's comparison arm and as the vectorized formula's test oracle (agreement within 1e-9 over 50 rows).
- New `join_zone_centroids` performs the two left merges explicitly (row-count invariant); `build_features` now raises `ValueError` naming every zone id that survives the join with no centroid match, instead of silently carrying a null distance forward. A test proves the production path never reaches `DataFrame.apply`/`Series.apply` at all (both monkeypatched to raise).
- New `downcast_features` implements REQ-C3's exact dtype contract (float32 for `trip_distance`/`trip_distance_km`/`trip_duration_s`/`passenger_count`, the fixed 263-category `ZONE_CATEGORY_DTYPE` for `PULocationID`/`DOLocationID`, `category` for `VendorID`, `int8` for `pickup_hour`/`pickup_dayofweek`), NaN-safe on `passenger_count`, value-preserving to 1e-4 relative error, and measurably memory-reducing; wired into `build_features` as its final step.
- `FEATURE_COLUMNS` changed from a list to an immutable tuple to satisfy the plan's module-level-mutable-state AST check; the two downstream `df[FEATURE_COLUMNS]` indexing call sites (`tests/lib/test_train.py`, `tests/lib/test_tracer_end_to_end.py`) were updated to `df[list(FEATURE_COLUMNS)]`.
- New `scripts/benchmark_features.py` loads a real cached TLC month through `lib.ingest.load_month` (the real pipeline path) and measures four variants — row-wise haversine, vectorized haversine, the natural float64/object joined frame, and the downcast frame — with `time.perf_counter` (best of 3 repeats) and `tracemalloc` peak allocation, rendering a markdown table plus speedup/memory ratios.
- A real run over 200,000 rows of `2019-07` measured vectorized haversine ~554-579x faster than the row-wise baseline and the downcast frame ~2.77x smaller than the natural frame — both strictly favorable, as required.
- README's Status section no longer claims Phase 2 logic is future work; new `## Feature Engineering Benchmark` section holds the script's real generated table verbatim plus the regeneration command; new `## Dataset and Drift Window` section states the `2019-07`..`2020-06` window, the March-2020 COVID collapse rationale (citing plan 02-04's measured 3,007,687 -> 238,073 row month-over-month collapse), the D-06 zone-centroid-table rationale, and the D-09a two-tier validation stance with its observed filter rates.
- 20 new tests in `tests/lib/test_features.py`; full suite (97 tests) holds 100% branch coverage on `lib/`.

## Task Commits

1. **Task 1 + Task 2: Vectorized haversine, zone-centroid join, and dtype-downcasting contract** — `f327f6c` (feat)
2. **Task 3: Benchmark script, README table, and drift-window rationale** — `7bdc230` (feat)

**Plan metadata:** committed alongside this SUMMARY (see final commit).

## Files Created/Modified

- `lib/features.py` — `haversine_km_rowwise`, `join_zone_centroids`, `downcast_features` added; `build_features` hardened (unmapped-zone `ValueError`, wired downcast, provably `.apply`-free); `FEATURE_COLUMNS` changed list -> tuple; module docstring documents the dtype contract table
- `tests/lib/test_features.py` — new, 20 tests covering haversine correctness/agreement, join row-count invariance, build_features purity/idempotency/apply-freedom/unmapped-zone error, and every downcast_features dtype/NaN/tolerance/memory/non-mutation assertion
- `tests/lib/test_train.py`, `tests/lib/test_tracer_end_to_end.py` — updated `df[FEATURE_COLUMNS]` call sites to `df[list(FEATURE_COLUMNS)]` (tuple-as-single-key fix, see Deviations)
- `scripts/benchmark_features.py` — new, four-variant time+memory benchmark CLI (`--parquet`/`--rows`/`--out`) over a real cached TLC month via `lib.ingest.load_month`
- `README.md` — Status section rewritten; new `## Feature Engineering Benchmark` and `## Dataset and Drift Window` sections
- `.planning/REQUIREMENTS.md` — REQ-C5 traceability row: Pending -> Complete

## Decisions Made

- **`astype(np.float32)` instead of `pd.to_numeric(..., downcast="float")`** for the float32 columns in `downcast_features`. RESEARCH.md's code example used `to_numeric(downcast="float")`, but live testing showed pandas only applies that downcast when the round trip through the smaller dtype is exactly lossless — for real-valued continuous doubles like `trip_distance_km`/`trip_duration_s`, that's essentially never true, so `to_numeric` silently no-ops back to float64. This is precisely the "downcast must not silently no-op" prohibition the plan calls out. `astype(np.float32)` always downcasts and still handles `passenger_count`'s NaN natively — the NaN-safety concern behind the `to_numeric` advice was specifically about *integer* downcasts, not this float case.
- **`FEATURE_COLUMNS`: list -> tuple.** The plan's explicit AST acceptance check flags any top-level `List`/`Dict`/`Set` literal assignment in `lib/features.py` as module-level mutable state. Converting to a tuple satisfies the check; the two places that indexed a DataFrame directly with the bare constant (`df[FEATURE_COLUMNS]`) needed `list(...)` wrapping, since pandas interprets a bare tuple key as a single MultiIndex-style lookup rather than a column-name sequence — `[*FEATURE_COLUMNS, TARGET_COLUMN]` unpacking (used inside `lib/features.py` itself) is unaffected.
- **Tasks 1 and 2 committed together**, matching the precedent set in every prior Phase 2 plan's SUMMARY (see Deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `pd.to_numeric(..., downcast="float")` silently failed to downcast real continuous values**
- **Found during:** Task 2, first `pytest` run of `test_downcast_features_produces_float32_for_numeric_feature_columns`.
- **Issue:** Following RESEARCH.md's code example literally (`pd.to_numeric(df[col], downcast="float")`) left `trip_distance`/`trip_distance_km`/`trip_duration_s`/`passenger_count` at `float64` for a 20-row synthetic frame of realistic random magnitudes — pandas' `downcast="float"` only takes effect when the value round-trips exactly through the smaller dtype, which is essentially never true for continuous doubles.
- **Fix:** Switched to `Series.astype(np.float32)` directly, which always downcasts and still preserves NaN in `passenger_count` (verified with a dedicated test).
- **Files modified:** `lib/features.py`
- **Commit:** `f327f6c`

**2. [Rule 3 - Blocking issue] `df[FEATURE_COLUMNS]` broke once `FEATURE_COLUMNS` became a tuple**
- **Found during:** Task 1, first full-suite `pytest` run after the AST-check-driven list -> tuple change.
- **Issue:** `tests/lib/test_train.py` and `tests/lib/test_tracer_end_to_end.py` both indexed a DataFrame with the bare `FEATURE_COLUMNS` constant (`df[FEATURE_COLUMNS]`); pandas treats a bare tuple key as a single (MultiIndex-style) lookup rather than a sequence of column names, raising `KeyError` on the whole tuple.
- **Fix:** Updated both call sites to `df[list(FEATURE_COLUMNS)]`.
- **Files modified:** `tests/lib/test_train.py`, `tests/lib/test_tracer_end_to_end.py`
- **Commit:** `f327f6c`

**3. [Process/tooling constraint, matching every prior Phase 2 plan] Tasks 1 and 2 could not land as separate `test(...)`/`feat(...)` (RED/GREEN) commits, or even as two separate task commits**
- **Found during:** Planning the commit sequence for Task 1 (tdd="true") before starting implementation.
- **Issue:** This repo's pre-commit `pytest` hook runs the full 100%-coverage suite on every commit regardless of git staging. A literal RED-phase commit (the test file alone, referencing `downcast_features`/`haversine_km_rowwise`/`join_zone_centroids` before they exist) would fail the hook with `ImportError`/`AttributeError`, and skipping hooks is prohibited. Task 1 and Task 2 also both modify the same two files (`lib/features.py`, `tests/lib/test_features.py`) with tightly coupled behavior (`build_features` calls `downcast_features` internally), so splitting them into two commits would have required an artificial intermediate state.
- **What was actually done to satisfy the spirit of RED/GREEN:** All 20 tests in `tests/lib/test_features.py` were written first per the `<behavior>` specs for both tasks. `pytest tests/lib/test_features.py` was run against the implementation as it was built incrementally, confirming each new test failed for the expected reason (`AttributeError: module 'lib.features' has no attribute 'haversine_km_rowwise'`, then a real dtype-mismatch failure on the `pd.to_numeric` no-op described in Deviation 1 above) before the corresponding implementation code made it pass. Only the git-commit-level RED/GREEN separation was collapsed into one commit per task-pair, for the pre-commit-hook reason above — same precedent documented in plans 02-01 and 02-04's SUMMARYs.
- **Files modified:** N/A (process note, not a code fix)
- **Commit:** `f327f6c`

---

**Total deviations:** 3 (1 Rule 1 bug caught before commit, 1 Rule 3 blocking-issue fix, 1 process/tooling constraint matching established Phase 2 precedent).
**Impact on plan:** No scope creep. All three deviations are direct, necessary consequences of executing the plan's own instructions (RESEARCH.md's suggested `to_numeric` pattern, the plan's own AST acceptance check) under this repo's existing pre-commit gate and pandas' own indexing semantics.

## Issues Encountered

None beyond the three auto-fixed/documented deviations above.

## User Setup Required

None — no external service configuration required. `scripts/benchmark_features.py` reads only the already-downloaded local `data/tlc/` cache (plan 02-02) and `data/zone_centroids.csv`; no network calls were made.

## Next Phase Readiness

- Phase 2 is now fully complete: all of REQ-C1 through REQ-C5 and REQ-D1 through REQ-D3 are implemented and evidenced (REQ-C5 traceability row updated Pending -> Complete in this plan; the other Phase 2 requirement rows were already Complete from plans 02-01 through 02-04).
- `lib.features.FEATURE_COLUMNS`/`TARGET_COLUMN`/`ZONE_CATEGORY_DTYPE`/`build_features`/`downcast_features` are the stable, dtype-pinned contract `lib.train.train_trip_duration_model` trains on — Phase 3's KFP components can wrap `build_features`/`downcast_features` directly with no further dtype negotiation.
- README's `## Feature Engineering Benchmark` and `## Dataset and Drift Window` sections are the raw material Phase 3's README consolidation (REQ-E1/E2/E3) can build on directly (architecture diagram, ADRs, "Next Steps").
- No blockers. `scripts/qa.sh lint/format/typecheck/test/boundary` and `pre-commit run --all-files` all exit 0 on the final tree (97/97 tests, 100% branch coverage on `lib/`), and the working tree is clean except the pre-existing untracked `.gsd/` directory (present before this plan started, out of scope).
- Per the orchestrator's instructions, this plan does not merge back into `development` or open a PR — that is the orchestrator's responsibility once this SUMMARY and the plan-metadata commit land on `feature/02-05-benchmark`.

## Self-Check: PASSED

- `lib/features.py` contains `haversine_km_rowwise`/`join_zone_centroids`/`downcast_features`: FOUND
- `tests/lib/test_features.py` exists, 20 tests: FOUND
- `scripts/benchmark_features.py` exists and runs against real data: FOUND (verified live, real table printed)
- Commit `f327f6c` (Task 1+2 — haversine + dtype contract): FOUND in `git log --oneline --all`
- Commit `7bdc230` (Task 3 — benchmark script + README): FOUND in `git log --oneline --all`
- `scripts/qa.sh lint/format/typecheck/test/boundary` on the final tree: all exit 0, 100% branch coverage (97/97 tests)
- `pre-commit run --all-files`: all 5 hooks Passed
- README.md contains `## Feature Engineering Benchmark` and `## Dataset and Drift Window`: FOUND
- `git status --porcelain` shows no leftover untracked files beyond the pre-existing `.gsd/` directory

---
*Phase: 02-data-model-engineering-lib*
*Completed: 2026-08-22*
