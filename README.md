# nyc-trip-duration-kfp

A batch ML training pipeline on Kubeflow Pipelines v2, predicting NYC TLC trip duration (LightGBM regression) from monthly taxi trip records — built to demonstrate production-grade pipeline engineering (typed artifacts, custom component images, conditional model promotion, provable idempotent backfill), not to chase modeling accuracy.

## Status

**Phase 1 (repo foundation and CI quality gates) is complete.** `lib/` currently contains only the month-range utility used to enumerate a backfill window (`lib/months.py`) — this proves the quality-gate stack (lint, type-check, test, boundary gate, CI, pre-commit) end-to-end on the smallest possible real surface. The pandas/numpy feature engineering, schema validation, and LightGBM training logic land in Phase 2. The Kubeflow Pipelines DAG, k3d cluster, MinIO, and MLflow integration land in Phase 3. Do not mistake the current tree for the finished project — see `.planning/ROADMAP.md` for the full plan.

## Quick Start

```
uv sync --extra dev
```

This repository's Python work targets the venv at `path/to/venv` (per `CLAUDE.MD`), resolved via `UV_PROJECT_ENVIRONMENT`. `scripts/qa.sh` resolves this from the script's own location on disk, not from the caller's working directory, so every command below works identically whether you run it from the repo root, `lib/`, or `components/ingest/`.

Five local commands cover every quality gate:

```
scripts/qa.sh lint        # ruff check .
scripts/qa.sh format      # ruff format --check .
scripts/qa.sh typecheck   # mypy --strict lib
scripts/qa.sh test        # pytest
scripts/qa.sh boundary    # scripts/check_component_boundary.sh
```

Every `uv` call inside the script passes `--extra dev` (and `--frozen` under CI). A hand-run bare `uv run <tool>` implicitly syncs the default dependency set first, which uninstalls ruff/mypy/pytest from the venv as a side effect of running them — always use `scripts/qa.sh` rather than invoking `uv run` directly.

## Repository Layout

```
lib/          100%-unit-tested pandas/numpy/modeling logic, zero KFP imports
components/   thin KFP component wrappers — one dir per pipeline stage, each its own image
pipelines/    @dsl.pipeline DAG definitions, compiled to YAML
serving/      out of scope for this milestone (KServe deployment — deferred)
dashboard/    out of scope for this milestone (monitoring UI — deferred)
tests/        pytest suite, mirrors lib/
```

## Architectural Contract: Thin Component, Fat Lib

`lib/` holds 100% of the pandas and feature logic and imports nothing from KFP. A `components/` module parses its inputs, calls exactly one `lib` function, and writes its outputs — nothing else. This is enforced mechanically, not by review discipline: `scripts/check_component_boundary.sh` runs in both CI (as a step of the `lint` job) and every pre-commit run, and rejects three violation classes inside `components/`:

1. A `pandas` or `numpy` import (plain, dotted-submodule, or `from`-import form).
2. A DataFrame-shaped method call (`.groupby(`, `.merge(`, `.pivot(`, `.resample(`, `.apply(`, `.assign(`, `.astype(`, `.read_parquet(`, `.to_parquet(`, `.read_csv(`, `.to_csv(`).
3. A `packages_to_install` KFP decorator argument — component dependencies come from the CI-built image, never a pip install at pod start.

The gate also refuses to pass vacuously: if its scan of `components/` finds zero tracked Python modules, it exits non-zero rather than silently reporting success.

## CI

`.github/workflows/ci.yml` runs on every pull request (per D-01), as four jobs in a strict dependency chain: `lint` → `typecheck` → `test` → `build-push`. A failure at any stage prevents the image from being built — a broken `lib/` change never reaches GHCR. On a clean PR, `build-push` tags the built image with the full 40-character SHA of the source commit that built it (the pull request's head commit on a PR run) and pushes to:

```
ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:<commit-sha>
```

Images are never tagged with a mutable tag like `:latest`.

## Repository and Package Visibility (D-05)

This repository and its GHCR packages are **public**. Rationale: it matches the project's portfolio purpose (interview-legible, clonable by anyone reviewing it), and it means Phase 3's k3d cluster needs zero registry-credential wiring to pull component images — no `imagePullSecrets` Secret to provision, no PAT to rotate.

Tradeoff: a real employer repository handling proprietary code would instead use a **private** GHCR package, and the cluster would need a `kubectl create secret docker-registry` pull secret referenced via `imagePullSecrets` on the pipeline's service account. That extra plumbing is intentionally skipped here because there is no sensitive code or data in this mock project — it would be the correct default for production use, not this one.

## Full Plan

See `.planning/ROADMAP.md` for the phase-by-phase plan and `.planning/REQUIREMENTS.md` for the full requirements traceability table.
