# Phase 2: Data & Model Engineering (lib/) - Pattern Map

**Mapped:** 2026-08-20
**Files analyzed:** 13 (6 `lib/` modules, 6 `tests/lib/` modules, 1 precompute script; plus 2 supporting config/data files)
**Analogs found:** 2 exact-structural / 11 no-codebase-analog (greenfield phase — RESEARCH.md code examples are the primary source for those)

## Context

This is effectively a greenfield phase: the codebase currently has exactly **one** `lib/` module (`lib/months.py`) and **one** corresponding test (`tests/lib/test_months.py`). No pandas/numpy/pandera/LightGBM/MLflow code exists anywhere in the repo yet. There is no controller/service/component layer to draw CRUD/request-response patterns from (`components/` is Phase-3-only and is pandas-import-forbidden by `scripts/check_component_boundary.sh`).

Because of this, `lib/months.py` + `tests/lib/test_months.py` are the **only real codebase analogs**, and they only supply *module-level* conventions (docstrings, error-raising style, pure-function shape, exact-value test style) — not domain logic. For domain logic (pandera schemas, vectorized haversine, LightGBM config, MLflow wrapper), the planner should use RESEARCH.md's "Code Examples"/"Architecture Patterns" sections directly, which were independently verified live this session against real TLC data and official docs. This PATTERNS.md treats those RESEARCH.md snippets as the canonical source-of-truth pattern where no codebase analog exists, and cites exact section names/line anchors within `02-RESEARCH.md` for traceability.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `lib/ingest.py` | service (I/O) | file-I/O, batch | `lib/months.py` (module shape only) | role-match (structural only) |
| `lib/schemas.py` | model (validation) | transform | none in codebase | no-analog — use RESEARCH.md Pattern 3 |
| `lib/features.py` | transform/utility | transform, file-I/O (CSV join) | none in codebase | no-analog — use RESEARCH.md Pattern 2 + Vectorized Haversine + dtype Downcasting |
| `lib/train.py` | service (ML) | batch | none in codebase | no-analog — use RESEARCH.md Pattern 4 |
| `lib/evaluate.py` | service (ML) | transform | none in codebase | no-analog — use RESEARCH.md (Architectural Responsibility Map row) |
| `lib/registry.py` | service (external client wrapper) | request-response (mocked) | none in codebase | no-analog — use RESEARCH.md Pattern 5 |
| `scripts/precompute_zone_centroids.py` | utility (one-time script) | batch, file-I/O | `scripts/check_component_boundary.sh` / `scripts/qa.sh` (CLI script shape only) | role-match (structural only) |
| `tests/lib/test_ingest.py` | test | file-I/O | `tests/lib/test_months.py` | exact (test style/structure) |
| `tests/lib/test_schemas.py` | test | transform | `tests/lib/test_months.py` | exact (test style/structure) |
| `tests/lib/test_features.py` | test | transform | `tests/lib/test_months.py` | exact (test style/structure) |
| `tests/lib/test_train.py` | test | batch | `tests/lib/test_months.py` | exact (test style/structure) |
| `tests/lib/test_evaluate.py` | test | transform | `tests/lib/test_months.py` | exact (test style/structure) |
| `tests/lib/test_registry.py` | test (mocked client) | request-response | `tests/lib/test_months.py` (style only); RESEARCH.md Pattern 5 (mock structure) | role-match |
| `pyproject.toml` (modify: populate `ml` group, add `dev` group entries) | config | — | existing `pyproject.toml` `dev`/`pipeline` groups | exact |
| `scripts/qa.sh` (modify: `UV_RUN` extras) | config/utility | — | existing `scripts/qa.sh` | exact (self-modification) |
| `data/zone_centroids.csv` | config/data (static artifact) | — | none | no-analog — one-time generated data file |

## Pattern Assignments

### `lib/ingest.py` (service, file-I/O/batch)

**Analog:** `lib/months.py` (module shape/conventions only — no I/O logic to borrow from it)

**Module docstring + import style** (`lib/months.py` lines 1-3):
```python
"""Month-range enumeration for backfill windows."""

import re
```
Apply the same one-line module docstring convention to `ingest.py` (e.g. `"""Chunked TLC Parquet ingest."""`).

**Error-raising style** (`lib/months.py` lines 9-15):
```python
def _parse_month(value: str) -> tuple[int, int]:
    match = _MONTH_PATTERN.match(value)
    if match is None:
        raise ValueError(f"expected a 'YYYY-MM' month string, got {value!r}")
```
Convention: raise plain built-in exceptions (`ValueError`) with an f-string message that includes `!r`-repr'd offending value — no custom exception hierarchy in this codebase yet. Reuse for `ingest.py`'s "reject malformed path/month" cases and for `schemas.py`'s "month failed loudly" cases (per D-09/REQ-C1), unless pandera's own `SchemaError`/`SchemaErrors` supersedes it (preferred for schema failures specifically — see below).

**Core chunked-read pattern** — no codebase analog; use RESEARCH.md verbatim (`02-RESEARCH.md` "Pattern 1: Chunked Parquet ingest (REQ-C4)", lines ~189-204):
```python
import pyarrow.parquet as pq
import pandas as pd

def read_month_chunked(path: str, batch_size: int = 200_000) -> pd.DataFrame:
    pf = pq.ParquetFile(path)
    frames = [batch.to_pandas() for batch in pf.iter_batches(batch_size=batch_size)]
    return pd.concat(frames, ignore_index=True)
```
Reuse `lib/months.py`'s `month_range()` to generate the 12-month window this function is called over (per CONTEXT.md "Reusable Assets").

**Row-level pre-filter-and-log step** (D-09a amendment) belongs in `ingest.py` per RESEARCH.md's module-boundary note (Pitfall 6): "this must be resolved before the first `lib/ingest.py`+`lib/schemas.py` integration test is written, since it changes the module boundary between 'ingest reads + cleans' and 'schemas validates.'" Concretely: `ingest.py` drops rows failing row-level numeric-quality checks (non-positive distance/duration, zone IDs 264/265) and logs the count/rate before handing the frame to `schemas.py` for structural validation.

---

### `lib/schemas.py` (model/validation, transform)

**Analog:** none in codebase — use RESEARCH.md directly.

**Core pandera schema pattern** (`02-RESEARCH.md` "Pattern 3: pandera 0.32.1 schema with real Checks", lines ~259-282):
```python
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
        pa.Check(lambda df: df["tpep_dropoff_datetime"] >= df["tpep_pickup_datetime"]),
    ],
    strict=False,  # allow extra columns to pass through unvalidated
)
```
**Critical design note (D-09a / Pitfall 6, mandatory):** do NOT apply this schema's row-level numeric checks (`trip_distance > 0`, dropoff>=pickup as literally read against raw un-filtered data) directly against a raw ingested month — real data has a ~1% baseline violation rate that will fail every month. `ingest.py` must pre-filter+log those rows first (see above); `schemas.py`'s checks should be validated against the already-filtered frame, and should primarily guard structural drift (missing/renamed columns, wrong dtypes, `PULocationID`/`DOLocationID` outside `[1,263]` beyond the known 264/265 case).

**Error-handling / "fails loudly" pattern:** use pandera's own `SchemaError`/`SchemaErrors` (with `lazy=True` for a full failure report) rather than hand-rolled `if`/`raise ValueError` — per RESEARCH.md's "Don't Hand-Roll" table: "pandera's `SchemaError`/`SchemaErrors` (with `lazy=True`) gives structured, column-and-row-addressable failure reports for free."

**Nullable columns caveat (Pitfall 7):** do not add `nullable=False` checks on `congestion_surcharge`/`airport_fee` — they're legitimately 100%-null for pre-Feb-2019 months; keep schema scoped exactly to D-09's five bullet points.

---

### `lib/features.py` (transform, file-I/O CSV join)

**Analog:** none in codebase — use RESEARCH.md directly (two patterns combine here).

**Vectorized haversine** (`02-RESEARCH.md` "Vectorized Haversine (REQ-C2)", lines ~484-500):
```python
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

**Zone-centroid join:** `features.py`'s runtime path only does `pandas.read_csv("data/zone_centroids.csv")` + a left-join on `PULocationID`/`DOLocationID` → `zone_id` (per RESEARCH.md "Architecture Patterns" diagram, lines ~156-164). It must NOT import `pyshp`/`pyproj` at runtime — those stay confined to `scripts/precompute_zone_centroids.py` (dev-only dependency group).

**dtype downcasting** (`02-RESEARCH.md` "dtype Downcasting (REQ-C3)", lines ~506-521):
```python
import pandas as pd

def downcast_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("trip_distance", "trip_duration_s"):
        df[col] = pd.to_numeric(df[col], downcast="float")   # float64 -> float32
    for col in ("PULocationID", "DOLocationID", "VendorID", "payment_type"):
        df[col] = df[col].astype("category")                  # low-cardinality -> category
    return df
```
**Pitfall 8 caveat:** `passenger_count`/`RatecodeID` are `float64` and can hold NaN — downcast via `downcast="float"` (→ float32), never a naive int downcast, unless nulls have been explicitly asserted-zero for that month first.

---

### `lib/train.py` (service, batch ML)

**Analog:** none in codebase — use RESEARCH.md directly.

**LightGBM fixed-config pattern** (`02-RESEARCH.md` "Pattern 4: LightGBM 4.7.0 minimal fixed config (REQ-D2)", lines ~289-309):
```python
import lightgbm as lgb
import pandas as pd

CATEGORICAL_FEATURES = ["PULocationID", "DOLocationID", "VendorID"]

def train_model(X: pd.DataFrame, y: pd.Series) -> lgb.LGBMRegressor:
    for col in CATEGORICAL_FEATURES:
        X[col] = X[col].astype("category")
    model = lgb.LGBMRegressor(
        objective="regression",
        metric="rmse",
        num_leaves=31,
        learning_rate=0.05,
        n_estimators=300,
        random_state=42,
    )
    model.fit(X, y, categorical_feature=CATEGORICAL_FEATURES)
    return model
```
**Verified pitfall to guard against:** LightGBM aligns pandas `category` dtypes between train/predict — unseen categories at predict time silently become missing. Persist the category set (e.g. an explicit `CategoricalDtype` built from the full 1-263 zone-ID range) rather than relying on whatever's present in the training split.

**Chronological split (D-08):** split on `tpep_pickup_datetime` value directly, not on which month's source file a row came from — per Pitfall 9, some rows' timestamps fall outside their nominal file's month; splitting by file risks quiet leakage.

---

### `lib/evaluate.py` (service, transform)

**Analog:** none in codebase; no RESEARCH.md code snippet given directly (only the architectural responsibility row). Compose from: plain RMSE computation (numpy/sklearn-style, no external pattern needed) + calls into `lib/registry.py`'s `get_champion_rmse()` for the champion-vs-candidate comparison. Keep `evaluate.py` mockable/testable without a real MLflow client by depending on `registry.py`'s already-mockable interface, not on `MlflowClient` directly (per Architectural Responsibility Map row: "the champion lookup crosses into the MLflow client, kept in a separate module so `evaluate.py` stays mockable without a client").

---

### `lib/registry.py` (service, external client wrapper, mocked)

**Analog:** none in codebase — use RESEARCH.md directly.

**MLflow registry wrapper pattern** (`02-RESEARCH.md` "Pattern 5: MLflow registry client wrapper, mockable (REQ-D3)", lines ~318-338):
```python
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
Uses MLflow 3.x's alias-based API (`set_registered_model_alias`/`get_model_version_by_alias`), NOT the deprecated `transition_model_version_stage` stage-transition API — confirmed via official docs and STACK.md.

---

### `scripts/precompute_zone_centroids.py` (utility, one-time script, batch/file-I/O)

**Analog:** structural only, `scripts/qa.sh`/`scripts/check_component_boundary.sh` (CLI-script shebang/`set -uo pipefail`/`REPO_ROOT` resolution convention — bash convention, not directly transferable to Python, but establishes this repo's "scripts are standalone, root-relative, fail-loud" convention).

**Core precompute pattern** (`02-RESEARCH.md` "Pattern 2: Zone centroid precompute", lines ~212-249) — pyshp read → pure-Python shoelace area-weighted centroid → pyproj reprojection EPSG:2263→EPSG:4326:
```python
import shapefile          # pyshp
from pyproj import Transformer

_transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)

def _ring_centroid(points: list[tuple[float, float]]) -> tuple[float, float, float]:
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
Download URL (Pitfall 1, load-bearing — the widely-cited S3 URL is dead): `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip` (verified `HTTP 200`). Must handle 23/263 multi-part zones (Pitfall 4) via the `parts`-index splitting shown above — do not use bbox-midpoint.

---

### `tests/lib/test_ingest.py`, `test_schemas.py`, `test_features.py`, `test_train.py`, `test_evaluate.py`, `test_registry.py`

**Analog:** `tests/lib/test_months.py` (exact match for test-file structure/style)

**Style to copy** (`tests/lib/test_months.py`, full file, 55 lines):
```python
"""Exact-value tests for lib.months.month_range."""

import pytest

from lib.months import month_range


def test_month_range_crosses_year_boundary() -> None:
    assert month_range("2019-11", "2020-02") == [
        "2019-11", "2019-12", "2020-01", "2020-02",
    ]

def test_month_range_rejects_month_out_of_range() -> None:
    with pytest.raises(ValueError):
        month_range("2019-13", "2019-14")
```
Conventions to reuse: one-line module docstring naming the function/module under test; plain `def test_x() -> None:` (no classes); `pytest.raises(...)` for error-path tests; tiny exact-value fixtures/asserts (no snapshot testing); one happy-path test + one test per rejected/edge input. Per D-07/CONTEXT.md, all `pytest` fixtures in this phase's new tests must be **tiny synthetic DataFrames constructed in-test** (e.g. `pd.DataFrame({...})` with a handful of rows) — never load the real downloaded TLC Parquet in the fast test suite; that's reserved for the separate benchmark script (REQ-C5).

**`test_registry.py` additionally follows RESEARCH.md Pattern 5's mock structure** (lines ~340-357):
```python
from unittest.mock import MagicMock
from mlflow.exceptions import MlflowException
from lib.registry import ModelRegistry

def test_get_champion_rmse_returns_none_when_no_champion() -> None:
    client = MagicMock()
    client.get_model_version_by_alias.side_effect = MlflowException("not found")
    registry = ModelRegistry(client, "trip-duration")
    assert registry.get_champion_rmse() is None
```

**Coverage requirement (Pitfall 10, mandatory for every new test file):** `pyproject.toml` enforces `--cov-fail-under=100` with `branch = true` — every branch (including exception paths like `registry.py`'s `MlflowException` handler) needs an explicit test, or the entire `pytest` run fails, not just the under-covered module.

---

### `pyproject.toml` (modify)

**Analog:** existing file itself — extend the pattern already present.

Current state (verified, full relevant excerpt):
```toml
[project.optional-dependencies]
dev = [
    "ruff~=0.16.0",
    "mypy~=2.3.0",
    "pytest~=9.1.0",
    "pytest-cov",
    "pre-commit>=4.6.2",
]
# Phase 3 fills this group: kfp, kfp-kubernetes.
pipeline = []
# Phase 2 fills this group: pandas, numpy, pyarrow, pandera, lightgbm, mlflow.
ml = []
```
Populate `ml` with the STACK.md-pinned versions (RESEARCH.md "Installation" block); add `pandas-stubs`, `pyshp`, `pyproj` to `dev` (RESEARCH.md explicitly places `pyshp`/`pyproj` in `dev`, NOT `ml`, since they're precompute-script-only). `[tool.mypy] files = ["lib"]` already scopes `mypy --strict` to `lib/` — no mypy config change needed, new modules fall under it automatically.

---

### `scripts/qa.sh` (modify — mandatory first task, Pitfall 5)

**Analog:** existing file itself.

Current `UV_RUN` construction (verified, lines from live read):
```bash
if [ -n "${CI:-}" ]; then
  UV_RUN=(uv run --frozen --extra dev)
else
  UV_RUN=(uv run --extra dev)
fi
```
**Must change to include `--extra ml`** in both branches (`uv run --frozen --extra dev --extra ml` / `uv run --extra dev --extra ml`) before any pandas-importing `lib/` module is written — otherwise `scripts/qa.sh test`/`typecheck` fail with `ModuleNotFoundError: No module named 'pandas'` even though `uv add --extra ml pandas` succeeded. This is RESEARCH.md's explicit "Phase 2, first task" recommendation (Pitfall 5).

## Shared Patterns

### Pure-function, no-class module shape
**Source:** `lib/months.py` (entire file)
**Apply to:** All `lib/` modules where feasible — this codebase currently favors plain module-level functions with private `_`-prefixed helpers over classes, except where external-client state needs holding (`lib/registry.py`'s `ModelRegistry` class is the one justified exception, per RESEARCH.md Pattern 5, since it wraps a stateful `MlflowClient` reference).

### Error-raising style: plain built-in exceptions with `!r`-repr'd f-string messages
**Source:** `lib/months.py` lines 9-15
**Apply to:** Any hand-written validation outside pandera's own schema-failure path (e.g. `ingest.py`'s malformed-path checks). Prefer pandera's `SchemaError`/`SchemaErrors` specifically for `schemas.py`'s validation failures (see above) rather than reinventing this with manual `raise`.

### Test style: plain function tests, exact-value asserts, tiny synthetic fixtures
**Source:** `tests/lib/test_months.py` (entire file)
**Apply to:** All 6 new `tests/lib/*.py` files. No test classes, no fixtures files/conftest complexity shown yet in this codebase — keep new tests at the same simplicity level unless a module's setup genuinely requires a shared `conftest.py` fixture (e.g. a synthetic DataFrame reused across several `test_features.py` cases).

### 100% branch coverage gate applies module-by-module
**Source:** `pyproject.toml` `[tool.pytest.ini_options]` / `[tool.coverage.run]` (`--cov-fail-under=100`, `branch = true`)
**Apply to:** Every new `lib/` module — treat "one test per branch, including exception paths" as this phase's per-module Definition of Done (Pitfall 10), not a final phase-end check.

### `lib/` stays free of KFP/Kubernetes imports; `components/` stays free of pandas/numpy
**Source:** `scripts/check_component_boundary.sh` (full file, regex-enforced against `components/*.py`)
**Apply to:** All Phase 2 `lib/` files, by omission — none of them should import `kfp`/`kfp_kubernetes`. This gate currently only scans `components/` (which doesn't exist yet), so it passes vacuously-safe for Phase 2, but the planner should NOT add any pandas import under `components/` in this phase, keeping the gate meaningful when Phase 3 populates that directory.

### `scripts/qa.sh` is the single entrypoint for lint/format/typecheck/test/boundary
**Source:** `scripts/qa.sh` (full file)
**Apply to:** No new script-running convention needed — new `lib/` modules and tests plug into existing `qa.sh typecheck`/`qa.sh test` subcommands automatically once `UV_RUN` includes `--extra ml` (see modification above).

## No Analog Found

Files with no close structural/domain match in the codebase — planner must rely on `02-RESEARCH.md`'s verified Code Examples/Architecture Patterns sections (cited per-file above) rather than an in-repo analog:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `lib/schemas.py` | model | transform | No pandera/validation code exists anywhere in the repo yet; RESEARCH.md Pattern 3 is the source of truth |
| `lib/features.py` | transform | transform, file-I/O | No numpy/haversine/downcasting code exists yet; RESEARCH.md Vectorized Haversine + dtype Downcasting sections are the source of truth |
| `lib/train.py` | service | batch | No ML training code exists yet; RESEARCH.md Pattern 4 is the source of truth |
| `lib/evaluate.py` | service | transform | No RMSE/comparison code exists yet; compose from plain math + `registry.py`'s interface |
| `lib/registry.py` | service | request-response (mocked) | No external-client-wrapper code exists yet; RESEARCH.md Pattern 5 is the source of truth |
| `scripts/precompute_zone_centroids.py` | utility | batch, file-I/O | No shapefile/geo precompute script exists yet; RESEARCH.md Pattern 2 is the source of truth, verified live this session |
| `data/zone_centroids.csv` | data artifact | — | Generated output, not hand-written code — no pattern to extract, only the generating script matters |

## Metadata

**Analog search scope:** `lib/`, `tests/lib/`, `scripts/`, `pyproject.toml`, repo root (searched via direct `ls`/`cat` — codebase is small enough that a full manual inventory was more reliable than `Glob`/`Grep` sweeps)
**Files scanned:** `lib/months.py`, `tests/lib/test_months.py`, `scripts/qa.sh`, `scripts/check_component_boundary.sh`, `pyproject.toml`
**Pattern extraction date:** 2026-08-20
</content>
