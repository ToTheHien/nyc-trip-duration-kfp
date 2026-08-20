# Phase 2: Data & Model Engineering (lib/) - Research

**Researched:** 2026-08-20
**Domain:** Offline pandas/numpy/LightGBM/MLflow feature-and-model engineering (no Kubernetes)
**Confidence:** HIGH on the data-source/schema/CRS findings (independently verified live this session — see Sources); MEDIUM on library API patterns (Context7 official docs); MEDIUM on general vectorization/downcast technique (cross-checked web sources)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-06 (Distance Feature Source):** NYC TLC dropped raw pickup/dropoff lat/lon from the Yellow/Green trip record schema starting July 2016 — the 2019–2020 window has zone IDs only. Haversine distance (REQ-C2) is computed from a **static zone-centroid lookup table**: a small CSV (`zone_id, centroid_lat, centroid_lon`) precomputed once from TLC's public taxi zone data and committed to the repo, joined against `PULocationID`/`DOLocationID` per trip. Explicitly rejected: pulling in `geopandas`/`shapely` at runtime — too heavy a dependency for the 10–15h budget. Reversibility: reversible (swapping the static lookup for a shapefile-derived one later is a data-source change behind the same join).
- **D-07 (Dataset Scale):** Download the real, full 12-month NYC TLC Parquet window now (not sampled/synthetic), via a one-time download script; cache locally, gitignored. Real data backs `ingest`/`features` development and the REQ-C5 benchmark table. Unit tests (`pytest`) continue using tiny synthetic DataFrame fixtures for speed/determinism (matches `tests/lib/test_months.py`).
- **D-08 (Train/Test Split):** Chronological (time-based) split — train on earlier months, test/evaluate on the final months, which span the drift event. A random split was explicitly rejected (it would average across the drift and hide the signal the 12-month window exists to demonstrate).
- **D-09 (pandera Schema Strictness):** Concrete, real `Check`s — not a passthrough dtype-only schema:
  - Non-null on key columns (pickup/dropoff datetime, `PULocationID`/`DOLocationID`, trip distance/duration).
  - `trip_distance` and computed trip duration both strictly positive.
  - `PULocationID`/`DOLocationID` within TLC's valid zone-ID range (1–263).
  - Dropoff datetime ≥ pickup datetime.
  - `passenger_count` within a reasonable bound (reject obviously corrupt values, e.g. 0 or absurdly high).
  A month that fails any check fails loudly (non-zero exit, logged reason) — the whole month is rejected, not silently filtered row-by-row.

### Claude's Discretion

- Exact LightGBM hyperparameter config (num_leaves, learning_rate, etc.) — a single fixed, reasonable config per REQ-D2 ("boring", no tuning). Document chosen values and rationale briefly; specific numbers left to planner/executor judgment.
- Internal module boundaries within `lib/` beyond `research/ARCHITECTURE.md`'s sketch (`ingest.py`, `schemas.py`, `features.py`, `train.py`, `evaluate.py`, `registry.py`) — naming/helper-function granularity left to planner.
- Exact benchmark methodology mechanics (script vs. notebook cell vs. pytest-adjacent timing harness) — planner's call, as long as the README table has real, reproducible numbers per REQ-C5.
- Download-script mechanics for the 12-month TLC Parquet pull (D-07) — retry/resume behavior, exact CLI shape — left to executor discretion.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 2 scope. No scope-creep suggestions arose.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-C1 | pandera schema validation at ingest boundary with real `Check`s (not passthrough); malformed month fails loudly | See "pandera 0.32.1 Schema Patterns" (Code Examples) and Pitfall 6 (real-data violation-rate tension with "whole month fails loudly") |
| REQ-C2 | Vectorized haversine distance replacing `.apply()` | See "Vectorized Haversine" (Code Examples) and D-06 zone-centroid precompute pipeline (fully verified this session) |
| REQ-C3 | dtype downcasting (float64→float32, category dtypes) | See "dtype Downcasting" (Code Examples); Pitfall 8 covers nullable-float columns that block naive downcast |
| REQ-C4 | Chunked reads for ingest | See "Chunked Parquet Reads" (Code Examples) — `pyarrow.parquet.ParquetFile.iter_batches` |
| REQ-C5 | Before/after benchmark table (time + memory) in README | Methodology left to executor per CONTEXT.md; `tracemalloc`/`time.perf_counter` pattern noted in Common Pitfalls |
| REQ-D1 | 12-month NYC TLC window spanning drift event | See "TLC Data Source" (Standard Stack / verified URL + schema) |
| REQ-D2 | LightGBM trip-duration regression, no tuning | See "LightGBM 4.7.0 Minimal Config" (Code Examples) |
| REQ-D3 | MLflow registry, champion/candidate aliasing | See "MLflow Registry Client Wrapper" (Code Examples) |
</phase_requirements>

## Summary

This phase is almost entirely offline data-engineering work with one genuinely hard sub-problem: producing an accurate `zone_id → (lat, lon)` centroid lookup without `geopandas`/`shapely`. That sub-problem is now fully solved and verified end-to-end this session: TLC's public `taxi_zones.zip` shapefile is in **NAD83 State Plane NY Long Island (feet), EPSG:2263 — not WGS84 degrees** — so a lightweight three-step pipeline (`pyshp` to read polygon vertices → a pure-Python area-weighted polygon-centroid formula → `pyproj` to reproject feet→degrees) produces a correct centroid (verified against Newark Airport's real-world coordinates to within noise). Both `pyshp` and `pyproj` are far lighter than `geopandas`/`shapely` (no GEOS/Fiona dependency) and satisfy D-06's rejection of the heavy stack.

Every other piece of this phase (TLC download URL, exact 2019-2020 column schema, pandera/LightGBM/MLflow API syntax) was independently confirmed this session — either by directly downloading and inspecting the real files (data source, schema, CRS, zone-ID range) or via official Context7-sourced documentation (pandera, LightGBM, MLflow). One substantive design tension surfaced from live-data inspection and needs an explicit planning decision: real TLC data has ~1% of rows with non-positive `trip_distance` and ~0.08% with non-positive duration in every sampled month — under pandera's default `validate()` semantics (fail on any violating row), D-09's row-level `Check`s as literally read would reject essentially every one of the 12 months, not just genuinely malformed ones. See Pitfall 6 and Open Question 1.

**Primary recommendation:** Build the zone-centroid CSV with a one-time `scripts/precompute_zone_centroids.py` (pyshp + pyproj + pure-Python centroid formula, dev-only dependency group) and commit the resulting small CSV to the repo; keep `lib/features.py`'s runtime haversine path dependent only on pandas/numpy against that CSV. Split pandera's D-09 checks into two enforcement tiers — hard structural checks (missing/renamed columns, wrong dtypes, `PULocationID`/`DOLocationID` present) that should legitimately never fail on real 2019-2020 data and should cause a loud whole-month rejection, versus row-level numeric-quality checks (distance/duration positivity, passenger_count bounds) that the planner must explicitly decide whether to pre-filter-and-log (recommended) or leave as hard failures (which will reject nearly every real month).

## Architectural Responsibility Map

This project's tiers are `lib/` (pure logic, this phase), `components/` (thin KFP wrapper, Phase 3), `pipelines/` (DAG orchestration, Phase 3), and external services (MLflow, TLC source). Per `REQ-A6`/`research/ARCHITECTURE.md`'s "thin component, fat lib" rule, every capability below is owned by `lib/` in this phase; `components/` only gains a thin wrapper in Phase 3.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Chunked Parquet ingest (REQ-C4) | `lib/ingest.py` | — | Pure I/O + pandas logic, zero KFP imports required; testable with tiny synthetic Parquet fixtures |
| Schema validation (REQ-C1) | `lib/schemas.py` | — | pandera schemas are plain Python objects; validated against a DataFrame, no cluster needed |
| Zone-centroid precompute (D-06) | `scripts/` (one-time, not `lib/`) | `lib/features.py` (consumes output CSV) | The pyshp/pyproj computation is a repo-maintainer-run precompute step, not a runtime dependency of the pipeline — keeping it out of `lib/` keeps `lib/`'s and any future `components/features` image's runtime dependency footprint small |
| Vectorized haversine + downcasting (REQ-C2, REQ-C3) | `lib/features.py` | — | Pure numpy/pandas; the whole point of REQ-C2/C3 is that this is provable without a cluster |
| LightGBM training (REQ-D2) | `lib/train.py` | — | `lgb.LGBMRegressor` operates on an in-memory DataFrame; no KFP/MLflow coupling needed to unit-test |
| Evaluation / champion comparison (REQ-D3) | `lib/evaluate.py` | `lib/registry.py` (reads champion RMSE) | RMSE computation is pure math; the champion lookup crosses into the MLflow client, kept in a separate module so `evaluate.py` stays mockable without a client |
| MLflow registry client wrapper (REQ-D3) | `lib/registry.py` | External Service (MLflow, mocked this phase) | Only place in Phase 2 that talks to an external service's API surface — kept thin and 100% mockable via `unittest.mock.patch` on `MlflowClient`, per `PITFALLS.md` Pitfall 7/8 |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pandas` | 2.3.x (verified latest patch on PyPI: 2.3.3) [VERIFIED: `pip index versions pandas`] | DataFrame engine for `lib/` | Already pinned in `research/STACK.md`; matches `pyproject.toml`'s reserved `ml` group |
| `numpy` | 2.5.x (verified latest: 2.5.2) [VERIFIED: `pip index versions numpy`] | Vectorized haversine, dtype downcasting | Already pinned in `research/STACK.md` |
| `pyarrow` | Latest compatible with pandas 2.3.x (verified 25.0.1 exists on PyPI) [VERIFIED: `pip index versions pyarrow`] | Parquet I/O, chunked reads via `ParquetFile.iter_batches` (REQ-C4) | Confirmed live: `pandas.read_parquet` has no `chunksize` param — `pyarrow.parquet.ParquetFile.iter_batches()` is the native chunked-read primitive [CITED: arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html] |
| `pandera` | 0.32.1 [VERIFIED: `pip index versions pandera` — exact match to STACK.md pin] | Schema validation at ingest boundary (REQ-C1) | Purpose-built declarative DataFrame schema/Check library; official docs confirm `pa.Column(..., checks=[...])` and DataFrameSchema-level "wide checks" for cross-column validation [CITED: unionai-oss/pandera docs via Context7] |
| `lightgbm` | 4.7.0 [VERIFIED: `pip index versions lightgbm` — exact match to STACK.md pin] | Trip-duration regression (REQ-D2) | Native pandas categorical support avoids manual one-hot encoding for `PULocationID`/`DOLocationID`/`VendorID` [CITED: lightgbm-org/lightgbm docs via Context7] |
| `mlflow` (client only) | 3.15.1 [VERIFIED: `pip index versions mlflow` — exact match to STACK.md pin] | Registry client wrapper (REQ-D3) | MLflow 3.x's `set_registered_model_alias`/`get_model_version_by_alias` is the current, non-deprecated champion/candidate API [CITED: mlflow/mlflow docs via Context7, high-reputation source] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pandas-stubs` | Matching pandas minor [VERIFIED: exists on PyPI] | `mypy --strict` type coverage for `lib/`'s pandas code | Dev dependency; add to `dev` optional group — required for `mypy --strict lib` (already enforced by `scripts/qa.sh typecheck`) to type-check pandas-heavy new modules without `Any` noise |
| `pyshp` | 3.1.6 [VERIFIED: `pip index versions pyshp`] | Read `taxi_zones.shp` polygon vertices for the one-time centroid precompute (D-06) | Pure-Python, stdlib-only shapefile reader — no GEOS/C-extension dependency, the lightest possible way to get polygon vertices out of an ESRI shapefile |
| `pyproj` | 3.7.2 [VERIFIED: `pip index versions pyproj`] | Reproject shapefile coordinates from EPSG:2263 (feet) to EPSG:4326 (lat/lon degrees) for the centroid precompute (D-06) | **Required, not optional** — verified this session that `taxi_zones.shp`'s native coordinates are in US survey feet, not degrees (see Architecture Patterns below); `pyproj` is a coordinate-transform binding only (no polygon geometry ops), meaningfully lighter than `geopandas`/`shapely`+`fiona`, and is itself a dependency `geopandas` uses internally |

**Both `pyshp` and `pyproj` are precompute-script-only dependencies — they belong in the `dev` optional-dependency group (or a new small group, e.g. `geo`), NOT in the `ml` group that ships in any future component image.** The zone-centroid CSV they produce is a static, committed artifact; `lib/features.py`'s runtime haversine path only needs `pandas`/`numpy` to read that CSV and join it.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pyshp` + pure-Python centroid formula + `pyproj` | `geopandas`/`shapely` | Explicitly rejected in D-06 — heavier (GEOS/Fiona C-extension stack), not worth the setup time for a one-time precomputation inside the 10–15h budget |
| Area-weighted polygon centroid (shoelace formula) | Bounding-box midpoint (`(xmin+xmax)/2, (ymin+ymax)/2`) | Bbox midpoint is simpler but wrong for concave/multi-part zones — 23 of 263 taxi zones are multi-part polygons (verified this session); bbox midpoint can land outside the polygon or in the wrong borough entirely for these |
| `LGBMRegressor` sklearn API | `lgb.train()` core API with `lgb.Dataset` | sklearn API (`fit`/`predict`) is simpler to unit-test with plain DataFrames and mocks; core API is more idiomatic if custom callbacks/early-stopping-on-eval-set are needed later — either is a valid "boring" choice per REQ-D2 |

**Installation:**
```bash
# Populate pyproject.toml's `ml` group (already reserved empty by Phase 1's D-04)
uv add --extra ml "pandas>=2.3,<2.4" "numpy>=2.5,<2.6" pyarrow "pandera==0.32.1" "lightgbm==4.7.0" "mlflow==3.15.1"

# Dev-only: type stubs + one-time zone-centroid precompute tooling
uv add --extra dev pandas-stubs pyshp pyproj
```

**Version verification performed this session:** All six `ml`-group packages and both precompute-only packages confirmed to exist at the exact pinned version via `pip index versions <pkg>` against the live PyPI index (2026-08-20). No drift from `research/STACK.md`'s original pins.

## Package Legitimacy Audit

Ran `gsd-tools query package-legitimacy check --ecosystem pypi` against every package this phase introduces or reuses. All returned `SUS` — but inspecting the `reasons` array shows this seam's checker has no access to PyPI download-count telemetry in this environment (`unknown-downloads` fires on every package, including ones with billions of cumulative downloads), so `SUS` here reflects a data-availability gap in the checker, not a legitimacy signal. Cross-checked each against `pip index versions` (registry existence + version match) and, for the two new-to-this-phase packages, against their GitHub source repos.

| Package | Registry | Age (per checker) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pandas` | PyPI | n/a (checker misreports publish date as most-recent-release date, not project age) | unknown (checker gap) | none reported (checker gap — actual: github.com/pandas-dev/pandas) | SUS | Approved — already pinned in prior-phase `STACK.md`; among the most widely used PyPI packages in existence |
| `numpy` | PyPI | (same checker gap) | unknown | none reported (actual: github.com/numpy/numpy) | SUS | Approved — same as above |
| `pyarrow` | PyPI | (same checker gap) | unknown | github.com reported correctly (arrow.apache.org) | SUS | Approved |
| `pandera` | PyPI | (same checker gap) | unknown | github.com/pandera-dev/pandera reported | SUS | Approved — already pinned in `STACK.md`, matches Context7's high-reputation `unionai-oss/pandera` docs source |
| `lightgbm` | PyPI | (same checker gap) | unknown | none reported (actual: github.com/microsoft/LightGBM) | SUS | Approved — already pinned in `STACK.md` |
| `mlflow` | PyPI | (same checker gap) | unknown | none reported (actual: github.com/mlflow/mlflow) | SUS | Approved — already pinned in `STACK.md`, Context7 high-reputation source |
| `pandas-stubs` | PyPI | (same checker gap) | unknown | pandas.pydata.org reported | SUS | Approved |
| `pyshp` | PyPI | (same checker gap) | unknown | none reported (actual: github.com/GeospatialPython/pyshp, 15+ years old) | SUS | **Flagged — new to this phase.** Approved for use based on independent verification (established, MIT-licensed, pure-Python, no known CVEs found), but per protocol the planner should add a `checkpoint:human-verify` before the install task since it wasn't in the original `STACK.md` pin list |
| `pyproj` | PyPI | (same checker gap) | unknown | github.com/pyproj4/pyproj reported correctly | SUS | **Flagged — new to this phase.** Approved (official Python binding for PROJ, a dependency of `geopandas` itself, actively maintained), but per protocol the planner should add a `checkpoint:human-verify` before the install task since it wasn't in the original `STACK.md` pin list |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]` requiring a planner checkpoint:** `pyshp`, `pyproj` (both newly introduced this phase for the D-06 precompute script; not present in Phase 1's `STACK.md`).

## Architecture Patterns

### System Architecture Diagram — Zone Centroid Precompute (D-06)

```
TLC CloudFront distribution (d37ci6vzurychx.cloudfront.net)
    │
    ├─ /misc/taxi_zones.zip  (263 polygon shapes, EPSG:2263 — feet, NOT lat/lon)
    │       │
    │       ▼
    │  scripts/precompute_zone_centroids.py   (one-time, dev-only deps: pyshp + pyproj)
    │       │
    │       │ 1. pyshp: read each polygon's vertex rings + LocationID (dbf field "LocationID")
    │       │ 2. pure-Python area-weighted centroid formula per ring/part
    │       │    (23/263 zones are multi-part — combine parts by area-weighted average)
    │       │ 3. pyproj.Transformer(EPSG:2263 → EPSG:4326): feet centroid → (lon, lat) degrees
    │       ▼
    │  data/zone_centroids.csv   (zone_id, centroid_lat, centroid_lon — committed to repo, ~263 rows)
    │
    └─ /misc/taxi_zone_lookup.csv  (LocationID, Borough, Zone, service_zone — 265 rows, no coordinates;
                                     used only for human-readable Borough/Zone names if needed, not for
                                     the haversine join)

Runtime path (every ingest run, lib/features.py):
    trip DataFrame (PULocationID, DOLocationID)
        │  left-join on zone_id
        ▼
    zone_centroids.csv  (pandas.read_csv, no pyshp/pyproj needed at this point)
        │
        ▼
    vectorized numpy haversine(pu_lat, pu_lon, do_lat, do_lon) → trip_distance_km feature
```

### Recommended Project Structure

```
lib/
├── ingest.py       # chunked TLC Parquet read (pyarrow.parquet.ParquetFile.iter_batches)
├── schemas.py       # pandera DataFrameSchema(s) + Checks (D-09)
├── features.py       # vectorized haversine (reads data/zone_centroids.csv), dtype downcasting
├── train.py         # LightGBM fixed-config regression training (REQ-D2)
├── evaluate.py       # RMSE computation, champion-vs-candidate comparison logic
└── registry.py       # thin MLflow client wrapper (set_registered_model_alias, get_model_version_by_alias)
scripts/
└── precompute_zone_centroids.py   # one-time: shapefile → data/zone_centroids.csv (pyshp + pyproj, dev-only)
data/
└── zone_centroids.csv             # committed, ~263 rows — the D-06 static lookup
tests/lib/
├── test_ingest.py
├── test_schemas.py
├── test_features.py
├── test_train.py
├── test_evaluate.py
└── test_registry.py               # mocks MlflowClient, no real server (per CONTEXT.md phase boundary)
```

### Pattern 1: Chunked Parquet ingest (REQ-C4)

**What:** Use `pyarrow.parquet.ParquetFile(path).iter_batches(batch_size=N)` instead of `pandas.read_parquet(path)` (which loads the entire file into memory in one shot — `pandas.read_parquet` has no `chunksize` parameter, unlike `read_csv`).
**When to use:** `lib/ingest.py`'s month-read function, always — this is the concrete mechanism that satisfies REQ-C4's "never a single unbounded `read_parquet`" acceptance criterion.
**Verified detail:** the live 2019-01 Yellow file has `num_row_groups: 1` (confirmed via `pf.num_row_groups` this session) — meaning row-group-level chunking alone won't sub-divide this particular file; `iter_batches(batch_size=N)` still sub-divides within a row group at the Arrow batch level, so it remains the correct chunking primitive regardless of row-group count.

```python
# Source: verified live this session against yellow_tripdata_2019-01.parquet
import pyarrow.parquet as pq
import pandas as pd

def read_month_chunked(path: str, batch_size: int = 200_000) -> pd.DataFrame:
    pf = pq.ParquetFile(path)
    frames = [batch.to_pandas() for batch in pf.iter_batches(batch_size=batch_size)]
    return pd.concat(frames, ignore_index=True)
```

### Pattern 2: Zone centroid precompute (pure-Python, no shapely/geopandas)

**What:** Read shapefile vertices with `pyshp`, compute each polygon's area-weighted centroid with the standard shoelace-based formula (no external geometry library), reproject feet→degrees with `pyproj`.
**When to use:** Once, in `scripts/precompute_zone_centroids.py`, to produce the committed `data/zone_centroids.csv`.
**Verified end-to-end this session** — ran this exact code against the live-downloaded `taxi_zones.shp` for LocationID 1 (Newark Airport, single-part polygon) and got `lon=-74.174, lat=40.6918`, matching Newark Liberty Airport's real-world coordinates.

```python
# Source: executed and verified live this session (2026-08-20) against the
# actual TLC taxi_zones.shp (EPSG:2263 confirmed via its .prj file)
import shapefile          # pyshp
from pyproj import Transformer

_transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)

def _ring_centroid(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Shoelace-based area-weighted centroid of one polygon ring. Returns (cx, cy, signed_area)."""
    n = len(points)
    a = cx = cy = 0.0
    for i in range(n - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if a == 0:
        xs, ys = zip(*points)
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    return cx / (6 * a), cy / (6 * a), a

def zone_centroid_lonlat(points: list[tuple[float, float]], parts: list[int]) -> tuple[float, float]:
    """Handles multi-part zones (23 of 263) by area-weighting each ring's centroid."""
    ring_bounds = list(parts) + [len(points)]
    weighted_x = weighted_y = total_area = 0.0
    for start, end in zip(ring_bounds, ring_bounds[1:]):
        cx, cy, area = _ring_centroid(points[start:end])
        weight = abs(area)
        weighted_x += cx * weight
        weighted_y += cy * weight
        total_area += weight
    x_ft, y_ft = weighted_x / total_area, weighted_y / total_area
    lon, lat = _transformer.transform(x_ft, y_ft)
    return lon, lat
```

**Note on the CRS finding:** `taxi_zones.shp`'s `.prj` file (read directly this session) declares `PROJCS["NAD_1983_StatePlane_New_York_Long_Island_FIPS_3104_Feet", ...]` — this is EPSG:2263, coordinates in US survey feet, **not** WGS84 degrees. Any centroid computed directly from raw shapefile vertices without reprojection will be numerically wrong (values in the hundreds-of-thousands range, not -74/40-ish degrees). This is the load-bearing reason `pyproj` is a required dependency, not merely convenient.

### Pattern 3: pandera 0.32.1 schema with real Checks (REQ-C1 / D-09)

**What:** Column-level `Check`s for single-column rules, a DataFrameSchema-level "wide check" (or `@pa.dataframe_check` in the class-based `DataFrameModel` API) for the cross-column `dropoff >= pickup` rule.
**When to use:** `lib/schemas.py`, validated at the ingest boundary before any feature engineering.

```python
# Source: unionai-oss/pandera official docs (Context7), adapted to this project's columns.
# NOTE: exact column names/dtypes below are drawn from the live 2019-01 schema
# verified this session (see "TLC Data Source" below) — see Pitfall 6 before
# treating the row-level numeric Checks as "reject the whole month on any hit".
import pandas as pd
import pandera.pandas as pa

trip_schema = pa.DataFrameSchema(
    columns={
        "tpep_pickup_datetime": pa.Column("datetime64[ns]", nullable=False),
        "tpep_dropoff_datetime": pa.Column("datetime64[ns]", nullable=False),
        "PULocationID": pa.Column(int, pa.Check.in_range(1, 263), nullable=False),
        "DOLocationID": pa.Column(int, pa.Check.in_range(1, 263), nullable=False),
        "trip_distance": pa.Column(float, pa.Check.gt(0), nullable=False),
        "passenger_count": pa.Column(float, pa.Check.in_range(1, 6), nullable=True),
    },
    checks=[
        # wide (dataframe-level) check: dropoff must not precede pickup
        pa.Check(lambda df: df["tpep_dropoff_datetime"] >= df["tpep_pickup_datetime"]),
    ],
    strict=False,  # allow extra columns (congestion_surcharge, airport_fee, etc.) to pass through unvalidated
)
```

### Pattern 4: LightGBM 4.7.0 minimal fixed config (REQ-D2)

**What:** `lgb.LGBMRegressor` (sklearn API) with a single fixed, documented hyperparameter set — no `GridSearchCV`/Optuna/Katib anywhere in the repo.
**When to use:** `lib/train.py`.

```python
# Source: lightgbm-org/lightgbm official docs (Context7) — Parameters.rst + Python-Intro.rst
import lightgbm as lgb
import pandas as pd

CATEGORICAL_FEATURES = ["PULocationID", "DOLocationID", "VendorID"]

def train_model(X: pd.DataFrame, y: pd.Series) -> lgb.LGBMRegressor:
    for col in CATEGORICAL_FEATURES:
        X[col] = X[col].astype("category")
    model = lgb.LGBMRegressor(
        objective="regression",   # default; explicit for readability — optimizes L2/MSE
        metric="rmse",
        num_leaves=31,             # LightGBM's own documented default
        learning_rate=0.05,
        n_estimators=300,
        random_state=42,
    )
    model.fit(X, y, categorical_feature=CATEGORICAL_FEATURES)
    return model
```

**Verified pitfall (Context7-sourced):** "When using pandas dataframes, LightGBM automatically aligns categories observed during training, while unseen categories at prediction time are treated as missing." — the `category` dtype's category set must be fixed/persisted consistently between train and predict (e.g., via `CategoricalDtype` with an explicit category list derived from the full zone-ID range, not just what's present in the training split), or a zone ID seen only in the test/prediction window silently becomes a missing value instead of erroring.

### Pattern 5: MLflow registry client wrapper, mockable (REQ-D3)

**What:** A thin `lib/registry.py` wrapping `MlflowClient.set_registered_model_alias` / `get_model_version_by_alias`, unit-tested entirely against a mocked client (no real MLflow server exists until Phase 3, per the phase boundary in `02-CONTEXT.md`).
**When to use:** `lib/registry.py`, called by `evaluate.py`'s champion-comparison logic.

```python
# Source: mlflow/mlflow official docs (Context7, high-reputation source)
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

class ModelRegistry:
    def __init__(self, client: MlflowClient, model_name: str) -> None:
        self._client = client
        self._model_name = model_name

    def get_champion_rmse(self) -> float | None:
        """Returns None if no champion is registered yet (first-ever run)."""
        try:
            version = self._client.get_model_version_by_alias(self._model_name, "champion")
        except MlflowException:
            return None
        return float(version.tags.get("rmse", "nan"))

    def promote_to_champion(self, version: str) -> None:
        self._client.set_registered_model_alias(self._model_name, "champion", version)
```

```python
# tests/lib/test_registry.py — mockable without any real server (per Phase 2 boundary)
from unittest.mock import MagicMock
from mlflow.exceptions import MlflowException
from lib.registry import ModelRegistry

def test_get_champion_rmse_returns_none_when_no_champion() -> None:
    client = MagicMock()
    client.get_model_version_by_alias.side_effect = MlflowException("not found")
    registry = ModelRegistry(client, "trip-duration")
    assert registry.get_champion_rmse() is None

def test_promote_to_champion_calls_set_alias() -> None:
    client = MagicMock()
    registry = ModelRegistry(client, "trip-duration")
    registry.promote_to_champion("3")
    client.set_registered_model_alias.assert_called_once_with("trip-duration", "champion", "3")
```

### Anti-Patterns to Avoid

- **Computing the zone centroid from raw shapefile vertices without reprojecting:** produces numerically-plausible-looking but geographically wrong coordinates (values like `933100.9, 192536.1` — feet, not degrees). Verified this session; always run through `pyproj.Transformer.from_crs("EPSG:2263", "EPSG:4326")` first.
- **Bounding-box-midpoint "centroid":** wrong for the 23/263 multi-part (disjoint) zones — the midpoint can fall in the water between two islands/parts, not inside either.
- **Using the widely-cited `s3://nyc-tlc/misc/taxi_zones.zip` / `s3.amazonaws.com/nyc-tlc/misc/taxi_zones.zip` URL:** returned **HTTP 403 Forbidden** when directly tested this session — this URL, still referenced by many tutorials/blog posts, is dead. Use `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip` (verified `HTTP 200`, same CloudFront distribution as the trip-data Parquet files and the zone lookup CSV).
- **Treating `pandera.validate()`'s default per-row-Check semantics as automatically compatible with "reject whole month, don't silently filter":** see Pitfall 6 — real data has a baseline rate of numeric-quality violations every month.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reading a shapefile's polygon vertices | A custom ESRI shapefile binary-format parser | `pyshp` (`shapefile.Reader`) | Pure-Python, handles the `.shp`/`.shx`/`.dbf` binary format correctly (part boundaries, field types) — the format has enough edge cases (multi-part records, `.dbf` field encodings) that hand-parsing risks silent corruption |
| Coordinate reprojection (feet → degrees) | Manual Lambert Conformal Conic projection math | `pyproj.Transformer` | The projection math (verified this session: `Lambert_Conformal_Conic`, two standard parallels, a specific false easting/northing) is exactly the kind of "looks simple, has a dozen edge cases" problem `pyproj`/PROJ exists to solve correctly |
| Schema validation with informative failure messages | Hand-rolled `if`/`assert` chains over DataFrame columns | `pandera` | pandera's `SchemaError`/`SchemaErrors` (with `lazy=True`) gives structured, column-and-row-addressable failure reports for free — REQ-C1's "logged reason" acceptance criterion is nearly free with pandera, expensive to hand-roll well |
| Model registry versioning/aliasing | A custom "champion.json" file tracking the best model path | MLflow Model Registry (`set_registered_model_alias`) | MLflow's registry is exactly the durable, queryable "what's the champion right now" store `evaluate.py` needs — hand-rolling loses atomicity/history and duplicates what REQ-D3 already asks for |
| Categorical encoding for `PULocationID`/`DOLocationID` | Manual one-hot encoding (263+ dummy columns) | LightGBM's native pandas `category` dtype support | LightGBM's Fisher-method categorical splits are documented as "often outperforming one-hot encoding" and avoid an enormous, memory-costly one-hot matrix for a 263-value categorical |

**Key insight:** Every "don't hand-roll" item above is a case where the naive DIY version looks straightforward until you hit a specific, well-documented edge case (multi-part shapefile records, Lambert Conformal Conic math, structured schema-failure reporting, model version history, high-cardinality categoricals) — and a small, well-scoped library exists specifically because those edge cases are common and non-obvious.

## Common Pitfalls

### Pitfall 1: The classic `s3://nyc-tlc/misc/taxi_zones.zip` URL is dead

**What goes wrong:** Following any of the many tutorials/blog posts that reference `https://s3.amazonaws.com/nyc-tlc/misc/taxi_zones.zip` results in `HTTP 403 Forbidden`.
**Why it happens:** TLC migrated its `misc/` assets (zone lookup CSV, shapefile) onto the same CloudFront distribution used for trip-data Parquet files; the old direct-S3 URL was left to rot.
**How to avoid:** Use `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip` — verified `HTTP 200`, `content-length: 1022574` (~1MB), this session.
**Warning signs:** `curl`/`requests` returning 403 on the download script's first run — check the URL against the CloudFront pattern before assuming a network/auth problem.
**Phase to address:** Phase 2, zone-centroid precompute script.

---

### Pitfall 2: taxi_zones.shp coordinates are in feet (EPSG:2263), not degrees

**What goes wrong:** Reading `.shp` vertices with `pyshp` and treating them as `(lon, lat)` produces coordinates like `(933100.9, 192536.1)` — nonsensical as WGS84 degrees, but not obviously wrong at a glance if you don't sanity-check the magnitude.
**Why it happens:** The shapefile's `.prj` sidecar file (verified this session, read directly) declares `NAD_1983_StatePlane_New_York_Long_Island_FIPS_3104_Feet` — a state-plane projected CRS, not geographic WGS84.
**How to avoid:** Reproject with `pyproj.Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)` before treating any shapefile coordinate as lat/lon.
**Warning signs:** Haversine distances computed from the resulting centroids come out absurdly large (thousands of km) or the `arcsin`/`sqrt` in the haversine formula errors on an out-of-domain argument — either is a strong signal the "lat/lon" values are actually still in feet.
**Phase to address:** Phase 2, zone-centroid precompute script — verify the first computed centroid against a known real-world coordinate (e.g. Newark Airport zone should land near `-74.17, 40.69`) before trusting the full batch.

---

### Pitfall 3: 263 shapefile zones vs. 265 lookup-CSV LocationIDs — D-09's "1–263" range excludes two real, valid LocationID values

**What goes wrong:** `taxi_zone_lookup.csv` (verified this session, downloaded and read directly) has 265 rows; LocationID 264 = `Unknown`/`N/A`/`N/A` and LocationID 265 = `N/A`/`Outside of NYC`/`N/A`. The shapefile has exactly 263 polygon shapes — 264 and 265 have no geometry (no centroid is computable for them). D-09's locked Check range is `in_range(1, 263)`, which is *correct* in the sense that only 1–263 have real geographic zones and therefore only those can get a haversine distance — but it means any real trip with `PULocationID`/`DOLocationID` of 264 or 265 (verified present in the live 2019-01 sample: `PULocationID`/`DOLocationID` max observed was `265`) will trigger the Check and, per D-09, potentially reject the whole month.
**Why it happens:** TLC's zone lookup table includes two placeholder "unknown/outside NYC" pseudo-zones that never had a geographic boundary, alongside 263 real zones — a common trap for anyone assuming `zone lookup row count == valid zone count`.
**How to avoid:** This is very likely the *intended* behavior of D-09's check (rows with an unmappable zone genuinely can't get a distance feature), but the planner should decide explicitly whether these rows are dropped-and-logged before schema validation (treating 264/265 as expected, low-rate noise) or whether hitting them should count as "malformed month" (see Pitfall 6 for the same tension at larger scale).
**Warning signs:** A "malformed month" rejection on an otherwise-normal month, traceable to a small number of 264/265 rows rather than a real schema drift.
**Phase to address:** Phase 2, `lib/schemas.py` design — document the decision either way in the module or README.

---

### Pitfall 4: 23 of 263 taxi zones are multi-part polygons

**What goes wrong:** A "compute centroid" implementation that assumes one ring of vertices per zone (verified this session: `pyshp`'s `shape.parts` has more than one entry for 23 zone records) will average vertices across disjoint physical regions (e.g. islands), producing a centroid in open water or the wrong borough.
**Why it happens:** NYC taxi zones include some genuinely disjoint areas (e.g. zones with detached small islands or non-contiguous administrative boundaries).
**How to avoid:** Split each shape record on its `.parts` index boundaries, compute each ring's own area-weighted centroid, then combine via an area-weighted average across parts (see Pattern 2's `zone_centroid_lonlat` above).
**Warning signs:** A computed centroid for a coastal/island-adjacent zone lands outside the zone's polygon boundary entirely (visually implausible on a quick spot-check plot).
**Phase to address:** Phase 2, zone-centroid precompute script.

---

### Pitfall 5: `scripts/qa.sh` only passes `--extra dev` — new `lib/` modules importing pandas will fail `qa.sh test`/`qa.sh typecheck` until it's updated

**What goes wrong:** [VERIFIED: `scripts/qa.sh`, read this session] `UV_RUN=(uv run --extra dev)` (or `--frozen --extra dev` under CI) is the only extra passed to every `uv run` invocation in the script. `pyproject.toml`'s `ml` optional-dependency group (which this phase populates with pandas/numpy/pyarrow/pandera/lightgbm/mlflow) is never included. The first `lib/ingest.py` or `lib/schemas.py` module that does `import pandas` will fail at collection time when `scripts/qa.sh test` or `scripts/qa.sh typecheck` runs, because those packages aren't installed into the `--extra dev`-only sync.
**Why it happens:** `scripts/qa.sh` was written in Phase 1, before the `ml` group had any members — the script's `--extra dev` hardcoding was correct then and is now stale relative to Phase 2's scope.
**How to avoid:** Update `scripts/qa.sh`'s `UV_RUN` array to include both extras (`uv run --extra dev --extra ml`, and the CI/`--frozen` variant identically) as one of this phase's first tasks — before writing the first `pandas`-importing `lib/` module, not after discovering the failure.
**Warning signs:** `ModuleNotFoundError: No module named 'pandas'` from `scripts/qa.sh test`/`typecheck`, even though `uv add --extra ml pandas` succeeded and `uv.lock` shows it resolved.
**Phase to address:** Phase 2, first task (dependency/tooling setup), before any pandas-importing module is written.

---

### Pitfall 6: pandera's default `validate()` fails on *any* violating row — real TLC data has a baseline rate of numeric-quality violations every month, which conflicts with a literal reading of "malformed month fails loudly"

**What goes wrong:** [VERIFIED: live sample of 200,000 rows from the actual 2019-01 Yellow file, read this session] `trip_distance <= 0` occurred in **1,954/200,000 rows (~0.98%)**; `(dropoff - pickup).total_seconds() <= 0` occurred in **159/200,000 rows (~0.08%)**; `passenger_count == 0` occurred in **2,518/200,000 rows (~1.26%)**. This is not corrupted-file noise — it's the normal, baseline data-quality profile of every month in this dataset (meter errors, canceled/void trips still logged, GPS glitches). D-09's row-level `Check`s (`trip_distance > 0`, computed duration `> 0`, `passenger_count` bound), read literally under pandera's default fail-on-any-violating-row `validate()` semantics, would cause **every one of the 12 months to be rejected as "malformed"** — which almost certainly isn't the intended behavior (the acceptance criterion's example is "a malformed/schema-drifted month", i.e. genuinely bad data like a renamed/missing column or a corrupted file, not routine per-row noise present in every real month).
**Why it happens:** D-09's bullet list mixes two different kinds of check under one "fails loudly" umbrella: structural/schema-level checks (column presence, dtype, non-null on key columns — these genuinely should never fail on a well-formed month and are the right thing to fail loudly on) and row-level numeric-quality checks (distance/duration positivity, passenger_count bound — these fail at a small but nonzero rate on *every* real month).
**How to avoid — recommend to the planner as an explicit design decision, not silently resolved by research:**
  - **Option A (recommended):** Pre-filter/drop rows failing the row-level numeric checks *before* pandera validation, logging the count and rate dropped per month (e.g. "dropped 1,954/200,000 rows for trip_distance<=0"); pandera then validates only structural/non-null/range checks against the cleaned frame, which should legitimately pass every real month and only fail loudly on genuine schema drift. This satisfies "not silently filtered row-by-row" (the drop is logged, not silent) while making "fails loudly" meaningful (a structural violation, not routine noise, triggers the loud failure).
  - **Option B:** Keep D-09's checks exactly as row-level pandera `Check`s and accept that every month's ingest will hard-fail — but this needs to be a deliberate, documented choice (e.g. paired with `lazy=True` and a threshold on `exc.failure_cases` row count vs. a strict zero-tolerance), not a default that silently makes REQ-C1's "malformed month" scenario indistinguishable from "totally normal month."
**Warning signs:** The very first real ingest run of a normal month exits non-zero with a pandera `SchemaError` — if this happens on *every* month including ones with no reason to suspect schema drift, it's this pitfall, not a real data problem.
**Phase to address:** Phase 2, `lib/schemas.py` design — this must be resolved before the first `lib/ingest.py`+`lib/schemas.py` integration test is written, since it changes the module boundary between "ingest reads + cleans" and "schemas validates."

---

### Pitfall 7: `congestion_surcharge` and `airport_fee` are not populated for early-2019 data — schema must tolerate nulls on non-core columns

**What goes wrong:** [VERIFIED: live download and `pyarrow.parquet.ParquetFile.schema_arrow` read of `yellow_tripdata_2019-01.parquet` this session] `congestion_surcharge` is present as a `double` column but **100% NaN** in the January 2019 file (TLC introduced the congestion surcharge in February 2019 — the column exists in the unified schema but is backfilled null for pre-introduction months) [CITED: widely documented TLC data-dictionary history, cross-checked with this session's direct observation]. `airport_fee` is present with pyarrow dtype `null` (an all-null column) in the same file — TLC added this fee to the schema well after 2019 and backfills it as fully null for older files.
**Why it happens:** TLC republishes historical Parquet files against a single unified/current column schema, backfilling `NaN`/`null` for concepts that didn't exist yet in that month — this is different from genuine schema drift (a renamed or missing column) and should not be treated as a validation failure.
**How to avoid:** Don't add non-null `Check`s on `congestion_surcharge`/`airport_fee`/any TLC-added-later fee column; either omit them from the pandera schema entirely (pandera's `strict=False` lets extra/unvalidated columns pass through untouched, as used in Pattern 3 above) or explicitly mark them `nullable=True` if they need to reach `lib/features.py`.
**Warning signs:** A pandera schema with `nullable=False` on `congestion_surcharge` rejecting every month before February 2019 (i.e., half the 12-month window) on a column D-09 never actually asked to be checked.
**Phase to address:** Phase 2, `lib/schemas.py` — keep the schema scoped exactly to D-09's five bullet points; don't extend non-null coverage to columns D-09 didn't name.

---

### Pitfall 8: `passenger_count` and `RatecodeID` are stored as `float64`, not `int` — naive downcasting to a small int type will fail on NaN

**What goes wrong:** [VERIFIED: live schema read this session] `passenger_count` and `RatecodeID` are `double` (float64) in the Parquet schema, not integer — meaning they can legitimately hold `NaN`. A naive `pandas.to_numeric(df["passenger_count"], downcast="integer")` will raise/coerce incorrectly if any NaN is present (verified 0 nulls in the Jan-2019 sample specifically for these two columns, but this can't be assumed true for every month without checking).
**Why it happens:** TLC's own upstream systems store these as nullable numeric fields; a DataFrame reader that assumes "count-like fields are always int" will be surprised.
**How to avoid:** Downcast `passenger_count`/`RatecodeID` via `pandas.to_numeric(..., downcast="float")` (→ float32, which tolerates NaN) rather than an int downcast, unless the ingest/schema step has already asserted zero nulls for that specific month and explicitly casts to pandas' nullable `Int8`/`Int16` dtype (which does support NaN, unlike numpy's native int types).
**Warning signs:** `ValueError: Cannot convert non-finite values (NA or inf) to integer` during the dtype-downcasting step of `lib/features.py`.
**Phase to address:** Phase 2, `lib/features.py`'s dtype-downcasting implementation (REQ-C3).

---

### Pitfall 9: some rows' pickup timestamps fall well outside the file's nominal month

**What goes wrong:** [VERIFIED: live sample from `yellow_tripdata_2019-01.parquet` this session] A sample of 200,000 rows from the "January 2019" file included pickup timestamps in `2018-12`, `2018-11`, and even `2003-01`/`2009-01`/`2008-12` — i.e., the file's name/partition does not guarantee every row's `tpep_pickup_datetime` actually falls in that calendar month.
**Why it happens:** TLC's monthly files are partitioned by when the trip record was *reported/ingested* into their system, not strictly by the trip's own pickup timestamp — a small number of late-arriving or corrected records land in a different month's file than their timestamp suggests.
**How to avoid:** Don't assume `month_range()`'s month string can be used to further filter/validate rows by pickup timestamp without an explicit decision — if the chronological train/test split (D-08) is computed from `tpep_pickup_datetime` directly (recommended, since that's the actual event time), these out-of-range rows will naturally sort into whichever split their real timestamp falls in, which is likely fine; if the split is instead computed from "which file the row came from," these rows introduce quiet leakage/mislabeling.
**Warning signs:** A chronological split boundary that looks correct by file/month but has a handful of rows with timestamps from years earlier bleeding into the "training window."
**Phase to address:** Phase 2, `lib/train.py`/wherever the chronological split (D-08) is implemented — split on `tpep_pickup_datetime` value, not on which month's file the row was read from.

---

### Pitfall 10: `pytest`'s `--cov-fail-under=100` applies to every new `lib/` module, including `registry.py`'s mocked-client branches

**What goes wrong:** [VERIFIED: `pyproject.toml`, read this session — `addopts = "--cov=lib --cov-report=term-missing --cov-fail-under=100"`, `branch = true`] Any new `lib/` module (including error-handling branches like `registry.py`'s "no champion registered yet" path) must reach 100% branch coverage or the entire `pytest` run fails, not just that module.
**Why it happens:** This is a Phase 1 CI gate (`REQ-A3`) that now applies retroactively to every module this phase adds — it's easy to write a happy-path test for `ModelRegistry.get_champion_rmse()` and forget the `MlflowException` branch, which silently drops coverage below 100%.
**How to avoid:** For each `lib/` module, explicitly enumerate branches (including exception paths) and write a test per branch before considering the module done — the mocked-client test pattern in Pattern 5 above (`side_effect = MlflowException(...)`) is the template for `registry.py` specifically.
**Warning signs:** `scripts/qa.sh test` failing with a coverage-percentage error even though all individual test functions pass.
**Phase to address:** Phase 2, every `lib/` module — treat as a per-module Definition of Done, not a final phase-end check.

## Code Examples

### Vectorized Haversine (REQ-C2)

```python
# Source: cross-checked against multiple official-adjacent vectorization write-ups
# (tjansson.dk, pythontutorials.net) this session — standard, widely-used formula.
import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0

def haversine_km(
    lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series
) -> pd.Series:
    lat1_r, lon1_r, lat2_r, lon2_r = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2.0) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))
```

### Chunked Parquet Reads (REQ-C4)

See Pattern 1 above.

### dtype Downcasting (REQ-C3)

```python
# Source: cross-checked web sources this session (pandas.to_numeric official reference +
# community downcasting write-ups); NaN-safety detail verified against this session's
# live schema read (Pitfall 8).
import pandas as pd

def downcast_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("trip_distance", "trip_duration_s"):
        df[col] = pd.to_numeric(df[col], downcast="float")   # float64 -> float32
    for col in ("PULocationID", "DOLocationID", "VendorID", "payment_type"):
        df[col] = df[col].astype("category")                  # low-cardinality -> category
    return df
```

### pandera Schema / LightGBM Config / MLflow Wrapper

See Patterns 3, 4, 5 above.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Row-wise `.apply()` haversine distance | Vectorized numpy haversine | N/A (always been the correct approach for pandas at this scale) | ~18x speedup at moderate row counts per cross-checked benchmarks; widens further with N — directly the evidence REQ-C5's benchmark table should show |
| MLflow Model Registry stage transitions (`transition_model_version_stage`, "Staging"/"Production" strings) | Alias-based promotion (`set_registered_model_alias`, `@champion`/`@candidate`) | MLflow 3.x (per `research/STACK.md`, already accounted for) | Confirmed again this session via Context7's official MLflow docs — `get_model_version_by_alias` is the current lookup API, `transition_model_version_stage` is deprecated |
| Raw lat/lon columns in NYC TLC trip records | `PULocationID`/`DOLocationID` zone IDs only | July 2016 (per `research/STACK.md` and `02-CONTEXT.md`, D-06's premise) | Confirmed again this session — the live 2019-01 schema has zero lat/lon columns; distance must be derived from the zone-centroid join |

**Deprecated/outdated:**
- `s3://nyc-tlc/misc/taxi_zones.zip` as a working download URL: dead (403), confirmed this session — many still-circulating tutorials reference it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `congestion_surcharge` is introduced specifically in **February 2019** (not some other month) | Pitfall 7 | Low — this session directly verified 100% NaN for January 2019, which is sufficient on its own to justify `nullable=True`/schema exclusion regardless of the exact introduction month; the "February 2019" date itself is [CITED] community knowledge, not independently re-verified against a second TLC-authoritative source this session |
| A2 | `Airport_fee`'s introduction date and exact months it's null for | Pitfall 7 | Low — this session directly verified it's fully `null`-typed for the entire January 2019 file (the strongest possible confirmation for that one month); behavior in other months of the 12-month window (2019-2020) not individually re-verified, but the same "exclude/nullable" mitigation applies regardless of exact per-month behavior |
| A3 | 264/265 (`Unknown`/`Outside of NYC`) LocationIDs occur at a genuinely low rate across the full 12-month window, not just as isolated noise in one sample | Pitfall 3 | Low-Medium — only the January 2019 200k-row sample was inspected this session (max LocationID observed = 265, confirming presence, but exact rate across all 12 months wasn't computed); if the rate is higher in some month, Pitfall 6's "loud rejection on real data" tension is proportionally worse |
| A4 | The ~1%/~0.08% row-level violation rates observed in the January-2019 200k-row sample (Pitfall 6) are representative of the other 11 months in the window | Pitfall 6 | Medium — this is the load-bearing number behind the Pitfall 6 recommendation; if other months (especially the post-COVID low-volume months) have a substantially different violation profile, the planner's chosen mitigation (pre-filter-and-log vs. hard-fail) should be re-validated against at least one more sampled month before implementation, not assumed from January 2019 alone |

## Open Questions

1. **How should D-09's row-level numeric Checks (distance/duration positivity, passenger_count bound) interact with pandera's default "fail on any violating row" semantics, given real data has a baseline ~1% violation rate every month?**
   - What we know: Verified this session — real 2019-01 data has non-trivial per-row violation rates on exactly the numeric checks D-09 names; a literal implementation will reject every month.
   - What's unclear: Whether the CONTEXT.md author intended "malformed month" to include this routine noise, or only genuine structural drift.
   - Recommendation: Planner should make this an explicit task-level decision (see Pitfall 6, Option A vs. B) rather than let it default silently — Option A (pre-filter-and-log, then hard-fail only on structural violations) best matches both D-09's literal checks and REQ-C1's "not silently filtered row-by-row" (the filter is logged) and "fails loudly on malformed month" (structural violations still hard-fail) framing simultaneously.

2. **Should `PULocationID`/`DOLocationID` values of 264/265 (Unknown/Outside NYC) be dropped-and-logged as expected low-rate noise, or does hitting them count toward "malformed month"?**
   - What we know: They're valid, TLC-documented LocationID values that appear in real trip data but have no shapefile geometry (no centroid possible).
   - What's unclear: D-09 locks the Check range at `1–263`, which structurally excludes them — but doesn't say whether the resulting Check violations should be pre-filtered or treated as month-rejecting.
   - Recommendation: Handle identically to Open Question 1's Option A — pre-filter rows with unmappable zone IDs, log the count, and don't let this rare, expected condition trigger a full-month rejection.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Internet access to `d37ci6vzurychx.cloudfront.net` | D-07 (12-month TLC download), D-06 (zone shapefile/lookup download) | ✓ (verified live `HTTP 200` this session on trip-data, zone lookup CSV, and zone shapefile URLs) | — | — |
| Disk space for 12-month Parquet cache (gitignored) | D-07 | ✓ | 314GB free (verified `df -h` this session); each monthly file observed ~100-150MB, 12 months well under 2GB total | — |
| RAM for pandas/LightGBM work on this machine | REQ-C3/C4 (proving downcasting/chunking matters), REQ-D2 (training) | ✓ | 15GB total, ~9.7GB available at time of check (verified `free -h` this session) — matches `research/STACK.md`'s 16GB assumption | — |
| `uv` package manager | All dependency installation | ✓ | 0.11.0 (verified `uv --version`) | — |
| Python 3.12 (project-pinned) | `pyproject.toml` `requires-python` | ✓ (via `uv`-managed venv at `path/to/venv`, not system Python which is 3.14.4) | — | `uv python install 3.12` if the pinned venv needs rebuilding |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** none identified — all required external resources verified reachable this session.

## Security Domain

`security_enforcement` is enabled (`.planning/config.json`, `security_asvs_level: 1`, `security_block_on: "high"`). This phase is entirely offline `lib/` code with no network-exposed service, no authentication surface, and no user-facing input — the applicable ASVS surface is narrow.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | This phase has no auth surface — `lib/registry.py` talks to a mocked MLflow client only; real MLflow credentials/auth are a Phase 3 concern |
| V3 Session Management | No | No sessions in this phase |
| V4 Access Control | No | No multi-user/access-control surface in this phase |
| V5 Input Validation | Yes | `pandera` schema validation at the ingest boundary (REQ-C1/D-09) is exactly ASVS V5's "validate all untrusted input" control, applied to externally-sourced TLC data |
| V6 Cryptography | No (this phase) | No secrets/credentials handled by `lib/` in Phase 2 — MLflow client is mocked; real tracking-server auth (API keys, `MLFLOW_TRACKING_TOKEN`) is a Phase 3 concern when a real server exists |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Malformed/adversarially-crafted Parquet input to `lib/ingest.py` | Tampering | pandera schema validation immediately after read (REQ-C1) — reject non-conforming structure before any downstream code trusts the DataFrame's shape/dtypes |
| Zip-slip / path traversal when extracting `taxi_zones.zip` in the precompute script | Tampering | The download source is a trusted, pinned TLC/CloudFront URL under executor control (not user-uploaded), so risk is low, but the extraction code should still validate each zip entry's resolved path stays within the target extraction directory before writing, as defense-in-depth |
| Arbitrary code execution via untrusted `pickle`/`joblib` deserialization of a LightGBM model artifact | Tampering / Elevation of Privilege | Prefer LightGBM's native `Booster.save_model()`/`Booster(model_file=...)` text-format serialization over raw `pickle.dump`/`pickle.load` for any model artifact that could conceivably cross a trust boundary later (e.g. once MLflow-registered artifacts are pulled by a different service in Phase 3); if `joblib`/`pickle` is used for the sklearn-API `LGBMRegressor` object specifically (common practice, since the sklearn wrapper doesn't expose the same text-format save method as the core `Booster`), scope loading strictly to artifacts this pipeline itself produced, never to an arbitrary/user-supplied path — [ASSUMED: general secure-deserialization practice, not TLC/LightGBM-specific] |

## Sources

### Primary (HIGH confidence — verified live this session)

- `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2019-01.parquet` — downloaded and inspected directly (schema via `pyarrow.parquet.ParquetFile.schema_arrow`, row counts, null patterns, out-of-range dates, numeric violation rates)
- `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv` — downloaded and inspected directly (265 rows, LocationID 1-265, columns confirmed)
- `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip` — downloaded and inspected directly (263 shapes, `.prj` CRS read directly, `.dbf` fields read directly, multi-part-shape count computed directly)
- `s3.amazonaws.com/nyc-tlc/misc/taxi_zones.zip` — tested directly, confirmed `HTTP 403 Forbidden` (dead URL)
- End-to-end centroid computation (pyshp + shoelace formula + pyproj) executed live this session against the real shapefile, cross-checked against Newark Airport's known real-world coordinates
- `pip index versions <pkg>` — live PyPI registry check for `pandas`, `numpy`, `pyarrow`, `pandera`, `lightgbm`, `mlflow`, `boto3`, `pyshp`, `pyproj`, `pandas-stubs`
- `scripts/qa.sh`, `pyproject.toml`, `lib/months.py`, `tests/lib/test_months.py`, `CLAUDE.MD` — read directly this session (repo state)

### Primary (HIGH confidence — official docs via Context7)

- `unionai-oss/pandera` (Context7 High reputation, 1165 snippets) — DataFrameSchema, Column, Check, `@pa.dataframe_check`, wide checks
- `lightgbm-org/lightgbm` (Context7 Medium-High reputation, 736 snippets) — sklearn API, categorical feature handling, Parameters.rst
- `mlflow/mlflow` (Context7 High reputation, 8164 snippets) — `set_registered_model_alias`, `get_model_version_by_alias`, testing patterns

### Secondary (MEDIUM confidence — WebSearch cross-checked)

- `arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html` — `iter_batches` chunked-read API, cross-checked via WebSearch against the official Apache Arrow doc URL
- `www.tjansson.dk`, `pythontutorials.net` — vectorized haversine formula (standard, cross-checked against multiple independent write-ups converging on the same formula)
- `learn.microsoft.com/en-us/azure/open-datasets/dataset-taxi-yellow` — historical (pre-2016) schema reference confirming `puLocationId`/`doLocationId` naming lineage; superseded by this session's direct 2019-01 schema read for current-era column names
- `epsg.io/2263` — EPSG:2263 definition, cross-checked against the directly-read `.prj` file content (exact match)

### Tertiary (LOW confidence — WebSearch only, community sources)

- Congestion-surcharge February-2019 introduction date (Assumption A1) — community-documented, not independently re-verified against a second authoritative TLC source this session

## Metadata

**Confidence breakdown:**
- TLC data source, schema, CRS, zone-count findings: HIGH — independently verified via live download/inspection this session, not just cited
- pandera/LightGBM/MLflow API syntax: MEDIUM-HIGH — official docs via Context7 (high-reputation sources), not independently executed against a live pandera/LightGBM/MLflow install this session
- Vectorization/downcast technique: MEDIUM — well-established, cross-checked patterns, standard practice
- Real-data row-level violation rates (Pitfall 6): HIGH for January 2019 specifically (directly measured), MEDIUM for generalizing across all 12 months (see Assumption A4)

**Research date:** 2026-08-20
**Valid until:** ~30 days for library API patterns (pandera/LightGBM/MLflow are stable, slow-moving); TLC data source URLs/schema should be considered stable for the life of this project (TLC's CloudFront migration was a one-time historical event, not an ongoing churn pattern) but worth a quick re-check (`curl -I`) immediately before the actual 12-month download script runs, given the S3-URL deprecation precedent found this session

---
*Phase 2 research for: nyc-trip-duration-kfp — Data & Model Engineering (lib/)*
*Researched: 2026-08-20*
