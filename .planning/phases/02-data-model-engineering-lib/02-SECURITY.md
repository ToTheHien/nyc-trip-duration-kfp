---
phase: 2
slug: data-model-engineering-lib
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-23
---

# Phase 2 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| PyPI -> developer machine / CI runner | Third-party package code executes at install and import time | Package bytes / executable code |
| TLC CloudFront -> `lib/ingest.py` | Externally-controlled Parquet bytes become in-process DataFrame structure and dtypes | Trip-record Parquet bytes |
| Model artifact file -> `lib/train.py` loader | Serialized model bytes become an in-process object graph | LightGBM model bytes |
| TLC CloudFront -> local filesystem | Externally-controlled bytes (Parquet files, a zip archive) written to disk by a maintainer script | Parquet / zip bytes |
| Zip archive members -> extraction directory | Archive-controlled path strings determine write destinations | Archive member paths |
| `lib/registry.py` -> MLflow tracking service | External service API surface, mocked in Phase 2 | Mocked client calls only |
| `data/zone_centroids.csv` -> `lib/features.py` | A committed repository file supplies the coordinates every distance feature is derived from | Zone id -> lat/lon rows |
| TLC-sourced trip frame -> feature transform | Externally-originated zone ids drive a join whose misses would otherwise become silent nulls | Zone id join keys |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-SC | Tampering | `pyshp`/`pyproj` install (both flagged `[SUS]`, neither in Phase 1's STACK.md) | high | mitigate | Task 1 blocking-human package-legitimacy checkpoint verified against pypi.org before install, not auto-approvable under `mode: yolo` (recorded verdict in 02-01-SUMMARY.md) | closed |
| T-02-01 | Tampering | `lib/schemas.py` validation of externally-sourced trip data | medium | mitigate | `trip_schema.validate(df, lazy=True)` (`lib/schemas.py:66`) asserts column presence, dtypes, non-nullability and value ranges before any downstream module trusts the frame | closed |
| T-02-05 | Denial of Service | `lib/ingest.py` memory footprint reading a ~150MB month on a 16GB machine | medium | mitigate | `read_month_chunked` (`lib/ingest.py:43`) bounds peak residency via `pyarrow.parquet.ParquetFile.iter_batches(batch_size=...)` instead of a whole-file read | closed |
| T-02-02 | Information Disclosure | `lib/registry.py` credential handling | low | accept | Phase 2 injects a mocked client and handles no tracking-server URI, token, or S3 credential; real credential handling is scoped to Phase 3 | closed (accepted) |
| T-02-03 | Tampering | `scripts/precompute_zone_centroids.py` archive extraction | medium | mitigate | Every zip member's resolved path is checked to stay inside the work directory (`scripts/precompute_zone_centroids.py:65-74`); absolute paths and symlink members are refused before any write | closed |
| T-02-04 | Tampering | `scripts/download_tlc_data.py` transport and completion handling | medium | mitigate | HTTPS-only pinned CloudFront host (`BASE_URL`, line 15), explicit request timeout, and an atomic `.part`-then-rename write (lines 48-61) keep a truncated body from being cached as complete | closed |
| T-02-07 | Spoofing | Legacy direct-S3 URL circulating in tutorials | low | mitigate | Verified absent from both scripts and `lib/` — only the CloudFront host is used | closed |
| T-02-08 | Denial of Service | 12 monthly Parquet files on a 16GB / 314GB-free workstation | low | accept | ~1.5GB total against 314GB free; the streaming chunked write keeps peak memory flat regardless of file size | closed (accepted) |
| T-02-06 | Tampering / Elevation of Privilege | `lib/train.py` model persistence and loading | high | mitigate | Persist/load exclusively through LightGBM's native text format (`booster_.save_model` / `lgb.Booster(model_file=...)`, `lib/train.py:99-111`); no pickle/joblib import anywhere in the module | closed |
| T-02-09 | Repudiation | Champion promotion without a recorded metric | low | mitigate | `tag_version_rmse` (`lib/registry.py:32`) records the RMSE on the model version alongside alias promotion | closed |
| T-02-10 | Tampering | Silent row loss masking upstream data corruption | medium | mitigate | Every dropped row is attributed to one of four counted reasons (`lib/ingest.py:86-89`) and totals are logged at INFO (`lib/ingest.py:156-163`) | closed |
| T-02-11 | Spoofing | A path-derived month string reaching the filesystem | low | mitigate | Month strings resolve only through `month_parquet_path` (`lib/ingest.py:35`), which composes a fixed filename pattern under a fixed data directory | closed |
| T-02-12 | Tampering | `lib/features.py` zone-centroid join producing silent nulls | medium | mitigate | Left merges (`lib/features.py:146-147`) keep row count invariant; any surviving unmapped zone id raises `ValueError` naming the offending ids (`lib/features.py:201`) | closed |
| T-02-13 | Information Disclosure | `scripts/benchmark_features.py` machine description printed into README | low | accept | Reported facts (Python version, CPU count, RAM) are non-sensitive for a deliberately public portfolio repository (D-05) | closed (accepted) |
| T-02-14 | Tampering | Runtime dependency creep into the feature path | low | mitigate | `lib/features.py` imports only `math` and `pathlib.Path` at module scope — no `pyshp`/`pyproj`/`shapefile`/`geopandas`/`shapely`/`fiona`; verified by the plan's AST acceptance check at execution time (02-05-SUMMARY.md) and re-confirmed by direct import inspection during this audit | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-02 | `lib/registry.py` only exercises a mocked MLflow client in Phase 2 — no real tracking-server URI, token, or S3 credential exists yet to disclose. Real credential handling is scoped to Phase 3 when a live server exists. | Phase 2 plan authors (02-01-PLAN.md, 02-03-PLAN.md) | 2026-08-23 |
| AR-02-02 | T-02-08 | 12 monthly Parquet files total ~1.5GB against 314GB free disk (RESEARCH.md `## Environment Availability`); the streaming chunked write keeps peak memory flat regardless of file size. | Phase 2 plan authors (02-02-PLAN.md) | 2026-08-23 |
| AR-02-03 | T-02-13 | The benchmark script prints Python version, CPU count, and RAM into the README — needed to interpret the benchmark numbers and not sensitive for a deliberately public portfolio repository (D-05). | Phase 2 plan authors (02-05-PLAN.md) | 2026-08-23 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-23 | 15 | 15 | 0 | /gsd-secure-phase (orchestrator, L1 grep-depth — ASVS level 1, register authored at plan time, short-circuit per secure-phase.md Step 3) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-23
