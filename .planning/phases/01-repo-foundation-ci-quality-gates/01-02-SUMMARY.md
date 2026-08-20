---
phase: 01-repo-foundation-ci-quality-gates
plan: 02
subsystem: quality-gates
tags: [pre-commit, ruff, mypy, pytest, github-actions, boundary-gate]
dependency graph:
  requires:
    - lib.months.month_range (01-01)
    - components/ingest/main.py thin-wrapper pattern (01-01)
    - .github/workflows/ci.yml lint->typecheck->test->build-push chain (01-01)
  provides:
    - scripts/qa.sh (lint|format|typecheck|test|boundary subcommands)
    - scripts/check_component_boundary.sh (REQ-A6 mechanical gate)
    - .pre-commit-config.yaml (five repo:local hooks, D-03a)
    - README.md
  affects:
    - 01-03 (proves the gates fire — asserts parity against these exact subcommand names and hook ids)
    - Phase 2/3 (every future task runs scripts/qa.sh <subcommand> rather than raw tool invocations)
tech-stack:
  added: [pre-commit 4.6.2]
  patterns: ["shared qa.sh entrypoint (single source of truth for CI + pre-commit)", "repo:local pre-commit hooks (no third-party mirrors)", "mechanical architectural boundary gate (grep-based, non-vacuous)"]
key-files:
  created:
    - scripts/qa.sh
    - scripts/check_component_boundary.sh
    - .pre-commit-config.yaml
    - README.md
  modified:
    - .github/workflows/ci.yml
    - pyproject.toml
    - uv.lock
decisions:
  - "scripts/qa.sh resolves REPO_ROOT from its own script path (BASH_SOURCE) and cd's there before running anything, so invocation from any subdirectory (lib/, components/ingest/) produces the identical verdict as invocation from the repo root."
  - "Under CI, scripts/qa.sh deliberately leaves UV_PROJECT_ENVIRONMENT unset (letting the runner's own uv-synced environment, already created by the workflow's uv sync --frozen --extra dev step, do the work) rather than trying to reuse path/to/venv, which does not exist on the runner."
  - "check_component_boundary.sh scans only git-tracked *.py files under components/ (git ls-files), so an untracked scratch file can never fail the gate and a deleted file never lingers in the scan set."
  - "The boundary gate's non-vacuous guard runs before any pattern check: an empty scan set is a hard failure (exit 1 with an explicit refusal message), never a silent pass."
metrics:
  duration: "~40 min"
  completed: 2026-08-20
actuals:
  tokens: 6600
  tasks: 3
  commits: 3
status: complete
---

# Phase 1 Plan 2: Shared Quality Gates & Component Boundary Summary

`scripts/qa.sh` as the single shared entrypoint for lint/format/typecheck/test/boundary, invoked identically by five `repo: local` pre-commit hooks and by the refactored CI workflow — making REQ-A5's pass/fail parity structural — plus a mechanical, non-vacuous `scripts/check_component_boundary.sh` gate that enforces REQ-A6's thin-component/fat-lib rule in both places.

## What Was Built

- **`scripts/qa.sh`** (Task 1): dispatches five subcommands (`lint`, `format`, `typecheck`, `test`, `boundary`); resolves `REPO_ROOT` from `${BASH_SOURCE[0]}` and `cd`s there before anything else, so a call from `lib/` or `components/ingest/` targets the same `path/to/venv` and produces the same verdict as a call from the repo root. Locally exports `UV_PROJECT_ENVIRONMENT="$REPO_ROOT/path/to/venv"` (per CLAUDE.MD); under `CI` leaves it unset so the runner's own `uv sync --frozen --extra dev`-created environment is used. Builds `UV_RUN=(uv run --extra dev)` locally / `UV_RUN=(uv run --frozen --extra dev)` under CI once, so every subcommand branch inherits the dev-extra guarantee — no bare `uv run <tool>` exists anywhere in the script. Unknown subcommand exits 2 with a usage line.
- **`scripts/check_component_boundary.sh`** (Task 1): collects the scan set via `git ls-files -- 'components/*.py' 'components/**/*.py'` (tracked files only); refuses to pass on an empty scan set (exit 1, explicit refusal message) before running any pattern check; runs three `grep -nE` violation checks — pandas/numpy imports (plain, dotted-submodule, from-import forms), DataFrame-shaped method calls (`groupby`, `merge`, `pivot`, `resample`, `apply`, `assign`, `astype`, `read_parquet`, `to_parquet`, `read_csv`, `to_csv`), and `packages_to_install` — collecting all violations before exiting 1 once; exits 0 with a scanned-module count on a clean tree. Lives under `scripts/`, outside `components/`, so its own pattern strings never fall inside its own scan set.
- **`.pre-commit-config.yaml`** (Task 2): five `repo: local` hooks — `ruff-check`, `ruff-format`, `mypy-strict`, `boundary`, `pytest` — in that order, each `entry: scripts/qa.sh <subcommand>` with `pass_filenames: false` (so each tool runs over its own configured scope, exactly as CI does, rather than a pre-commit-appended file list). Hooks 3/5 scope to `\.py$`/`^lib/.*\.py$` so an empty-input commit reports Skipped, not Failed; hook 4 (`boundary`) is `always_run: true` so a deletion under `components/` still trips the non-vacuous guard. The fifth (`pytest`) hook is the D-03a-approved addition on top of D-03's hygiene scope, making REQ-A5's pass/fail parity literally true rather than merely documented.
- **`.github/workflows/ci.yml`** refactor (Task 2): `lint`, `typecheck`, `test` jobs now call `scripts/qa.sh lint`/`format`/`typecheck`/`test` instead of inlining tool commands; a `scripts/qa.sh boundary` step was added to the `lint` job. Every plan 01-01 invariant (strict `needs:` chain, SHA-pinned `uses:`, head-SHA image tag, least-privilege `permissions`, fork guard on `build-push`) survives unchanged.
- **`pyproject.toml`/`uv.lock`** (Task 2): `pre-commit>=4.6.2` added to the `dev` optional-dependency group via `uv add --optional dev pre-commit`; lockfile re-resolved and committed.
- **`README.md`** (Task 3): status framing (Phase 1 complete, `lib/` currently month-range-only), quick start (`uv sync --extra dev`, the five `scripts/qa.sh` commands, the bare-`uv-run` warning), repository layout (all six top-level directories), the thin-component/fat-lib contract and its three mechanically-enforced violation classes, CI stage order with the concrete GHCR namespace, and the D-05 visibility tradeoff (public repo/packages now vs. a private-package + `imagePullSecrets` choice for a real employer repo). No architecture diagram, ADRs, benchmark table, or "Next Steps" section — those are Phase 3's REQ-E1/E2/E3.

## qa.sh Subcommand -> CI/pre-commit Wiring (for plan 01-03's parity assertions)

| `qa.sh` subcommand | Tool invocation | pre-commit hook id | CI job/step |
|---|---|---|---|
| `lint` | `${UV_RUN[@]} ruff check .` | `ruff-check` | `lint` job |
| `format` | `${UV_RUN[@]} ruff format --check .` | `ruff-format` | `lint` job |
| `typecheck` | `${UV_RUN[@]} mypy --strict lib` | `mypy-strict` | `typecheck` job |
| `test` | `${UV_RUN[@]} pytest` | `pytest` | `test` job |
| `boundary` | delegates to `scripts/check_component_boundary.sh` | `boundary` | `lint` job (added step) |

`UV_RUN` resolves to `uv run --extra dev` locally (CI unset) and `uv run --frozen --extra dev` under CI (CI set, per GitHub Actions always setting `CI=true`).

## Deviations from Plan

None — plan executed exactly as written. `pre-commit` was added via `uv add --optional dev pre-commit` per the plan's explicit Task 2 instruction; this is not a deviation, it's the literal action specified.

### Acceptance-Criteria Note (not a deviation, documented for transparency)

The Task 1 acceptance criterion "running `CI=true scripts/qa.sh lint` does not create a `.venv` directory" holds **in the context the real CI workflow provides** (a preceding `uv sync --frozen --extra dev` step, per Task 2's action, creates `.venv` first) — verified explicitly: running `CI=true uv sync --frozen --extra dev` then `CI=true scripts/qa.sh lint` leaves `.venv`'s mtime unchanged (no second creation/mutation). Run bare, without that preceding sync, `uv run --frozen --extra dev` still auto-provisions `.venv` on first use — this is inherent `uv` behavior (a `run` with no pre-existing environment always provisions one, `--frozen` only skips lockfile mutation) and is what the CI workflow's explicit `uv sync` step exists to front-run. `.venv/` is already `.gitignore`d from 01-01, so this poses no tracked-file risk either way.

## Known Stubs

None. All three files created in this plan are complete, real implementations — `scripts/qa.sh` and `scripts/check_component_boundary.sh` are proven against the clean tree and against fail-first probes for every violation class; `README.md` documents only what has actually shipped.

## Threat Flags

None beyond what the plan's own `<threat_model>` already covers. All five dispositioned threats (T-01-09 through T-01-13) were applied exactly as specified: the boundary gate's non-vacuous guard (T-01-09), `repo: local`-only hooks with no `repo: https://` entries (T-01-10), plain reviewable shell with no network calls (T-01-11), a credential/secret-free README (T-01-12), and the plan 01-01 CI invariants reasserted after the refactor via the regression-guard greps (T-01-13).

## Self-Check: PASSED

- `scripts/qa.sh` exists and is executable: FOUND
- `scripts/check_component_boundary.sh` exists and is executable: FOUND
- `.pre-commit-config.yaml` exists with five `repo: local` hooks in order ruff-check, ruff-format, mypy-strict, boundary, pytest: FOUND
- `.github/workflows/ci.yml` invokes `scripts/qa.sh` five times, plan 01-01 invariants intact: FOUND
- `README.md` exists, contains `uv sync --extra dev`, `scripts/check_component_boundary.sh`, all six top-level dirs, CI job order, GHCR namespace, D-05 tradeoff: FOUND
- Commit `3481370` (Task 1 — qa.sh + boundary gate): FOUND in `git log --oneline`
- Commit `577a6d9` (Task 2 — pre-commit + CI wiring): FOUND
- Commit `d3a858d` (Task 3 — README): FOUND
- `UV_PROJECT_ENVIRONMENT=path/to/venv uv run --extra dev pre-commit run --all-files` on the final tree: exits 0, all five hooks Passed
- `scripts/qa.sh lint && scripts/qa.sh format && scripts/qa.sh typecheck && scripts/qa.sh test && scripts/qa.sh boundary` on the final tree: exits 0
- Working tree clean except pre-existing untracked `.gsd/` (present before this plan started, out of this plan's scope)
