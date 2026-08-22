---
phase: 02-data-model-engineering-lib
reviewed: 2026-08-22T09:13:43Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - .github/workflows/ci.yml
  - README.md
  - lib/evaluate.py
  - lib/features.py
  - lib/ingest.py
  - lib/registry.py
  - lib/schemas.py
  - lib/train.py
  - pyproject.toml
  - scripts/benchmark_features.py
  - scripts/download_tlc_data.py
  - scripts/precompute_zone_centroids.py
  - scripts/qa.sh
  - tests/lib/test_evaluate.py
  - tests/lib/test_features.py
  - tests/lib/test_ingest.py
  - tests/lib/test_registry.py
  - tests/lib/test_schemas.py
  - tests/lib/test_tracer_end_to_end.py
  - tests/lib/test_train.py
findings:
  critical: 0
  warning: 4
  info: 2
  total: 6
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-08-22T09:13:43Z
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Reviewed the Phase 2 `lib/` layer (pandas ingest, two-tier pandera quality gate, vectorized
haversine feature pipeline, chronological split, LightGBM training, RMSE evaluation, MLflow
alias-based registry), its supporting scripts, CI/tooling config, and the full test suite.

No BLOCKER-level defects were found. The core correctness properties called out for
scrutiny hold up under inspection:

- The D-09a two-tier boundary is internally consistent: `PLACEHOLDER_ZONE_IDS` /
  `PASSENGER_COUNT_MIN` / `PASSENGER_COUNT_MAX` are shared constants imported by both
  `lib.ingest.filter_trip_quality` (tier one, counted pre-filter) and `lib.schemas.trip_schema`
  (tier two, structural), so the two tiers cannot silently drift apart. Null handling
  (`passenger_count.notna()` guard, `isin` on placeholder IDs) is correct at both tiers.
  `filter_trip_quality`'s combined boolean mask does not reorder rows, matching its documented
  contract, and is exercised by a dedicated ordering test.
- `haversine_km_rowwise` is never called from `build_features` — confirmed by direct code
  inspection and by `test_build_features_never_calls_dataframe_or_series_apply`, which monkeypatches
  `DataFrame.apply`/`Series.apply` to raise. The production distance path is fully vectorized.
- `downcast_features`'s dtype contract (float32 for continuous columns via `astype`, not
  `to_numeric(downcast=...)`; int8 for derived hour/day-of-week; fixed 1-263 categorical for
  zone IDs) matches its own docstring and is defended by exact-value tests, including a NaN
  round-trip test for `passenger_count`.
- `build_features` is a pure function with respect to its `df` argument (only mutates copies
  produced by `merge`/`downcast_features`) and is proven idempotent and non-mutating by
  dedicated tests.
- No `subprocess`/`eval`/`exec`/pickle usage anywhere in `lib/` or `scripts/`. Model
  persistence explicitly avoids pickle in favor of LightGBM's native text format
  (`lib/train.py:99-115`). `scripts/precompute_zone_centroids.py`'s zip extraction defends
  against zip-slip, absolute-path members, and symlink members before calling
  `extractall` — a genuine, correctly-implemented security control.
- `scripts/download_tlc_data.py` and `scripts/qa.sh`/CI build only static, regex-validated
  strings (`lib.months._parse_month` enforces `^\d{4}-\d{2}$`) into file paths and URLs; no
  path-traversal or injection vector was found.

The findings below are narrower robustness/consistency gaps: an unhandled-exception path in
the registry wrapper, an inconsistency between how zone IDs and `VendorID` are protected
against unseen-category-becomes-missing at predict time, and two minor tooling/config
observations.

## Warnings

### WR-01: `ModelRegistry.get_champion_rmse` raises an unhandled exception if a champion exists but has no/malformed RMSE tag

**File:** `lib/registry.py:24-30`
**Issue:** `get_champion_rmse` only catches `MlflowException` (raised when no champion alias
exists). If a champion version *does* exist but was promoted without going through
`tag_version_rmse` first (manual promotion via the MLflow UI/CLI, a partially-failed prior
pipeline run that tagged-then-crashed-before-promoting in the wrong order, or a tag
key/format drift), `version.tags[RMSE_TAG]` raises `KeyError`, and `float(...)` on a
non-numeric tag value raises `ValueError`. Neither is caught, so a champion-comparison call
crashes with a low-context internal exception instead of a clear, actionable error — and the
crash happens inside logic REQ-D3's champion/candidate promotion depends on being reliable.
**Fix:**
```python
def get_champion_rmse(self) -> float | None:
    try:
        version = self._client.get_model_version_by_alias(self._model_name, CHAMPION_ALIAS)
    except MlflowException:
        return None
    try:
        return float(version.tags[RMSE_TAG])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(
            f"champion model version {version.version!r} for {self._model_name!r} has no "
            f"usable {RMSE_TAG!r} tag: {exc}"
        ) from exc
```

### WR-02: `VendorID` has no fixed-category protection against unseen values at predict time, unlike `PULocationID`/`DOLocationID`

**File:** `lib/features.py:174` (`downcast_features`), `lib/train.py:89-93` (`train_trip_duration_model`)
**Issue:** `lib/features.py`'s own module docstring and `ZONE_CATEGORY_DTYPE` comment explain
in detail *why* zone IDs must be cast against an explicit, fixed 1-263 category range rather
than whatever zones happen to be present in a given frame: "LightGBM aligns pandas categories
observed at fit time and treats any category unseen at fit time as missing at predict time; a
zone that only appears in the post-drift evaluation window must still score as that zone."
`VendorID` is downcast to `"category"` (both in `downcast_features` and again in
`train_trip_duration_model`) with no such fixed category set — its categories are inferred
from whatever values happen to be present in the input frame at the moment of the cast. If a
`VendorID` value appears in the post-split evaluation window (or a later month) that wasn't
present when the train-side frame's categories were established, it silently becomes a
missing value at predict time — exactly the failure mode `ZONE_CATEGORY_DTYPE` was introduced
to prevent, just for a different column. `test_unseen_zone_scores_without_becoming_missing`
exists for `PULocationID`; there is no analogous test for `VendorID`, so this gap is untested
as well as unguarded.
**Fix:** Introduce a `VENDOR_ID_CATEGORY_DTYPE` (TLC's documented VendorID domain, e.g. `{1, 2,
6, 7}`) analogous to `ZONE_CATEGORY_DTYPE`, and cast `VendorID` against it in both
`downcast_features` and `train_trip_duration_model` instead of a bare `"category"` astype.

### WR-03: `build_features`/`downcast_features` can silently turn an out-of-range zone ID into a missing value instead of failing loudly

**File:** `lib/features.py:172-173` (`downcast_features`), `lib/features.py:193-204` (`build_features`)
**Issue:** `build_features` explicitly raises `ValueError` when a row's zone ID has no
matching centroid row (`merged[coord_columns].isna().any(axis=1)` check), which the docstring
frames as a hard requirement: a genuine centroid-table/trip-data inconsistency "must fail
rather than silently emitting a null distance feature." However, this check only validates
that a centroid *exists* for the zone ID — it does not validate that the zone ID itself falls
inside `ZONE_CATEGORY_DTYPE`'s pinned `[1, 263]` range. If `centroids` ever contains a row for
a zone ID outside that range (e.g. a future centroid-table regeneration that includes 264/265,
or any off-by-one drift in `data/zone_centroids.csv`), the centroid join would succeed (no
`ValueError`), but `downcast_features`'s `astype(ZONE_CATEGORY_DTYPE)` would silently convert
that zone ID to `NaN` — precisely the "silently emitting a null" outcome the function's own
docstring says must not happen. Correctness today rests entirely on an implicit,
unenforced invariant (the committed CSV happens to contain exactly zones 1-263), not on
anything `build_features` itself checks.
**Fix:** Validate `PULocationID`/`DOLocationID` membership in `ZONE_CATEGORY_DTYPE.categories`
(or reuse `pandera`'s existing `VALID_ZONE_MIN`/`VALID_ZONE_MAX` range) inside `build_features`
before/after the centroid-join check, and raise the same kind of `ValueError` on failure rather
than relying on the downstream astype to happen to line up.

### WR-04: `train_trip_duration_model` mutates the caller's `x` in place, contrary to the project's stated immutability convention

**File:** `lib/train.py:77-96`
**Issue:** The function's docstring explicitly documents and justifies mutating `x` in place
("Casts the categorical columns on x in place (not a copy)... so the caller's x must carry the
same dtype forward"). This is a deliberate design choice with a real technical reason
(LightGBM requires an identically-dtyped frame at predict time), but it is a genuine exception
to this codebase's otherwise-consistent immutable-by-default pattern (`build_features`,
`chronological_split`, `downcast_features`, `filter_trip_quality` all operate on copies and
document that explicitly). A caller that holds a second reference to the same `x` object
(easy to do accidentally in a notebook or a future Phase 3 component that reuses a variable)
would observe its dtype silently change out from under it as a side effect of calling
`train_trip_duration_model`. Not a bug in isolation, but worth flagging because it is easy to
trip over given every sibling function in `lib/` promises the opposite.
**Fix:** Either rename the parameter/document more prominently (e.g. in the function name, not
just the docstring) that this call mutates its input, or have the caller pass an explicit copy
at the one call site that needs the post-fit dtype (Phase 3), keeping `lib/train.py`'s public
surface consistent with the rest of `lib/`.

## Info

### IN-01: `mypy --strict` type-checking gate only covers `lib/`, not `scripts/` or `tests/`

**File:** `pyproject.toml:44-54`, `scripts/qa.sh:32-34`
**Issue:** `[tool.mypy] files = ["lib"]` and `scripts/qa.sh typecheck` (`mypy --strict lib`)
mean the `typecheck` CI job never runs against `scripts/benchmark_features.py`,
`scripts/download_tlc_data.py`, or `scripts/precompute_zone_centroids.py` — three files
reviewed in this phase that do carry real type annotations and would presumably be expected
to pass strict mypy. A type error introduced in any of these scripts would not be caught by
CI today.
**Fix:** If this scope limitation is intentional (e.g. scripts are considered
maintainer-tooling rather than shipped `lib/` code), document it in `README.md`'s CI section
alongside the other documented scope notes; otherwise widen `files` (or add a second mypy
invocation) to include `scripts`.

### IN-02: Ruff's security rule set (`S`) is not enabled

**File:** `pyproject.toml:41-42`
**Issue:** `[tool.ruff.lint] select = ["E", "F", "I", "UP", "B", "SIM", "ANN"]` does not include
`S` (flake8-bandit-equivalent security lint rules: hardcoded-password detection, unsafe
`subprocess`/`eval` usage, weak-hash usage, etc.). No violations of that class were found by
manual review in this phase's files, but the project's own Python security convention calls
out `bandit`-equivalent static analysis as a standard practice, and nothing in CI currently
runs it.
**Fix:** Add `"S"` to `[tool.ruff.lint] select` (with any necessary targeted `# noqa` /
per-file ignores for the two download scripts' `urllib` usage, which ruff's `S310`/`S320` may
flag) so this class of issue is caught mechanically going forward.

---

_Reviewed: 2026-08-22T09:13:43Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
