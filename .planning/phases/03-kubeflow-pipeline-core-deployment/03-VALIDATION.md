---
phase: 3
slug: kubeflow-pipeline-core-deployment
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-24
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.x (`pyproject.toml` `dev` extra, `pytest~=9.1.0` — already installed, no new framework needed) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `--cov=lib --cov-fail-under=100`) — unchanged |
| **Quick run command** | `scripts/qa.sh test` |
| **Full suite command** | `scripts/qa.sh lint && scripts/qa.sh typecheck && scripts/qa.sh test && scripts/qa.sh boundary` |
| **Estimated runtime** | ~10-15 seconds for `scripts/qa.sh test` (static/compile-time checks only, no cluster) |

---

## Sampling Rate

- **After every task commit:** Run `scripts/qa.sh test` — covers all static/compile-time checks (typed-artifact shape, `packages_to_install` absence, DAG compile, `parallelism` cap, `dsl.Collected` presence, exit-handler group presence, README section presence)
- **After every plan wave:** Run `scripts/qa.sh lint && scripts/qa.sh typecheck && scripts/qa.sh test && scripts/qa.sh boundary` (existing full local gate)
- **Before `/gsd-verify-work`:** Full suite must be green, plus the manual-only cluster checkpoints below each documented in README with concrete evidence (checksums, run IDs, log excerpts)
- **Max feedback latency:** ~15 seconds (static suite); manual cluster checkpoints are inherently slower and out of the fast-feedback loop by design

---

## Per-Task Verification Map

*Not yet populated — Phase 3 has no PLAN.md files yet (plan-phase step 5.5 runs before the planner).* The table below is the interim **Requirements → Test Map** from `03-RESEARCH.md`'s Validation Architecture section; `/gsd-validate-phase 3` (or a future planning pass) reconciles it against actual task IDs once `PLAN.md` exists.

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|--------------|----------|-----------|---------------------|--------------|
| REQ-B2 | Every component signature uses typed artifact params, no raw string paths | static/compile | `scripts/qa.sh test` (new: `tests/pipelines/test_pipeline_compiles.py` inspecting `components/*/component.py` annotations) | ❌ Wave 0 |
| REQ-B3 | No `packages_to_install` anywhere in `components/`/`pipelines/` | static | `grep -rn "packages_to_install" components/ pipelines/` (new assert-empty pytest test, mirrors `check_component_boundary.sh`'s pattern) | ❌ Wave 0 |
| REQ-B4 | Full DAG compiles without error | compile (automated) | `tests/pipelines/test_pipeline_compiles.py::test_train_pipeline_compiles` via `kfp.compiler.Compiler().compile(...)` | ❌ Wave 0 |
| REQ-B4 | A real run reaches `register` or a documented skip-branch | manual-only | N/A — requires k3d + KFP + GHCR images + real TLC data; documented in README with KFP run-UI evidence | N/A |
| REQ-B5 | `parallelism` cap present in compiled IR YAML | static (automated) | `test_pipeline_compiles.py::test_parallel_for_capped` parses the compiled YAML for the `parallelism` field | ❌ Wave 0 |
| REQ-B6 | `dsl.Collected` used, not manual artifact stitching | static (automated) | Extends the same compile test: source-inspects `pipelines/train_pipeline.py` for `dsl.Collected(` | ❌ Wave 0 |
| REQ-B7 | Deliberately-worse model not registered; better model is | manual-only | N/A — requires two real cluster runs with different model quality; documented in README with MLflow UI/registry evidence | N/A |
| REQ-B8 | Two identical backfill runs (2-3 month subset, per D-13) produce byte-identical output | manual-only (cluster) + unit (if a deterministic-key function lands in `lib/`) | If a deterministic output-key function is added (e.g. `lib/paths.py::artifact_key(month)`), it gets a `tests/lib/test_paths.py` unit test per this repo's 100%-`lib/`-coverage convention; the byte-diff itself is manual/cluster | ❌ Wave 0 (conditional on planner's design) |
| REQ-B9 | `ExitHandler` triggers on both success and failure (per D-11, minimal log line; note: exit task cannot consume wrapped tasks' outputs — limited to `PipelineTaskFinalStatus` fields) | static (compile) + manual (cluster) | Compile test asserts the compiled YAML contains an exit-handler group structure; manual: a deliberately-failed run's log evidence in README | ❌ Wave 0 (static half) |
| REQ-B10 | Cache invalidation demonstrated with a documented input change | manual-only | N/A — requires two real cluster runs; documented in README with the specific input diff and cache-key diff | N/A |
| REQ-B11 | Compiled YAML attached as CI release artifact | CI-verified, not pytest | New CI job (or release workflow) running `kfp.compiler.Compiler().compile(...)` and uploading the YAML — verified by a green CI run producing a downloadable artifact | N/A (CI config, not test file) |
| REQ-E1/E2/E3 | README sections (architecture diagram, ADRs, Next Steps) present and non-empty | static (automated) | Extends `tests/test_readme.py`'s existing `_section_body` helper with assertions for `## Architecture`, `## ADRs` (or equivalent), `## Next Steps` | ❌ Wave 0 (extends existing file) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/pipelines/__init__.py` + `tests/pipelines/test_pipeline_compiles.py` — covers REQ-B2 (typed-artifact static check), REQ-B4 (compile succeeds), REQ-B5 (parallelism cap present), REQ-B6 (`dsl.Collected` present), REQ-B9 (exit-handler group present). `research/ARCHITECTURE.md`'s Recommended Project Structure already anticipated `tests/pipelines/` but it was never created (no `pipelines/` code existed until this phase).
- [ ] A `packages_to_install`-absence static test — new pytest test or extension of `scripts/check_component_boundary.sh` (more consistent with this repo's existing mechanical-gate pattern).
- [ ] Extend `tests/test_readme.py` with assertions for the three new required README sections (REQ-E1/E2/E3) — file and `_section_body` helper already exist; additive only.
- [ ] Conditional: if the planner designs a dedicated `lib/` function for the deterministic output-key strategy, it needs its own `tests/lib/test_<module>.py` file to satisfy the existing `--cov-fail-under=100` gate.
- [ ] Framework install: none — pytest/pytest-cov already installed via the `dev` extra.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A real pipeline run reaches `register` or a documented skip-branch | REQ-B4 | Requires a live k3d + KFP + GHCR-hosted images + real TLC data — no static test can prove a real run happened | Run the compiled pipeline on the cluster; capture the KFP run UI's final task status in README |
| Deliberately-worse model not registered; genuinely-better model is | REQ-B7 | Requires two real cluster runs with different model quality and a live MLflow registry to observe the promotion decision | Run the pipeline twice with a deliberately-degraded and a normal model; document both outcomes with MLflow UI/registry evidence in README |
| Two identical backfill runs (2-3 month subset) produce byte-identical output | REQ-B8 | Requires two real cluster runs and a file-level checksum comparison of the resulting artifacts | Run the same `start_month`/`end_month` backfill twice on the cluster; `sha256sum` the resulting Parquet/model artifacts and document the matching checksums in README |
| A deliberately-failed run still triggers the `ExitHandler` cleanup/notification task | REQ-B9 | Requires an actual failure injected into a live cluster run to observe the exit-path log line | Force a task failure (e.g. a bad input) in a real run; capture the notify task's log line in README |
| Cache invalidation demonstrated with a documented input change | REQ-B10 | Requires two real cluster runs (cache hit, then cache miss after a deliberate input change) | Run the pipeline twice unchanged (cache hit), then change one documented input and re-run (cache miss); document the specific change and resulting cache-key diff in README |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending — finalized by `/gsd-validate-phase 3` after execution, per this project's established Phase 2 pattern.
