# Phase 2: Data & Model Engineering (lib/) - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Write 100% of the pandas/numpy/modeling logic in `lib/` — ingest, pandera schema validation, feature engineering (vectorized haversine, dtype downcasting), LightGBM training, evaluation, and an MLflow registry client wrapper — correctness-proven via unit tests and speed-proven via a benchmark table. No Kubernetes/Kubeflow work happens in this phase (that's Phase 3): no k3d cluster, no real MinIO/MLflow server, no `@dsl.component` wiring. The MLflow registry wrapper is built and tested against a mocked client only — the real tracking server doesn't exist until Phase 3 stands up the cluster.

</domain>

<decisions>
## Implementation Decisions

### Distance Feature Source
- **D-06:** NYC TLC dropped raw pickup/dropoff lat/lon from the Yellow/Green trip record schema starting July 2016, replacing it with `PULocationID`/`DOLocationID` zone IDs — the 2019–2020 window this project uses has zone IDs only, never coordinates. Haversine distance (REQ-C2) is computed from a **static zone-centroid lookup table**: a small CSV (`zone_id, centroid_lat, centroid_lon`) precomputed once from TLC's public taxi zone data and committed to the repo, joined against `PULocationID`/`DOLocationID` per trip. Explicitly rejected: pulling in `geopandas`/`shapely` to compute centroids from the TLC shapefile at runtime — accurate, but a heavy dependency outside `research/STACK.md`'s pinned list, and not worth the setup time inside the 10–15h budget for a one-time precomputation. — **Reversibility:** reversible — swapping the static lookup for a shapefile-derived one later is a data-source change behind the same join, not an API change.

### Phase 2 Dataset Scale
- **D-07:** Download the real, full 12-month NYC TLC Parquet window now (not a sampled/synthetic subset) via a one-time download script; cache locally, gitignored. This real data backs `ingest`/`features` development and the REQ-C5 benchmark table — a benchmark or chunked-read proof (REQ-C4) against a tiny sample wouldn't be a credible demonstration. Unit tests (`pytest`) continue using tiny synthetic DataFrame fixtures for speed and determinism, matching the pattern `tests/lib/test_months.py` already established in Phase 1 — real data is for the benchmark and manual/integration-style verification, not the fast test suite.

### Train/Test Split
- **D-08:** Chronological (time-based) split: train on the earlier months of the 12-month window, test/evaluate on the final months — which span into the pre/post-COVID drift event. A random split was explicitly rejected: REQ-D1's whole rationale for the 12-month window is that it spans a real drift event, and a random split would average across the drift and hide exactly the signal the dataset was chosen to demonstrate.

### pandera Schema Strictness (REQ-C1)
- **D-09:** Concrete, real `Check`s — not a passthrough dtype-only schema:
  - Non-null on key columns (pickup/dropoff datetime, `PULocationID`/`DOLocationID`, trip distance/duration).
  - `trip_distance` and computed trip duration both strictly positive.
  - `PULocationID`/`DOLocationID` within TLC's valid zone-ID range (1–263).
  - Dropoff datetime ≥ pickup datetime.
  - `passenger_count` within a reasonable bound (reject obviously corrupt values, e.g. 0 or absurdly high).
  A month that fails any check fails loudly (non-zero exit, logged reason) per REQ-C1's acceptance criterion — the whole month is rejected, not silently filtered row-by-row.

### Claude's Discretion
- Exact LightGBM hyperparameter config (num_leaves, learning_rate, etc.) — a single fixed, reasonable config per REQ-D2 ("boring", no tuning). Document the chosen values and rationale briefly in the training module/README, but the specific numbers are left to planner/executor judgment.
- Internal module boundaries within `lib/` beyond what `research/ARCHITECTURE.md` already sketches (`ingest.py`, `schemas.py`, `features.py`, `train.py`, `evaluate.py`, `registry.py`) — naming/helper-function granularity left to the planner.
- Exact benchmark methodology mechanics (how the before/after numbers are captured — a script vs. a notebook cell vs. a pytest-adjacent timing harness) — planner's call, as long as the README table ends up with real, reproducible numbers per REQ-C5.
- Download-script mechanics for the 12-month TLC Parquet pull (D-07) — retry/resume behavior, exact CLI shape — left to executor discretion.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Scope
- `.planning/REQUIREMENTS.md` §Category C (REQ-C1–C5), §Category D (REQ-D1–D3) — the locked requirements this phase implements
- `.planning/PROJECT.md` — project vision, constraints (10–15h/1 week, 16GB RAM), Key Decisions table

### Research
- `.planning/research/ARCHITECTURE.md` — `lib/` module layout (`ingest.py`, `schemas.py`, `features.py`, `train.py`, `evaluate.py`, `registry.py`), the MinIO/MLflow separation-of-concerns model, and the explicit execution ordering (offline `lib/` work fully before any Kubernetes step)
- `.planning/research/STACK.md` — pinned versions: pandas 2.3.x, numpy 2.5.x, pyarrow, pandera 0.32.1, LightGBM 4.7.0, mlflow[extras] 3.15.1 client, boto3; note MLflow 3.x uses `set_registered_model_alias` (`@champion`/`@candidate`), not the deprecated stage-transition API
- `.planning/research/FEATURES.md` §Table Stakes — why the benchmark table and pandera real-Checks requirement matter for the project's interview/portfolio goal, not just "having tests"
- `.planning/research/PITFALLS.md` Pitfall on MinIO/MLflow storage collision (line ~130) — relevant context for how `registry.py`'s mockable design anticipates the real server Phase 3 stands up

### Prior Phase Decisions
- `.planning/phases/01-repo-foundation-ci-quality-gates/01-CONTEXT.md` — D-04: `pyproject.toml` already reserves an `ml` optional-dependency group (currently empty) for exactly this phase's dependencies (pandas, numpy, pyarrow, pandera, lightgbm, mlflow); D-02: `mypy --strict` scope is `lib/` only, which this phase's new modules fall under

### Roadmap
- `.planning/ROADMAP.md` §Phase 2 — goal statement and success criteria this phase must satisfy

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/months.py` (`month_range(start_month, end_month) -> list[str]`) — the 12-month window's month list can be generated with this existing, tested utility rather than reimplementing month-range logic.
- `scripts/qa.sh` — the shared lint/format/typecheck/test/boundary entrypoint; new `lib/` modules and their tests plug directly into the existing `mypy --strict lib` and `pytest` subcommands with no script changes needed.
- `scripts/check_component_boundary.sh` — already enforces that no pandas/DataFrame logic exists under `components/`; this phase's work stays entirely under `lib/`, so the boundary gate should continue passing untouched.

### Established Patterns
- Tiny synthetic-fixture unit tests with exact-value assertions (`tests/lib/test_months.py`) — the pattern this phase's `pytest` suite should follow for `ingest`/`schemas`/`features`/`train`/`evaluate`/`registry`, per D-07's separation of "fast synthetic tests" vs "real-data benchmark".
- `pyproject.toml`'s `ml` optional-dependency group is pre-declared (D-04, Phase 1) and currently empty — this phase's first task is populating it with the STACK.md-pinned versions.

### Integration Points
- None yet with Kubernetes/KFP — by design, this phase's code has zero KFP imports (`research/ARCHITECTURE.md`'s explicit constraint on `lib/`). Phase 3 wraps these `lib/` functions in thin `components/` bodies.

</code_context>

<specifics>
## Specific Ideas

No additional specific implementation ideas beyond the four decisions above — the user confirmed all four Recommended options directly, with no deviations or additional constraints raised during discussion.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 2 scope. No scope-creep suggestions arose.

</deferred>

---

*Phase: 2-Data & Model Engineering (lib/)*
*Context gathered: 2026-08-20*
