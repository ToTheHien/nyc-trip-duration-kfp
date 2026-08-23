---
phase: 2
slug: data-model-engineering-lib
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-23
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pyproject.toml` `[tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` (`testpaths = ["tests"]`) |
| **Quick run command** | `uv run pytest tests/lib/test_<module>.py -q` |
| **Full suite command** | `./scripts/qa.sh test` (also runs `./scripts/qa.sh lint`/`format`/`typecheck`/`boundary` as the full gate) |
| **Estimated runtime** | ~10-15 seconds (100 tests, no network/GPU dependencies) |

---

## Sampling Rate

- **After every task commit:** Run the module's quick test file
- **After every plan wave:** Run `./scripts/qa.sh test` (full suite, 100% branch coverage enforced)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task | Plan | Requirement | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|-----------|--------------------|-------------|--------|
| Package-legitimacy gate (pyshp/pyproj) | 02-01 | REQ-C2 | blocking-human checkpoint | N/A (one-time PyPI legitimacy check, recorded in 02-01-SUMMARY.md) | N/A | ✅ green |
| ml dependency group + qa.sh/CI wiring | 02-01 | REQ-C2, REQ-C3, REQ-D1, REQ-D2, REQ-D3 | integration | `./scripts/qa.sh lint/format/typecheck/test/boundary` | ✅ | ✅ green |
| Tracer: synthetic month → scored model | 02-01 | REQ-C1..C4, REQ-D1..D3 | unit + integration | `uv run pytest tests/lib/test_tracer_end_to_end.py -q` | ✅ | ✅ green |
| Download pinned 12-month TLC window | 02-02 | REQ-D1 | script + manual invocation | `uv run python scripts/download_tlc_data.py` (network-gated, not in CI) | ✅ | ✅ green (verified in 02-02-SUMMARY.md) |
| Precompute 263-row zone-centroid table | 02-02 | REQ-C2 | script + committed artifact | `uv run python scripts/precompute_zone_centroids.py`; `data/zone_centroids.csv` committed | ✅ | ✅ green |
| Chronological train/test split | 02-03 | REQ-D1, REQ-D2 | unit | `uv run pytest tests/lib/test_train.py -q` | ✅ | ✅ green |
| Fixed LightGBM config, stable categoricals, safe serialization | 02-03 | REQ-D2 | unit | `uv run pytest tests/lib/test_train.py -q` | ✅ | ✅ green |
| RMSE evaluation + alias-based registry | 02-03 | REQ-D3 | unit | `uv run pytest tests/lib/test_evaluate.py tests/lib/test_registry.py -q` | ✅ | ✅ green |
| Chunked read + counted/logged row-quality pre-filter | 02-04 | REQ-C4 | unit | `uv run pytest tests/lib/test_ingest.py -q` | ✅ | ✅ green |
| pandera schema with real Checks | 02-04 | REQ-C1 | unit | `uv run pytest tests/lib/test_schemas.py -q` | ✅ | ✅ green |
| Two-tier gate proven against 12 real months | 02-04 | REQ-C1, REQ-C4 | integration (real cached data) | documented table in 02-04-SUMMARY.md `## Twelve-Month Real-Data Table` | ✅ | ✅ green |
| Vectorized zone-centroid haversine | 02-05 | REQ-C2 | unit | `uv run pytest tests/lib/test_features.py -q` | ✅ | ✅ green |
| NaN-safe dtype downcasting contract | 02-05 | REQ-C3 | unit | `uv run pytest tests/lib/test_features.py -q` | ✅ | ✅ green |
| Benchmark script + README table | 02-05 | REQ-C5 | unit (doc-content, added by Nyquist audit) | `uv run pytest tests/test_readme.py::test_feature_engineering_benchmark_section_contains_a_real_numeric_table -q` | ✅ | ✅ green |
| README drift-window rationale | 02-05 | REQ-D1 | unit (doc-content, added by Nyquist audit) | `uv run pytest tests/test_readme.py::test_dataset_and_drift_window_section_names_pinned_window_and_covid_rationale -q` | ✅ | ✅ green |
| No hyperparameter-tuning framework present | 02-05 (retroactive) | REQ-D2 | unit (absence check, added by Nyquist audit) | `uv run pytest tests/lib/test_train.py::test_no_hyperparameter_tuning_framework_is_declared_or_imported -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No Wave 0 scaffolding was needed — this VALIDATION.md was reconstructed retroactively (State B) after Phase 2 was already fully executed, code-reviewed (`02-REVIEW.md`, 0 blockers), regression-tested (97/97 passing pre-audit), and phase-goal-verified (`02-VERIFICATION.md`, 13/13 must-haves).

---

## Manual-Only Verifications

*All phase behaviors have automated verification.* The two script-driven acquisition steps (`scripts/download_tlc_data.py`, `scripts/precompute_zone_centroids.py`) are network-gated and not re-run in CI on every commit, but their one-time execution is documented with real output in `02-02-SUMMARY.md`, and their internal logic (path-traversal/symlink guards, atomic writes, HTTPS-only host) is covered by the code-review audit (`02-REVIEW.md`) and the security audit (`02-SECURITY.md`), not left as an unverified manual claim.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — infrastructure was already complete)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-23

---

## Validation Audit 2026-08-23

| Metric | Count |
|--------|-------|
| Gaps found | 3 |
| Resolved | 3 |
| Escalated | 0 |

Gaps found (all resolved by the gsd-nyquist-auditor subagent, tests added and verified green):

1. **REQ-C5** — no standing test guarded README's `## Feature Engineering Benchmark` section against silently reverting to prose/placeholder content. Resolved: `tests/test_readme.py::test_feature_engineering_benchmark_section_contains_a_real_numeric_table`.
2. **REQ-D1** — no standing test guarded README's `## Dataset and Drift Window` section naming the pinned 2019-07/2020-06 window and the March-2020 rationale. Resolved: `tests/test_readme.py::test_dataset_and_drift_window_section_names_pinned_window_and_covid_rationale`.
3. **REQ-D2** — no standing test asserted the absence of a hyperparameter-tuning framework (optuna/hyperopt/ray.tune/GridSearchCV/etc.) from dependencies and imports. Resolved: `tests/lib/test_train.py::test_no_hyperparameter_tuning_framework_is_declared_or_imported`.

Full suite after fixes: 100/100 tests passing, `lib` 100% branch coverage maintained, Ruff and `mypy --strict` (scoped to `lib/`) both clean. Committed as `test(phase-02): add Nyquist validation tests`.
