---
phase: 02-data-model-engineering-lib
plan: 04
subsystem: data-model-engineering
tags: [pandera, pyarrow, chunked-read, data-quality, D-09a]

requires:
  - phase: 02-data-model-engineering-lib
    provides: "lib.ingest's TLC_START_MONTH/TLC_END_MONTH/TLC_DATA_DIR/month_parquet_path/read_month_chunked/add_trip_duration and lib.schemas' trip_schema/validate_trips (plan 02-01 tracer); the real 12-month data/tlc/ Parquet cache (plan 02-02)"
provides:
  - "lib.ingest.FilterReport: frozen dataclass counting every dropped row by reason (dropped_non_positive_distance, dropped_non_positive_duration, dropped_unmapped_zone, dropped_passenger_count, total_rows, kept_rows)"
  - "lib.ingest.filter_trip_quality(df) -> (kept_df, FilterReport): the D-09a row-level pre-filter tier, order-preserving"
  - "lib.ingest.load_month(month, data_dir, batch_size) -> (validated_df, FilterReport): the full ingest boundary orchestrator (read -> duration -> filter+log -> validate)"
  - "lib.ingest.read_month_chunked: hardened to handle the zero-row/zero-batch case without raising"
  - "lib.schemas.trip_schema: hardened D-09a tier-one structural gate with a real Check on trip_duration_s and PLACEHOLDER_ZONE_IDS as a shared frozenset"
  - "Empirical proof: all 12 real TLC months (2019-07..2020-06) pass load_month with dropped rates 3.7%-7.1%, never raising"
affects: [02-05]

actuals:
  tokens: 6325
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns:
    - "D-09a two-tier enforcement: lib.ingest.filter_trip_quality pre-filters and counts routine row-level noise (non-positive distance/duration, placeholder zone IDs 264/265, out-of-range passenger_count) before lib.schemas.trip_schema runs; the schema's own Checks stay real (not removed) as a structural-drift/regression backstop that should never fire on an already-filtered frame"
    - "Shared boundary constants (PLACEHOLDER_ZONE_IDS, PASSENGER_COUNT_MIN/MAX) live in lib.schemas and are imported by lib.ingest, so the filter and the schema cannot silently drift apart on where the tier boundary sits"
    - "read_month_chunked builds the empty-frame case from the Parquet file's own Arrow schema (schema_arrow.empty_table()) rather than letting pd.concat([]) raise on a zero-batch file"
    - "load_month emits a single INFO log record naming the month and every dropped count before validation runs — the mechanism that satisfies REQ-C1's 'not silently' under D-09a"

key-files:
  created:
    - tests/lib/test_ingest.py
    - tests/lib/test_schemas.py
  modified:
    - lib/ingest.py
    - lib/schemas.py
    - tests/lib/test_tracer_end_to_end.py

key-decisions:
  - "Kept (did not remove) trip_schema's pre-existing pa.Check.gt(0) on trip_distance, and added an equivalent gt(0) Check on trip_duration_s, per the plan's explicit Task 2 action text and acceptance criteria (which require >=1 real Check on trip_distance). Reconciled against the orchestrator's flagged tension with D-09a's tier split: these Checks are real and should legitimately never fire on real data once filter_trip_quality has already removed the offending rows before validate_trips runs — they exist as a structural-drift/regression backstop (defense-in-depth against a filter bug or a bypassed ingest path), not as duplicated row-level enforcement, and their presence is what keeps the schema from degrading into a dtype-only passthrough per the plan's explicit prohibition."
  - "Verified live that pandera's dtype check for 'datetime64[ns]' tolerates a datetime64[us] source column (real TLC Parquet files read back as datetime64[us] under this pandas/pyarrow pin, not [ns]) while still correctly rejecting a genuinely non-datetime dtype — confirmed no cast/normalization was needed in lib.ingest for the schema to validate real months."
  - "Tasks 1 and 2 landed in a single combined commit rather than two separate task commits: the pre-commit hook's full-suite pytest gate collects tests/lib/test_ingest.py regardless of git staging, and that file imports lib.ingest.FilterReport, which does not exist until lib/ingest.py's Task-1 changes are also staged. Committing lib/schemas.py alone (Task 2) left an intermediate ImportError state the hook correctly rejected. Same precedent documented in plan 02-01's SUMMARY (Task 3)."

patterns-established:
  - "Independent per-reason boolean masks in filter_trip_quality (not mutually exclusive) so a row violating two rules is counted under both reasons — kept_rows + all four dropped counters only sums to total_rows when each row violates at most one rule, which is the common case on real data but not a structural guarantee"

requirements-completed: [REQ-C1, REQ-C4]

coverage:
  - id: D1
    description: "read_month_chunked reads in bounded batches, writes nothing, preserves source row order, and handles empty/single-row Parquet files without raising"
    requirement: "REQ-C4"
    verification:
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_read_month_chunked_returns_all_rows_in_source_order"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_read_month_chunked_zero_row_file_returns_empty_frame_with_columns"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_read_month_chunked_single_row_file_returns_that_row"
        status: pass
    human_judgment: false
  - id: D2
    description: "add_trip_duration derives unrounded float64 seconds, preserving fractional-second precision"
    requirement: "REQ-C1"
    verification:
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_add_trip_duration_preserves_fractional_seconds_without_rounding"
        status: pass
    human_judgment: false
  - id: D3
    description: "filter_trip_quality attributes every dropped row to one of four counted reasons (distance, duration, unmapped zone, passenger count), preserves relative order, and handles the empty-frame edge case"
    requirement: "REQ-C1"
    verification:
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_filter_trip_quality_drops_non_positive_trip_distance"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_filter_trip_quality_drops_zero_and_negative_duration"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_filter_trip_quality_drops_placeholder_zone_ids_keeps_boundary_zones"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_filter_trip_quality_drops_passenger_count_0_and_7_keeps_1_and_6_and_null"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_filter_trip_quality_preserves_relative_order_of_unsorted_input"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_filter_trip_quality_empty_frame_returns_empty_frame_and_all_zero_report"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_filter_trip_quality_report_accounts_for_every_row_single_violation_each"
        status: pass
    human_judgment: false
  - id: D4
    description: "load_month emits a single INFO log record naming the month and every dropped count before validation, and raises FileNotFoundError naming the missing path"
    requirement: "REQ-C1"
    verification:
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_load_month_emits_info_log_with_month_and_counts"
        status: pass
      - kind: unit
        ref: "tests/lib/test_ingest.py#test_load_month_raises_file_not_found_for_absent_month"
        status: pass
    human_judgment: false
  - id: D5
    description: "trip_schema carries a real Check on every D-09 column plus the dropoff>=pickup wide check, tolerates all-null fee columns and extra columns, and hard-fails on missing column / wrong dtype / zone id 300 / null key column / dropoff-before-pickup"
    requirement: "REQ-C1"
    verification:
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_trip_schema_carries_real_checks_per_column"
        status: pass
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_validate_trips_raises_on_missing_required_column"
        status: pass
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_validate_trips_raises_on_wrong_dtype"
        status: pass
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_validate_trips_raises_on_zone_id_outside_valid_range"
        status: pass
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_validate_trips_raises_on_null_in_key_column"
        status: pass
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_validate_trips_raises_on_dropoff_before_pickup"
        status: pass
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_validate_trips_passes_with_extra_unlisted_column"
        status: pass
      - kind: unit
        ref: "tests/lib/test_schemas.py#test_validate_trips_passes_with_all_null_fee_columns"
        status: pass
    human_judgment: false
  - id: D6
    description: "All 12 real TLC months (2019-07 through 2020-06) pass load_month without raising, each logging a small non-zero filter rate, proving the two-tier design on real data"
    requirement: "REQ-C1"
    verification:
      - kind: manual_procedural
        ref: "uv run python3 -c 'iterate month_range(...) calling load_month per month' — 12/12 months completed, dropped rates 3.71%-7.11%, none exceeding the 10% flag threshold (see Twelve-Month Real-Data Table below)"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-08-20
status: complete
---

# Phase 2 Plan 4: Ingest Boundary — Chunked Read, Quality Pre-Filter, Structural Schema Summary

**`lib/ingest.py` gains `FilterReport`/`filter_trip_quality`/`load_month` implementing D-09a's row-level pre-filter tier, `lib/schemas.py`'s `trip_schema` is hardened into the structural tier (real Check on every D-09 column including a new `trip_duration_s` positivity check), and all 12 real downloaded TLC months (2019-07 through 2020-06) pass the full two-tier gate with dropped rates between 3.71% and 7.11% — proving the split between routine per-row noise and genuine schema drift on real data, not just synthetic fixtures.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-08-20T08:03:00Z
- **Completed:** 2026-08-20T08:38:00Z
- **Tasks:** 3/3
- **Files modified:** 5 (2 lib/ modules, 2 new test modules, 1 pre-existing test module fixed)

## Accomplishments

- `lib/ingest.py`'s `read_month_chunked` now handles the zero-row Parquet case (builds the empty frame from the file's own Arrow schema instead of letting `pd.concat([])` raise) and carries a docstring documenting its read-only, writes-nothing contract for Phase 3's `ParallelFor` fan-out.
- New `FilterReport` frozen dataclass and `filter_trip_quality(df)` pre-filter D-09a's four row-level noise reasons — non-positive `trip_distance`, non-positive `trip_duration_s`, placeholder zone IDs 264/265, out-of-range `passenger_count` — via independent boolean masks, preserving row order and keeping null `passenger_count` rows.
- New `load_month(month, data_dir, batch_size)` orchestrates the full boundary (read → derive duration → filter+log → validate), raising `FileNotFoundError` naming the missing path and emitting a single INFO log record naming the month and every dropped count before validation runs.
- `lib/schemas.py`'s `trip_schema` gains a real `Check.gt(0)` on `trip_duration_s` alongside the existing D-09 checks; `PLACEHOLDER_ZONE_IDS` becomes a `frozenset` shared with `lib.ingest` so the two tiers cannot silently drift apart.
- All 12 real months in `data/tlc/` pass `load_month` without raising — the empirical proof RESEARCH.md's Assumptions Log A3/A4 asked for, confirming the ~1% baseline noise rate measured on the single January-2019 sample holds (within the same order of magnitude) across the whole pinned window, including the COVID-collapse months.
- 27 new tests (15 in `tests/lib/test_ingest.py`, 12 in `tests/lib/test_schemas.py`) pin every boundary from the plan's `<behavior>` spec; the full suite (77 tests) holds 100% branch coverage on `lib/`.

## Task Commits

Tasks 1 and 2 landed in a single combined commit (see "Decisions Made" for why); Task 3 required no code changes.

1. **Task 1 + Task 2: D-09a ingest gate — chunked read, quality pre-filter, structural schema hardening** — `9d6d84a` (feat)
2. **Task 3: Prove the two-tier gate against all 12 real months** — no code commit (all 12 months passed; no new filter reason was necessary). This SUMMARY (plus the metadata commit) is the task's only artifact, per the plan's own `<files>` spec.

**Plan metadata:** committed alongside this SUMMARY (see final commit).

## Files Created/Modified

- `lib/ingest.py` — `read_month_chunked` hardened for the zero-row case; `add_trip_duration` docstring documents its no-rounding contract; new `FilterReport`, `filter_trip_quality`, `load_month`
- `lib/schemas.py` — `trip_schema` gains a `trip_duration_s` Check; `PLACEHOLDER_ZONE_IDS` becomes a shared `frozenset`; `validate_trips` docstring documents the D-09a tier boundary
- `tests/lib/test_ingest.py` — new, 15 tests covering chunked-read edge cases, duration precision, all four filter reasons, order preservation, empty-frame/report accounting, and `load_month`'s logging/`FileNotFoundError` behavior
- `tests/lib/test_schemas.py` — new, 12 tests covering the clean-pass case, every structural-failure mode (missing column, wrong dtype, zone id 300, null key column, dropoff-before-pickup), extra/fee-column tolerance, and per-column Check introspection
- `tests/lib/test_tracer_end_to_end.py` — 2 pre-existing `validate_trips` tests updated to route through `add_trip_duration` first, since `trip_duration_s` is now a required schema column

## Twelve-Month Real-Data Table (Task 3)

All figures from `lib.ingest.load_month` run against the real `data/tlc/*.parquet` cache (plan 02-02). No month raised; every dropped percentage is well under the 10% flag threshold.

| Month | Total Rows | Kept | Dropped-Distance | Dropped-Duration | Dropped-Zone | Dropped-Passenger | Dropped % |
|---|---|---|---|---|---|---|---|
| 2019-07 | 6,310,419 | 6,061,680 | 67,669 (1.07%) | 8,223 (0.13%) | 85,755 (1.36%) | 116,951 (1.85%) | 3.94% |
| 2019-08 | 6,073,357 | 5,827,989 | 69,155 (1.14%) | 6,975 (0.11%) | 86,783 (1.43%) | 110,402 (1.82%) | 4.04% |
| 2019-09 | 6,567,788 | 6,310,197 | 71,182 (1.08%) | 5,991 (0.09%) | 86,266 (1.31%) | 120,591 (1.84%) | 3.92% |
| 2019-10 | 7,213,891 | 6,940,120 | 69,913 (0.97%) | 5,219 (0.07%) | 86,657 (1.20%) | 137,656 (1.91%) | 3.80% |
| 2019-11 | 6,878,111 | 6,612,489 | 72,990 (1.06%) | 5,640 (0.08%) | 80,416 (1.17%) | 129,849 (1.89%) | 3.86% |
| 2019-12 | 6,896,317 | 6,633,316 | 72,764 (1.06%) | 4,779 (0.07%) | 83,740 (1.21%) | 125,410 (1.82%) | 3.81% |
| 2020-01 | 6,405,008 | 6,166,470 | 70,200 (1.10%) | 4,406 (0.07%) | 71,185 (1.11%) | 114,367 (1.79%) | 3.72% |
| 2020-02 | 6,299,367 | 6,065,919 | 60,485 (0.96%) | 3,975 (0.06%) | 65,525 (1.04%) | 123,635 (1.96%) | 3.71% |
| 2020-03 | 3,007,687 | 2,888,414 | 31,396 (1.04%) | 2,131 (0.07%) | 32,025 (1.06%) | 63,455 (2.11%) | 3.97% |
| 2020-04 | 238,073 | 222,767 | 6,225 (2.61%) | 315 (0.13%) | 3,305 (1.39%) | 6,583 (2.77%) | **6.43%** |
| 2020-05 | 348,415 | 323,658 | 10,226 (2.94%) | 630 (0.18%) | 6,144 (1.76%) | 9,609 (2.76%) | **7.11%** |
| 2020-06 | 549,797 | 513,186 | 17,438 (3.17%) | 584 (0.11%) | 7,635 (1.39%) | 13,309 (2.42%) | **6.66%** |

**Flag note (none exceed 10%, but three months are notably elevated):** 2020-04/05/06 — the COVID-collapse recovery months — show dropped rates roughly 1.7x-1.9x the pre-COVID baseline (6.4%-7.1% vs. ~3.7%-4.0%). This tracks with the much smaller absolute row counts in these months (238K-550K rows vs. 6-7M pre-collapse): the same roughly-constant per-trip noise sources (meter glitches, canceled/void trips, GPS errors) make up a larger share of a much smaller denominator, not a change in per-trip data quality. 2020-03 and 2020-04 also show the COVID volume collapse itself (`total_rows` drops from 3.0M in March to 238K in April, a ~92% month-over-month decline) — the drift evidence REQ-D1's README rationale will cite.

## D-09a Tier Boundary As Implemented (for README's data-quality section and Phase 3's validate component to quote)

`lib.ingest.filter_trip_quality` pre-filters and counts four routine row-level noise reasons — non-positive `trip_distance`, non-positive `trip_duration_s`, placeholder zone IDs 264/265 (TLC's `Unknown`/`Outside of NYC` pseudo-zones with no shapefile geometry), and out-of-range `passenger_count` — *before* the frame reaches `lib.schemas.trip_schema`; `lib.ingest.load_month` logs the full `FilterReport` at INFO immediately after filtering, which is what makes REQ-C1's "not silently" requirement true even though the filtering itself is not a hard failure. `trip_schema` then validates only structural integrity (column presence, correct dtypes, zone IDs within \[1, 263\], non-null key columns, dropoff-not-before-pickup) against the already-filtered frame — its row-level `Check`s (distance/duration positivity, zone/passenger-count range) remain real Checks rather than being removed, but by design they should never fire on real data once the pre-filter has run: they exist as a structural-drift/regression backstop (catching a filter bug or a bypassed ingest path), not as duplicated row-level enforcement. A genuinely malformed month — a renamed/missing column, a wrong dtype, or a zone ID outside \[1, 263\] that is not the known 264/265 case — still raises a pandera `SchemaErrors` and exits non-zero with the failing column and check named, which is the "fails loudly" REQ-C1 actually asks for.

## Decisions Made

- **Kept `trip_distance`'s `pa.Check.gt(0)` and added an equivalent `trip_duration_s` Check**, rather than removing row-level Checks from the schema entirely, per the plan's explicit Task 2 action text and acceptance criteria (`len(trip_schema.columns['trip_distance'].checks) >= 1`). This reconciles the orchestrator's flagged tension with D-09a: the Checks stay real specifically because they should never fire on an already-filtered frame — removing them would leave the schema unable to catch a filter regression, and the plan's own prohibitions explicitly forbid a dtype-only passthrough schema.
- **Verified pandera's `"datetime64[ns]"` dtype Check tolerates a `datetime64[us]` source column** (confirmed real TLC Parquet files read back as `[us]` precision under this pandas 2.3.3/pyarrow 25.0.1 pin, not `[ns]`) while still correctly rejecting a genuinely non-datetime dtype (e.g. object/string). This meant no dtype-normalization code was needed in `lib.ingest` — the schema as written (unmodified from the tracer's declaration) already validates real months correctly.
- **Tasks 1 and 2 combined into one commit** — see "Deviations from Plan" below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Task 1 and Task 2 could not land as separate atomic commits under the repo's pre-commit hook**
- **Found during:** First attempt to commit Task 2 (`lib/schemas.py` + `tests/lib/test_schemas.py`) alone, leaving `lib/ingest.py`'s Task 1 changes and `tests/lib/test_ingest.py` unstaged/untracked.
- **Issue:** `.pre-commit-config.yaml`'s `pytest` hook runs the full test suite against the working tree regardless of git staging. It stashes tracked-but-unstaged changes (reverting `lib/ingest.py` to its pre-plan, tracer-era content for the hook run) but leaves untracked files (the new `tests/lib/test_ingest.py`) in place — so the hook run collected a test file importing `lib.ingest.FilterReport` against a version of `lib/ingest.py` that didn't define it yet, failing with `ImportError`.
- **Fix:** Staged and committed both tasks' `lib/` and test changes together in a single commit, since they must be internally consistent for the full-suite gate to pass. Same precedent documented in plan 02-01's SUMMARY (its Task 3 also collapsed into one commit for an analogous pre-commit-hook reason).
- **Files modified:** `lib/ingest.py`, `lib/schemas.py`, `tests/lib/test_ingest.py`, `tests/lib/test_schemas.py`, `tests/lib/test_tracer_end_to_end.py`
- **Commit:** `9d6d84a`

**2. [Rule 1 - Bug] Pre-existing tracer test `test_validate_trips_returns_clean_frame_unchanged` broke under the hardened schema**
- **Found during:** Full-suite `pytest` run after hardening `trip_schema`, before the Task 1+2 commit.
- **Issue:** `tests/lib/test_tracer_end_to_end.py`'s two `validate_trips`-calling tests passed a synthetic frame directly from `_synthetic_trip_frame()`, which has no `trip_duration_s` column — a column the newly-hardened `trip_schema` now requires (`COLUMN_NOT_IN_DATAFRAME` `SchemaErrors`). This is a direct, intended consequence of Task 2's schema hardening, not a bug in the new code, but the pre-existing test's assumption was now stale.
- **Fix:** Updated both call sites to route the fixture through `add_trip_duration` first, matching `validate_trips`'s documented contract (expects a frame that has already been through `lib.ingest.add_trip_duration`).
- **Files modified:** `tests/lib/test_tracer_end_to_end.py`
- **Commit:** `9d6d84a` (caught and fixed before commit)

---

**Total deviations:** 2 (1 Rule 3 process/tooling constraint, 1 Rule 1 bug — a stale pre-existing test fixture made stale by the plan's own intended schema hardening).
**Impact on plan:** No scope creep. Both deviations were direct, necessary consequences of executing the plan's own Task 1/Task 2 instructions under this repo's existing pre-commit gate; no `lib/` module outside `ingest.py`/`schemas.py` was touched, and no test outside the two new files plus the two pre-existing `validate_trips` call sites was modified.

## Issues Encountered

None beyond the two auto-fixed deviations documented above.

## User Setup Required

None — no external service configuration required. Task 3 reads the already-downloaded local `data/tlc/` cache (plan 02-02); no network calls were made.

## Next Phase Readiness

- `lib/ingest.py` and `lib/schemas.py` now expose their full `[02-04]`-tagged public surface (`FilterReport`, `filter_trip_quality`, `load_month`, plus the hardened `trip_schema`/`validate_trips`) — plan 02-05 (vectorized haversine, dtype downcasting, README benchmark table) can build directly on `load_month` as the canonical per-month entry point instead of composing `read_month_chunked`/`add_trip_duration`/`validate_trips` manually.
- The Twelve-Month Real-Data Table above is the raw material plan 02-05's README benchmark/drift-rationale section needs — both the per-reason filter rates and the COVID volume-collapse numbers (2020-03: 3.0M rows -> 2020-04: 238K rows) are now recorded with exact figures.
- No blockers. `scripts/qa.sh lint/format/typecheck/test/boundary` all exit 0 on the final tree (77/77 tests, 100% branch coverage on `lib/`), and the working tree is clean except the pre-existing untracked `.gsd/` directory (present before this plan started, out of scope).
- Per the orchestrator's instructions, this plan does not merge back into `development` or open a PR — that is the orchestrator's responsibility once this SUMMARY and the plan-metadata commit land on `feature/02-04-ingest-gate`.

## Self-Check: PASSED

- `lib/ingest.py` exists and contains `FilterReport`/`filter_trip_quality`/`load_month`: FOUND
- `lib/schemas.py` exists and contains the hardened `trip_schema`: FOUND
- `tests/lib/test_ingest.py` exists, 15 tests: FOUND
- `tests/lib/test_schemas.py` exists, 12 tests: FOUND
- Commit `9d6d84a` (Task 1+2 — ingest gate + schema hardening): FOUND in `git log --oneline --all`
- `scripts/qa.sh lint/format/typecheck/test/boundary` on the final tree: all exit 0, 100% branch coverage (191/191 statements, 30/30 branches)
- AST check (`iter_batches` present, `read_parquet` absent in `lib/ingest.py`): `chunked-ok`
- All 12 real months in `data/tlc/` pass `load_month` without raising: confirmed (see Twelve-Month Real-Data Table)
- `git status --porcelain` shows no leftover untracked script from Task 3's throwaway invocation, only the pre-existing `.gsd/` directory

---
*Phase: 02-data-model-engineering-lib*
*Completed: 2026-08-20*
