# Phase 3: Kubeflow Pipeline Core & Deployment - Pattern Map

**Mapped:** 2026-08-24
**Files analyzed:** 17 (7 components, 1 pipeline, 1 pipeline-compile test, 1 boundary-gate extension, 1 CI workflow edit, 1 README, 3 ADRs, 1 lib deterministic-key module + test, deployment manifests/scripts)
**Analogs found:** 15 / 17 (2 have no in-repo analog — new infra/deployment surface)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|----------------|
| `components/ingest/main.py` (extended) | component (CLI wrapper) | request-response (batch, single-invocation) | itself (`components/ingest/main.py`, current tracer form) | exact — extend in place |
| `components/validate/main.py` | component (CLI wrapper) | request-response / CRUD (reads artifact, writes typed artifact) | `components/ingest/main.py` + `lib/schemas.py::validate_trips` | role-match |
| `components/features/main.py` | component (CLI wrapper) | request-response / transform | `components/ingest/main.py` + `lib/features.py::build_features` | role-match |
| `components/merge/main.py` | component (CLI wrapper) | request-response / fan-in aggregation | `components/ingest/main.py` (thin-wrapper shape only — no direct fan-in analog exists) | partial |
| `components/train/main.py` | component (CLI wrapper) | request-response / CRUD (writes model artifact) | `components/ingest/main.py` + `lib/train.py::train_trip_duration_model`/`save_model` | role-match |
| `components/evaluate/main.py` | component (CLI wrapper) | request-response / CRUD | `components/ingest/main.py` + `lib/evaluate.py::evaluate_model` | role-match |
| `components/register/main.py` | component (CLI wrapper) | event-driven (conditional promotion via `dsl.If`) | `components/ingest/main.py` + `lib/registry.py::ModelRegistry` (first real `MlflowClient` injection) | role-match |
| `components/notify/main.py` | component (CLI wrapper) | event-driven (ExitHandler, log-only) | `components/ingest/main.py` (thin shape) + RESEARCH.md Code Examples' `notify()` pattern | partial (no in-repo exit-handler analog; RESEARCH.md supplies the exact snippet) |
| `pipelines/train_pipeline.py` | pipeline / orchestration | event-driven DAG (ParallelFor + Collected + If + ExitHandler) | none in-repo (`pipelines/.gitkeep` only) — RESEARCH.md Code Examples is the analog | no analog (external) |
| `lib/paths.py` (conditional — deterministic output key, Pattern 5) | utility / model | CRUD (pure function, content-addressed key) | `lib/months.py` (small, pure, single-purpose utility module) | role-match |
| `tests/lib/test_paths.py` (conditional, pairs with `lib/paths.py`) | test | — | `tests/lib/test_months.py` | exact |
| `tests/pipelines/__init__.py` + `tests/pipelines/test_pipeline_compiles.py` | test (static/compile) | — | `tests/lib/test_registry.py` (mocked-boundary style) + `tests/test_readme.py` (regression-guard style) | role-match |
| `scripts/check_component_boundary.sh` (extended: `packages_to_install` check already exists; extend scan or add sibling assertion for typed-artifact params) | utility (CI gate script) | static analysis | itself | exact — extend in place |
| `.github/workflows/ci.yml` (extended: new build-push jobs per component image + compile+upload-YAML release job) | config (CI workflow) | event-driven (CI trigger) | itself (`build-push` job for `ingest`) | exact — replicate pattern per component |
| `README.md` (extended: Architecture, ADRs, Next Steps sections) | doc | — | itself (`## Feature Engineering Benchmark`, `## Dataset and Drift Window` sections, guarded by `tests/test_readme.py`) | exact — replicate section+test pattern |
| `.planning/.../ADR-*.md` or README `## ADRs` section (4 ADRs: D-10/D-11/D-12/D-13) | doc | — | none in-repo (no prior ADR files) — CONTEXT.md's Decisions section is the content source | no analog (content-source, not code) |
| Helm/deploy scripts (`deploy/mlflow-values.yaml`, `deploy/minio-values.yaml`, `deploy/k3d-cluster.sh` or similar) | config / infra | batch (one-shot cluster bring-up) | none in-repo (net-new infra surface) — RESEARCH.md Code Examples (`helm install mlflow ...`, `helm install minio ...`) is the analog | no analog (external, RESEARCH.md-sourced) |

## Pattern Assignments

### `components/validate/main.py`, `components/features/main.py`, `components/train/main.py`, `components/evaluate/main.py`, `components/register/main.py` (component, request-response/CRUD)

**Analog:** `components/ingest/main.py` (full file, 27 lines — read above)

**Core shape to copy** (all 27 lines are the pattern — this file is the entire analog):
```python
"""Thin CLI wrapper around lib.months.month_range."""

import argparse
import sys

from lib.months import month_range


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the inclusive month range.")
    parser.add_argument("--start-month", required=True, help="YYYY-MM")
    parser.add_argument("--end-month", required=True, help="YYYY-MM")
    args = parser.parse_args()

    try:
        months = month_range(args.start_month, args.end_month)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for month in months:
        print(month)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**What to carry forward into every new component:**
- Module docstring: one line, "Thin CLI wrapper around `lib.<module>.<function>`."
- `argparse` for all inputs — KFP v2's `@dsl.container_component`/`ContainerSpec` pattern (per ARCHITECTURE.md Pattern 2, Claude's Discretion) passes typed artifact `.path` values and scalar params as CLI flags; this file's `--start-month`/`--end-month` flags are the exact shape to replicate for e.g. `--input-path`, `--output-path`, `--month`.
- `try/except ValueError` around the one `lib` call, printing to `stderr` and returning `1` — this is the component's entire error-handling contract. `lib/ingest.py::load_month` raises `FileNotFoundError`, `lib/train.py::chronological_split` raises `ValueError`, `lib/features.py::build_features` raises `ValueError` — each new component's `except` clause must name the specific exception type(s) its wrapped `lib` call actually raises (do not blanket-catch `Exception`; let anything unexpected propagate as a loud pod failure, per RESEARCH.md's Security Domain "let it propagate" guidance and `PITFALLS.md` Pitfall 8 in spirit).
- `raise SystemExit(main())` entrypoint idiom — keep identical.
- **Boundary constraint (mandatory):** the wrapper body must never call pandas/numpy directly or contain `.groupby/.merge/.astype/.read_parquet/...` — `scripts/check_component_boundary.sh` mechanically enforces this (see Shared Patterns below). Read/write artifact bytes only via the one `lib` function call; typed-artifact I/O (`Output[Dataset].path`, `Input[Dataset].path`) is the only extra glue beyond what `components/ingest/main.py` already shows.

**Per-file `lib` call to wrap:**
| Component | `lib` function | Exception(s) to catch |
|---|---|---|
| `validate` | `lib.schemas.validate_trips` | `pandera` `SchemaError`(s) — check `lib/schemas.py` for exact type raised |
| `features` | `lib.features.build_features` | `ValueError` (unmapped zone ids) |
| `train` | `lib.train.chronological_split` + `lib.train.train_trip_duration_model` + `lib.train.save_model` | `ValueError` (empty split) |
| `evaluate` | `lib.evaluate.evaluate_model` (+ `lib.train.load_booster`) | `FileNotFoundError` (missing model) |
| `register` | `lib.registry.ModelRegistry` (first real `MlflowClient`, not a mock) + `lib.evaluate.beats_champion` | `mlflow.exceptions.MlflowException` |

---

### `components/notify/main.py` (component, event-driven, ExitHandler exit task)

**Analog:** RESEARCH.md's Code Examples section (no in-repo analog — this is the first exit-handler component in the repo), combined with `components/ingest/main.py`'s thin-CLI shape for the file/Dockerfile structure.

**Core pattern** (RESEARCH.md lines 227-256, reproduced exactly — this is what the executor must implement, adapted from `@dsl.component` in-process form to this repo's CLI-wrapper/container-component convention):
```python
from kfp import dsl
from kfp.dsl import PipelineTaskFinalStatus


@dsl.component(base_image="ghcr.io/ORG/REPO/notify:latest")
def notify(status: PipelineTaskFinalStatus) -> None:
    # D-11: a single structured log line - no artifact file, no external call.
    # RMSE is deliberately absent: evaluate runs inside the ExitHandler's own
    # scope, so its output cannot be threaded into this exit task (Pitfall 11).
    print(
        f"run_status={status.state} "
        f"run_id={status.pipeline_job_resource_name} "
        f"failed_task={status.pipeline_task_name or ''} "
        f"error_code={status.error_code or ''} "
        f"error_message={status.error_message or ''}"
    )
```

**Load-bearing constraint (do not violate):** `notify_task = notify()` must be constructed *before* the `with dsl.ExitHandler(...)` block in `pipelines/train_pipeline.py` — it cannot consume `.outputs[...]` from any task defined inside that block (RESEARCH.md Pitfall 11 / `kubeflow/pipelines#10187`). Do not attempt to pass `evaluate_task.outputs['rmse']` into `notify`.

**Security note (apply from Shared Patterns):** never print `AWS_SECRET_ACCESS_KEY`/MinIO credentials/an MLflow tracking URI with embedded auth in this log line.

---

### `pipelines/train_pipeline.py` (pipeline, event-driven DAG orchestration)

**Analog:** No in-repo file exists yet (`pipelines/.gitkeep` only). Analog is RESEARCH.md's Code Examples ExitHandler skeleton (lines 227-256) plus `ARCHITECTURE.md` Patterns 1-4 (not reproduced in RESEARCH.md, must be read directly by the planner/executor).

**Skeleton to build from** (RESEARCH.md lines 249-256):
```python
@dsl.pipeline
def train_pipeline(months: list, start_month: str, end_month: str, parallelism: int = 2):
    notify_task = notify()  # constructed before the with-block, per SDK requirement
    with dsl.ExitHandler(exit_task=notify_task):
        with dsl.ParallelFor(months, parallelism=parallelism) as month:
            ingest_task = ingest(month=month)
            # ... validate, features, merge, train, evaluate, dsl.If(...) as in ARCHITECTURE.md Pattern 3/4
```

**Required elements per CONTEXT.md/RESEARCH.md:**
- `dsl.ParallelFor(months, parallelism=<2 or 3>)` — cap enforced as a literal int, verifiable in compiled YAML by `tests/pipelines/test_pipeline_compiles.py::test_parallel_for_capped`.
- `dsl.Collected` for fan-in before `merge`/`train` (REQ-B6) — no manual artifact-list stitching.
- `dsl.If(rmse < champion_rmse, ...)` — both directions must be exercised at runtime (manual cluster checkpoint, not compile-time).
- Every task references `base_image=`/`ContainerSpec(image=...)` pointing at a GHCR SHA-tagged image (mirroring `.github/workflows/ci.yml`'s `IMAGE_TAG` scheme) — never `packages_to_install`.
- Typed artifacts only (`Input[Dataset]`, `Output[Dataset]`, `Output[Model]`, `Output[Metrics]`) — no raw string path params between tasks.

---

### `lib/paths.py` (conditional, utility/model — deterministic output key, Pattern 5) + `tests/lib/test_paths.py`

**Analog:** `lib/months.py` (full file, 34 lines — read above) for module shape/style; `tests/lib/test_months.py` for the paired test file.

**Style to copy from `lib/months.py`:**
- Terse one-line module docstring.
- Small, pure, single-purpose functions with no side effects; regex/deterministic-string construction pattern (`_parse_month`, `month_range`) is the model for a `artifact_key(month: str) -> str` function.
- Raises `ValueError` with an f-string naming the offending value — same error-handling idiom used throughout `lib/` (`lib/train.py::chronological_split`, `lib/features.py::build_features`).
- **Mandatory:** any new `lib/` function needs a paired `tests/lib/test_<module>.py` to satisfy `pyproject.toml`'s `--cov-fail-under=100` gate (`[tool.pytest.ini_options]` addopts) — do not add `lib/paths.py` without `tests/lib/test_paths.py` in the same commit.

---

### `tests/pipelines/test_pipeline_compiles.py` + `tests/pipelines/__init__.py` (test, static/compile)

**Analog:** `tests/test_readme.py` (full file, 41 lines — read above) for the "regression-guard test file with small pure helper functions" style; `tests/lib/test_registry.py` for the "assert on a mocked/constructed object's shape" style.

**Pattern to copy from `tests/test_readme.py`:**
```python
from pathlib import Path

README_PATH = Path(__file__).resolve().parent.parent / "README.md"


def _section_body(readme_text: str, heading: str) -> str:
    """Return the text between `heading` and the next '## ' heading (exclusive)."""
    start = readme_text.index(heading)
    rest = readme_text[start + len(heading) :]
    next_heading_idx = rest.find("\n## ")
    body = rest if next_heading_idx == -1 else rest[:next_heading_idx]
    return body
```
Apply the same "one small helper + several `test_*` assertions reading a real artifact" shape to the compiled pipeline: compile `pipelines/train_pipeline.py` via `kfp.compiler.Compiler().compile(...)` to a temp path once (module-level fixture or helper), then assert on the resulting YAML/IR dict for: typed-artifact params (REQ-B2), successful compile (REQ-B4), `parallelism` field present and ≤3 (REQ-B5), `dsl.Collected` used (REQ-B6, source-inspect `pipelines/train_pipeline.py` directly — `grep`/`inspect` style, no need to parse compiled YAML for this one), exit-handler group present (REQ-B9).

**Extend `tests/test_readme.py` itself** (not a new file) for REQ-E1/E2/E3 — add `test_architecture_section_exists`, `test_adr_section_exists`, `test_next_steps_section_exists` following the exact `_section_body` + assertion pattern already shown above (lines 24-40 of that file are the two existing examples to clone).

---

### `.github/workflows/ci.yml` (config, extend `build-push` job)

**Analog:** itself — the existing `build-push` job (lines 46-76, read above).

**Pattern to replicate per new component image** (`validate`, `features`, `merge`, `train`, `evaluate`, `register`, `notify`):
```yaml
  build-push:
    needs: [lint, typecheck, test]
    if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    env:
      IMAGE_TAG: ${{ github.event.pull_request.head.sha || github.sha }}
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - name: Set lowercase repository path
        run: echo "REPO_LC=$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')" >> "$GITHUB_ENV"
      - uses: docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c # v4
      - uses: docker/login-action@dbcb813823bdd20940b903addbd779551569679f # v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a # v7
        with:
          context: .
          file: components/ingest/Dockerfile
          push: true
          tags: ghcr.io/${{ env.REPO_LC }}/ingest:${{ env.IMAGE_TAG }}
          build-args: |
            SOURCE=https://github.com/${{ github.repository }}
            REVISION=${{ env.IMAGE_TAG }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```
Either (a) duplicate this job per component with `file:`/`tags:` swapped to `components/<name>/Dockerfile` and `ghcr.io/.../<name>:${IMAGE_TAG}`, or (b) convert to a matrix strategy (`strategy: matrix: component: [ingest, validate, features, merge, train, evaluate, register, notify]`) — planner's call, but the pinned-SHA action versions and `SOURCE`/`REVISION` build-args must be preserved for every image. Add a new job (e.g. `compile-pipeline`, `needs: [test]`) that runs `kfp.compiler.Compiler().compile(...)` and uploads the resulting YAML via `actions/upload-artifact` (or attaches it to a GitHub Release) for REQ-B11 — no existing analog for this job shape in-repo; it is new CI surface, not a copy of `build-push`.

---

### `components/<name>/Dockerfile` (all new components)

**Analog:** `components/ingest/Dockerfile` (full file, 13 lines — read above).

```dockerfile
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ARG SOURCE=""
ARG REVISION=""
LABEL org.opencontainers.image.source=${SOURCE}
LABEL org.opencontainers.image.revision=${REVISION}

WORKDIR /app
COPY lib/ /app/lib/
COPY components/ingest/main.py /app/main.py
ENV PYTHONPATH=/app

ENTRYPOINT ["python", "/app/main.py"]
```
Copy verbatim, swapping only `COPY components/ingest/main.py` -> `COPY components/<name>/main.py`. Components needing `ml` extras (pandas/pandera/lightgbm/mlflow — i.e. every component except the pure-CLI ones) must also `RUN pip install` (or copy a built wheel/`uv export`) the pinned `ml` dependency group inside the image at build time — **never** `packages_to_install` at runtime (mechanically forbidden by `scripts/check_component_boundary.sh` Step 3(c) and REQ-B3). Same pinned base-image digest for reproducibility across all component images.

---

### `scripts/check_component_boundary.sh` (utility, extend or verify unchanged)

**Analog:** itself (full file, 83 lines — read above). No change strictly required — Phase 3 only adds more files under `components/`, which the existing `git ls-files -- "components/*.py" "components/**/*.py"` scan (line 14) already picks up automatically. Confirm this stays true: every new `components/<name>/main.py` must pass Step 3(a) (no pandas/numpy import), Step 3(b) (no DataFrame-shaped method calls), Step 3(c) (no `packages_to_install`) unchanged. If `pipelines/train_pipeline.py` needs a similar mechanical check (e.g. no `packages_to_install` in `pipelines/` too), extend `SCAN_PATH` handling or add a sibling grep — RESEARCH.md's Wave 0 Gaps calls out a `packages_to_install`-absence static test as either extending this script or a new pytest test; extending this script is "more consistent with this repo's existing... pattern" per RESEARCH.md's own recommendation.

---

## Shared Patterns

### Thin-component/fat-lib boundary
**Source:** `components/ingest/main.py` (whole file) + `scripts/check_component_boundary.sh`
**Apply to:** every file under `components/`
Component bodies do argparse + one `lib` call + typed-artifact path glue + a narrow `try/except <SpecificError>` — nothing else. Mechanically enforced; do not hand-wave this.

### Error handling
**Source:** `components/ingest/main.py` lines 15-19; `lib/train.py::chronological_split` (raises `ValueError` with descriptive f-string); `lib/ingest.py::load_month` (raises `FileNotFoundError` with descriptive f-string)
**Apply to:** all `components/*/main.py`, `lib/paths.py`
Catch the *specific* exception type each wrapped `lib` function raises, print to `stderr`, return `1`. Let anything else propagate uncaught (a loud pod failure) — never a blanket `except Exception`.

### MLflow alias-based registry access
**Source:** `lib/registry.py` (whole file, 47 lines)
**Apply to:** `components/register/main.py`
`ModelRegistry(client, model_name)` wraps a real `MlflowClient` for the first time in Phase 3 (Phase 2 only used a `MagicMock`, see `tests/lib/test_registry.py`). Never use MLflow's deprecated numeric-stage API — only `get_champion_rmse`, `tag_version_rmse`, `set_candidate`, `promote_to_champion`.

### Test-and-code pairing / 100% lib coverage
**Source:** `pyproject.toml` `[tool.pytest.ini_options]` (`--cov=lib --cov-fail-under=100`) + `tests/lib/test_months.py` / `tests/lib/test_registry.py` pairing convention
**Apply to:** any new `lib/*.py` file (conditionally, `lib/paths.py`)
Every `lib/` module needs a same-named `tests/lib/test_<module>.py` in the same change, or CI's `test` job fails on coverage.

### README regression-guard sections
**Source:** `tests/test_readme.py` (whole file)
**Apply to:** README.md's new `## Architecture`, `## ADRs`, `## Next Steps` sections (REQ-E1/E2/E3)
Add one `test_*` function per new section reusing the existing `_section_body` helper — do not write a second helper.

### CI job wiring / pinned-SHA GitHub Actions
**Source:** `.github/workflows/ci.yml` `build-push` job
**Apply to:** all new component-image build jobs, the new compile+release job
Reuse the exact pinned action SHAs (`actions/checkout@11d5960...`, `docker/setup-buildx-action@bb05f3f...`, `docker/login-action@dbcb8138...`, `docker/build-push-action@53b7df9...`) already in the file — do not introduce floating `@v4`/`@latest` tags for a new job.

### Secrets via K8s Secret, never literal
**Source:** RESEARCH.md Security Domain (V6) — no in-repo code analog exists yet (first phase touching real credentials)
**Apply to:** MLflow Helm values, MinIO Helm values, `components/register/main.py` (MLflow tracking URI/credentials), `components/notify/main.py` (log line must never print a credential)
`kubectl create secret generic ...` + `env[].valueFrom.secretKeyRef` in Helm `--set` invocations (see RESEARCH.md Code Examples) — never a literal credential in a component, Dockerfile, manifest, or Helm `--set` history.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `pipelines/train_pipeline.py` | pipeline/orchestration | event-driven DAG | First pipeline file in the repo (`pipelines/.gitkeep` placeholder only) — use RESEARCH.md's Code Examples section + `ARCHITECTURE.md` Patterns 1-4 directly, not an in-repo analog |
| Helm value files / cluster bring-up scripts (`deploy/*.yaml`, k3d install commands) | config/infra | batch (one-shot) | No prior infra-as-config exists in this repo (Phase 1/2 were pure Python/CI) — RESEARCH.md's Code Examples (MLflow chart install, MinIO chart install) and STACK.md's Installation section are the sole source; follow those directly |

## Metadata

**Analog search scope:** `components/`, `lib/`, `tests/`, `scripts/`, `.github/workflows/`, `pyproject.toml`, `README.md` (repo root, excluding `.git`, `.claude`, `.planning`, `.mypy_cache`, `.ruff_cache`, `data/`, `path/`)
**Files scanned:** ~30 tracked source/test/config files directly read or grep-inspected this session
**Pattern extraction date:** 2026-08-24
