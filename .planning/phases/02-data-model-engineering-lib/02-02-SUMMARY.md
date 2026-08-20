---
phase: 02-data-model-engineering-lib
plan: 02
subsystem: data-acquisition
tags: [tlc-parquet, cloudfront, pyshp, pyproj, shapefile, zip-slip, haversine]

requires:
  - phase: 02-data-model-engineering-lib
    provides: "lib.ingest's TLC_START_MONTH/TLC_END_MONTH/TLC_DATA_DIR/month_parquet_path window pin (plan 02-01), lib.months.month_range, lib.features.load_zone_centroids's zone_id/centroid_lat/centroid_lon column contract, pyshp+pyproj pre-approved in the dev group"
provides:
  - "scripts/download_tlc_data.py: idempotent, atomic-rename, fail-loud downloader for the pinned 12-month TLC Yellow Parquet window into gitignored data/tlc/"
  - "scripts/precompute_zone_centroids.py: reproducible shapefile-to-CSV precompute (pyshp read + pure-Python area-weighted shoelace centroid + pyproj EPSG:2263->EPSG:4326 reprojection), with a zip-slip extraction guard and a shape-count/bounding-box/Newark-coordinate refuse-to-write gate"
  - "data/zone_centroids.csv: committed, 263 rows, zone_id/centroid_lat/centroid_lon, the D-06 haversine join source"
affects: [02-03, 02-04, 02-05]

actuals:
  tokens: 4910
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Atomic .part-then-rename streamed download, non-200/zero-byte treated as hard failure (T-02-04)"
    - "Zip-slip extraction guard: reject absolute-path, symlink, or resolved-path-escaping zip members before any write (T-02-03)"
    - "Refuse-to-write gate on a precompute script: assert expected shape count + coordinate sanity before touching the output file, so a silently-changed upstream source fails loud instead of producing a corrupt short table"

key-files:
  created:
    - scripts/download_tlc_data.py
    - scripts/precompute_zone_centroids.py
    - data/zone_centroids.csv
  modified: []

key-decisions:
  - "Kept both scripts free of any mypy --strict scope (pyproject.toml's [tool.mypy] files=[\"lib\"] and the pre-commit hook both exclude scripts/) — verified this is the existing repo convention (Task 1's pre-commit run showed 'mypy --strict lib ... Skipped' for a scripts/-only change) rather than a gap this plan needed to close."
  - "Wrote the legacy-S3-host reference in scripts/download_tlc_data.py's comment as 'the widely-cited legacy direct-S3 host' rather than the literal domain string, after the first draft's literal mention tripped the plan's own acceptance check (grep -c 's3.amazonaws.com' must return 0) against its own explanatory comment."

requirements-completed: [REQ-C2, REQ-D1]

coverage:
  - id: D1
    description: "scripts/download_tlc_data.py fetches exactly the 12 pinned monthly Yellow Parquet files (2019-07 through 2020-06) into data/tlc/, skips already-cached non-empty files on rerun, and fails loudly (non-zero exit) on any non-200 or zero-byte response"
    requirement: "REQ-D1"
    verification:
      - kind: manual_procedural
        ref: "uv run python scripts/download_tlc_data.py (first run: 12 downloaded / 0 skipped, exit 0); second run: 0 downloaded / 12 skipped, exit 0; find data/tlc -name '*.parquet' -size -1k -> 0; ls data/tlc/*.part -> none"
        status: pass
    human_judgment: false
  - id: D2
    description: "data/zone_centroids.csv is committed with exactly 263 rows, header zone_id,centroid_lat,centroid_lon, every coordinate inside the NYC bounding box, and zone 1 (Newark Airport) within 0.01 degrees of the known real-world coordinate"
    requirement: "REQ-C2"
    verification:
      - kind: manual_procedural
        ref: "python -c centroids-ok assertion script (see plan 02-02 acceptance criteria) -> prints 'centroids-ok'; head -1/tail -n +2/cut+grep checks on data/zone_centroids.csv"
        status: pass
    human_judgment: false
  - id: D3
    description: "The precompute script is reproducible (byte-identical CSV across two runs) and readable by lib.features.load_zone_centroids"
    requirement: "REQ-C2"
    verification:
      - kind: manual_procedural
        ref: "two consecutive `uv run python scripts/precompute_zone_centroids.py` runs -> identical md5sum 88c6717ec26ce58bbfdbfa673e534ba5; `python -c 'from lib.features import load_zone_centroids; print(len(load_zone_centroids()))'` -> 263"
        status: pass
    human_judgment: false
  - id: D4
    description: "The zip extraction routine's zip-slip guard raises rather than writes when handed a member whose resolved path escapes the work directory"
    requirement: "REQ-C2"
    verification:
      - kind: unit
        ref: "ad hoc script constructing a zip with a '../../etc/passwd-evil' member and calling _extract_zip_safely -> ValueError: refusing to extract member outside dest dir"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-08-20
status: complete
---

# Phase 2 Plan 2: Data Acquisition Summary

**Real 12-month TLC Yellow Parquet cache (839.5MB, 12/12 files) plus a reproducible, area-weighted, multi-part-aware 263-row zone-centroid CSV precomputed from TLC's shapefile via pyshp + pyproj — the two external-data artifacts the rest of Phase 2 joins against.**

## Performance

- **Duration:** ~20 min (dominated by the ~5-minute real download of 801MB across 12 files)
- **Tasks:** 2/2
- **Files modified:** 3 (2 created scripts, 1 committed data artifact)

## Accomplishments

- `scripts/download_tlc_data.py` streamed all 12 pinned months (2019-07..2020-06, per `lib.ingest.TLC_START_MONTH`/`TLC_END_MONTH`) from the verified CloudFront host into `data/tlc/` — 839,516,647 bytes total, sizes ranging from 4.4MB (2020-04, the COVID demand collapse month) to 106.3MB (2019-10).
- A second run of the same script downloaded 0 months and reported 12 skips, proving idempotency; `data/tlc/` remains untracked by git (`data/tlc/` was already in `.gitignore` from plan 02-01).
- `scripts/precompute_zone_centroids.py` downloaded TLC's `taxi_zones.zip`, extracted it behind a zip-slip guard, read all 263 polygon shapes via `pyshp`, computed an area-weighted centroid per zone (23 multi-part zones combined by area-weighted ring averaging), reprojected EPSG:2263 feet to EPSG:4326 degrees via a module-scope `pyproj.Transformer`, and wrote `data/zone_centroids.csv`.
- Zone 1 (Newark Airport) landed at `(40.691830, -74.174002)` against the real-world `(40.6918, -74.174)` — the end-to-end read-compute-reproject chain verified correct on the first real run, no iteration needed.
- Two consecutive precompute runs produced a byte-identical CSV (`md5sum 88c6717ec26ce58bbfdbfa673e534ba5`), and `lib.features.load_zone_centroids()` reads all 263 rows successfully, satisfying the plan 02-01 reader contract.

## Task Commits

Each task was committed atomically:

1. **Task 1: Download the pinned 12-month TLC Parquet window into the gitignored cache** — `f58e2c0` (feat)
2. **Task 2: Precompute the 263-row zone-centroid lookup table** — `2baaa4a` (feat)

## Files Created/Modified

- `scripts/download_tlc_data.py` — standalone CLI (`--start-month`, `--end-month`, `--dest`, `--force`); streams to a `.part` sibling then atomically renames, treats non-200/zero-byte as a hard failure, prints a downloaded/skipped/bytes-on-disk summary
- `scripts/precompute_zone_centroids.py` — standalone CLI (`--url`, `--out`, `--work-dir`); zip-slip-guarded extraction, `pyshp` read by `LocationID` field name (not positional index), shoelace-formula area-weighted centroid per ring combined across multi-part shapes, `pyproj` reprojection, refuse-to-write gate on shape count / bounding box / Newark coordinate
- `data/zone_centroids.csv` — committed, 263 rows, `zone_id,centroid_lat,centroid_lon`, 6-decimal-place coordinates, sorted ascending by `zone_id`

## Decisions Made

- **mypy scope left untouched for `scripts/`** — confirmed via Task 1's pre-commit hook output (`mypy --strict lib ... Skipped` on a `scripts/`-only diff) that `pyproject.toml`'s `[tool.mypy] files = ["lib"]` deliberately excludes `scripts/`; both new scripts pass `ruff check`/`ruff format --check` under the `ANN`-enabled profile (full type annotations throughout) but were not run through `mypy --strict` as a gating step, matching the plan's own `<verify>` blocks which likewise only require ruff.
- **Comment wording avoids the literal dead-host domain string** — `scripts/download_tlc_data.py`'s explanatory comment about the legacy S3 host was rephrased to avoid the literal `s3.amazonaws.com` substring after it was caught failing the plan's own `grep -c 's3.amazonaws.com' scripts/download_tlc_data.py` acceptance check (which expects `0`, i.e. the dead host must not appear anywhere in the file, including comments).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Explanatory comment tripped the plan's own dead-host acceptance check**
- **Found during:** Task 1, running the acceptance-criteria grep checks after the first `ruff check`/`ruff format` pass.
- **Issue:** The first draft of `scripts/download_tlc_data.py` included a code comment literally naming `s3.amazonaws.com` to explain why the CloudFront host is used instead. The plan's Task 1 acceptance criteria run `grep -c 's3.amazonaws.com' scripts/download_tlc_data.py` and require it to return `0` — the comment itself (not just live code) triggered a match.
- **Fix:** Reworded the comment to say "the widely-cited legacy direct-S3 host" without the literal domain string, preserving the explanatory intent without matching the check.
- **Files modified:** `scripts/download_tlc_data.py`
- **Commit:** `f58e2c0` (Task 1 commit — caught and fixed before commit)

**2. [Rule 1 - Bug] E501 line-length violation in `_zone_centroid_lonlat`'s signature**
- **Found during:** Task 2, first `ruff check` run.
- **Issue:** The function signature line (`def _zone_centroid_lonlat(points: ..., parts: ...) -> tuple[float, float]:`) exceeded the 100-character line-length limit by 2 characters.
- **Fix:** Wrapped the parameter list across multiple lines (standard `ruff format`-compatible style).
- **Files modified:** `scripts/precompute_zone_centroids.py`
- **Commit:** `2baaa4a` (Task 2 commit — caught and fixed before commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1, both caught by lint/acceptance checks before either task's commit landed).
**Impact on plan:** No scope creep — both fixes were confined to the exact files each task already owned; no `lib/` module or test file was touched.

## Issues Encountered

None beyond the two auto-fixed deviations documented above. The zone-centroid precompute pipeline worked correctly on the first real end-to-end run against the live shapefile (no iteration needed on the centroid math itself) — RESEARCH.md's live verification of the same formula against Newark Airport's coordinate in the prior planning session carried over directly.

## User Setup Required

None — no external service configuration required. Both scripts are one-time/repeatable maintainer-run CLIs against public TLC endpoints; no credentials involved.

## Next Phase Readiness

- `data/tlc/` now holds the real 12-month Parquet cache that plan 02-04's ingest-gate work and the REQ-C5 benchmark (plan 02-05) need for credible, non-toy numbers.
- `data/zone_centroids.csv` is committed and satisfies `lib.features.load_zone_centroids`'s exact column contract from plan 02-01 — plan 02-05's `build_features`/benchmark work can join against it immediately with no further precompute step.
- No `lib/` module or test file was modified by this plan, so wave-2 sibling plan 02-03 (modelling tail: split/train/evaluate/registry expansion) ran/runs with zero risk of either plan's gates observing the other's in-flight edits, per the plan's own `<verification>` section.
- No blockers. `scripts/qa.sh lint/format/typecheck/test/boundary` all pass clean on the final tree (20/20 tests, 100% branch coverage on `lib/`, unaffected by this plan's scripts-only changes).

## Self-Check: PASSED

- `scripts/download_tlc_data.py` exists: FOUND
- `scripts/precompute_zone_centroids.py` exists: FOUND
- `data/zone_centroids.csv` exists: FOUND, 263 data rows, tracked by git
- Commit `f58e2c0` (Task 1 — TLC Parquet download): FOUND in `git log --oneline --all`
- Commit `2baaa4a` (Task 2 — zone-centroid precompute): FOUND in `git log --oneline --all`
- `data/tlc/` has 12 non-empty `.parquet` files, 0 `.part` files, untracked by git: confirmed
- `git ls-files --error-unmatch data/zone_centroids.csv`: succeeds
- `scripts/qa.sh lint/format/typecheck/test/boundary` on the final tree: all exit 0

---
*Phase: 02-data-model-engineering-lib*
*Completed: 2026-08-20*
