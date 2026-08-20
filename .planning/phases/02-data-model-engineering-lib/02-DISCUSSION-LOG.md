# Phase 2: Data & Model Engineering (lib/) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-20
**Phase:** 2-Data & Model Engineering (lib/)
**Areas discussed:** Distance Feature Source, Phase 2 Dataset Scale, Train/Test Split, pandera Schema Strictness

---

## Distance Feature Source

| Option | Description | Selected |
|--------|-------------|----------|
| Static zone-centroid lookup | Precompute a small CSV (zone_id → lat/lon centroid) from TLC's public taxi zone data, committed to the repo; join against PULocationID/DOLocationID. No new heavy GIS dependency. | ✓ |
| Self-computed centroid from official shapefile | Use geopandas/shapely to derive centroids from TLC's taxi_zones.shp at runtime — more precise, but adds a dependency outside research/STACK.md and more setup time. | |

**User's choice:** Static zone-centroid lookup (Recommended)
**Notes:** 2019–2020 TLC data has no raw lat/lon (removed from the schema July 2016 onward, replaced by zone IDs) — this was surfaced as a domain landmine specific to the project's chosen dataset window, not a generic implementation choice.

---

## Phase 2 Dataset Scale

| Option | Description | Selected |
|--------|-------------|----------|
| Download full 12 months of real data now | One-time download script, gitignored local cache; used for ingest/features dev and the REQ-C5 benchmark. Unit tests still use tiny synthetic fixtures. | ✓ |
| Small sample/subset now, full data deferred to Phase 3 | Saves bandwidth/disk now, but the benchmark and chunked-read proof (REQ-C4) wouldn't be credible against a tiny sample. | |

**User's choice:** Download full 12 months of real data now (Recommended)
**Notes:** None.

---

## Train/Test Split

| Option | Description | Selected |
|--------|-------------|----------|
| Chronological split | Train on earlier months, test on final months spanning the drift event — matches REQ-D1's stated rationale for choosing this window. | ✓ |
| Random split | Standard ML practice, but would average across the drift event and hide the exact signal the dataset window was chosen to demonstrate. | |

**User's choice:** Chronological split (Recommended)
**Notes:** None.

---

## pandera Schema Strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Concrete real Checks | Non-null on key columns; positive distance/duration; valid zone-ID range (1–263); dropoff ≥ pickup; reasonable passenger_count bound. Whole month fails loudly on violation. | ✓ |
| Looser dtype/nullability-only checks | Simpler, but risks being read as a "passthrough" schema — the exact failure mode research/FEATURES.md warns against. | |

**User's choice:** Concrete real Checks (Recommended)
**Notes:** None.

---

## Claude's Discretion

- Exact LightGBM hyperparameter config (single fixed, documented, no tuning).
- Internal `lib/` module boundaries beyond ARCHITECTURE.md's sketch (`ingest.py`, `schemas.py`, `features.py`, `train.py`, `evaluate.py`, `registry.py`).
- Exact benchmark methodology mechanics (script vs. harness), as long as README ends up with real, reproducible numbers.
- Download-script mechanics for the 12-month TLC Parquet pull (retry/resume behavior, CLI shape).

## Deferred Ideas

None — discussion stayed within Phase 2 scope.
