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

Reconciled against the five PLAN.md files created 2026-08-24. Task IDs are `{plan}-T{n}`.

| Task | What it produces | Automated verify | Requirement |
|------|------------------|------------------|-------------|
| 03-01-T1 | Package-legitimacy human gate (blocking-human) | none — checkpoint by design | REQ-B3 (supply chain) |
| 03-01-T2 | `pipeline` extra, `lib/artifacts.py` + `tests/lib/test_artifacts.py` | `scripts/qa.sh lint && format && typecheck && test` | REQ-B8 |
| 03-01-T3 | ingest component, single-task DAG, `tests/pipelines/test_pipeline_compiles.py`, CI matrix + compile job, boundary gate over `pipelines/` | full `qa.sh` chain + `python -m pipelines.compile` | REQ-B2, REQ-B3, REQ-B11 |
| 03-02-T1 | `lib/tracking.py` + tests, `months`/`validate`/`features` components | full `qa.sh` chain | REQ-B2 |
| 03-02-T2 | `merge`/`train`/`evaluate`/`register`/`notify` components | full `qa.sh` chain | REQ-B2, REQ-B9 |
| 03-02-T3 | Full DAG + compile-shape gates | full `qa.sh` chain + `python -m pipelines.compile` | REQ-B4, REQ-B5, REQ-B6, REQ-B7, REQ-B9 |
| 03-03-T1 | README `## Architecture` (mermaid) + `## Cluster Deployment` | heading greps + `scripts/qa.sh test` | REQ-E1 |
| 03-03-T2 | README `## ADRs` + `## Next Steps` | heading greps + ADR count + `scripts/qa.sh test` | REQ-E2, REQ-E3 |
| 03-03-T3 | `tests/test_readme.py` section guards, PROJECT.md decision outcomes | `scripts/qa.sh lint && format && test` | REQ-E1, REQ-E2, REQ-E3 |
| 03-04-T1 | k3d cluster + KFP standalone 2.17.0 + REQ-B1 verification block | `bash deploy/01-cluster-up.sh && bash deploy/02-kfp-install.sh` | REQ-B1 |
| 03-04-T2 | MinIO + MLflow (D-12), Secrets in both namespaces, raw-data upload | `bash deploy/03-storage-tracking.sh && bash deploy/04-upload-raw-data.sh` | REQ-B1 |
| 03-04-T3 | `scripts/submit_pipeline.py`, `scripts/backfill_checksums.py`, first real per-month branch | `python scripts/submit_pipeline.py --start-month 2020-02 --end-month 2020-04` | REQ-B3 (cluster-side pull) |
| 03-05-T1 | Runs A/B/C + edge runs; README REQ-B4/B7 evidence | evidence-section greps + `scripts/qa.sh test` | REQ-B4, REQ-B7 |
| 03-05-T2 | Run D; README REQ-B8 checksum table and REQ-B10 cache record | `python scripts/backfill_checksums.py` + digest count grep + `scripts/qa.sh test` | REQ-B8, REQ-B10 |
| 03-05-T3 | Run E; README REQ-B9 exit-path evidence; evidence-section guard; traceability closure | full `qa.sh` chain | REQ-B9 |

**Sampling continuity:** every task except the 03-01-T1 checkpoint carries an automated verify, so there is never a run of three consecutive tasks without machine feedback.

The interim **Requirements → Test Map** below is retained from `03-RESEARCH.md`'s Validation Architecture section; the Wave 0 gaps it lists are now assigned to concrete tasks (see Wave 0 Requirements below).

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

Each gap is now owned by a named task; none is left unassigned.

- [ ] `tests/pipelines/__init__.py` + `tests/pipelines/test_pipeline_compiles.py` — **owned by 03-01-T3** (created with the REQ-B2/B3/B4 assertions) and **extended by 03-02-T3** (REQ-B5 parallelism cap, REQ-B6 `dsl.Collected`, REQ-B7 condition group, REQ-B9 exit-handler group, plus a per-executor memory-limit assertion covering PITFALLS.md Pitfall 2). `research/ARCHITECTURE.md`'s Recommended Project Structure already anticipated `tests/pipelines/` but it was never created, since no `pipelines/` code existed until this phase.
- [ ] A runtime-dependency-install absence gate — **owned by 03-01-T3**, satisfied both ways: `scripts/check_component_boundary.sh` is extended to scan `pipelines/` alongside `components/` (the repo's existing mechanical-gate pattern, per RESEARCH.md's own recommendation), and the compile test adds a source scan that reads the forbidden literal out of that script rather than retyping it, so the two gates cannot drift apart.
- [ ] Extend `tests/test_readme.py` for the new README sections — **owned by 03-03-T3** (REQ-E1/E2/E3, plus a heading-aliasing guard against the pre-existing `## Architectural Contract` section) and **03-05-T3** (the `## Pipeline Run Evidence` guard). Additive only; the existing `_section_body` helper is reused, never duplicated.
- [ ] The deterministic output-key module's unit tests — **owned by 03-01-T2**. The planner's design choice supersedes the `lib/paths.py::artifact_key` naming `03-PATTERNS.md` proposed: the key lives in `lib/artifacts.py` alongside the path-level adapters that use it, paired with `tests/lib/test_artifacts.py`, which is what satisfies the existing `--cov-fail-under=100` gate. A second module for one function was not worth the file.
- [ ] Framework install: none — pytest and pytest-cov are already installed via the `dev` extra. 03-01-T2 adds `--extra pipeline` to `scripts/qa.sh` and CI so the compile tests can import `kfp`.

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
