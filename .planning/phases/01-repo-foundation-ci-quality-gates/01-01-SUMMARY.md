---
phase: 01-repo-foundation-ci-quality-gates
plan: 01
subsystem: repo-foundation-ci
tags: [uv, ruff, mypy, pytest, docker, github-actions, ghcr]
dependency graph:
  requires: []
  provides:
    - lib.months.month_range
    - components/ingest thin-wrapper pattern
    - .github/workflows/ci.yml (lint -> typecheck -> test -> build-push)
    - pyproject.toml D-04 optional-dependency groups (dev/pipeline/ml)
  affects:
    - 01-02 (pre-commit config mirrors this CI)
    - 01-03 (consumes TRACER_HEAD_SHA as positive control for tag-derivation proofs)
    - Phase 2 (lib/ engineering builds on this scaffold)
    - Phase 3 (pipelines import lib.months for start_month/end_month backfill)
tech-stack:
  added: [uv 0.11.0, ruff 0.16.3, mypy 2.3.1, pytest 9.1.1, pytest-cov 7.1.0, hatchling]
  patterns: ["thin component / fat lib", "TDD RED-GREEN", "digest-pinned base image", "SHA-pinned GH Actions"]
key-files:
  created:
    - .python-version
    - pyproject.toml
    - uv.lock
    - lib/__init__.py
    - lib/months.py
    - tests/__init__.py
    - tests/lib/__init__.py
    - tests/lib/test_months.py
    - components/__init__.py
    - components/ingest/__init__.py
    - components/ingest/main.py
    - components/ingest/Dockerfile
    - pipelines/.gitkeep
    - serving/.gitkeep
    - dashboard/.gitkeep
    - .github/workflows/ci.yml
  modified:
    - .gitignore
decisions:
  - "D-05 (Task 1, resolved by user prior to this dispatch): public repo `ToTheHien/nyc-trip-duration-kfp`, public GHCR packages. Reason: matches the project's portfolio purpose (interview-legible, clonable), and Phase 3's k3d cluster needs zero registry-credential wiring to pull component images. GHCR namespace implied: `ghcr.io/ToTheHien/nyc-trip-duration-kfp/ingest` as displayed on GitHub — the actual pushed/pulled OCI reference is lowercase (see Deviations): `ghcr.io/tothehien/nyc-trip-duration-kfp/ingest`."
  - "Task 2 package-legitimacy checkpoint: resolved by user prior to this dispatch (explicit 'đồng ý cài đặt' approval) after a WebFetch-verified report on ruff, mypy, pytest, pytest-cov, coverage, pre-commit — including the coveragepy org-move note (nedbat/coveragepy -> coveragepy/coveragepy, same maintainer, not a typosquat). Versions actually written into pyproject.toml: ruff~=0.16.0, mypy~=2.3.0, pytest~=9.1.0, pytest-cov (unpinned minor, current)."
  - "Single-root-package pyproject.toml (D-04 optional-dependency groups dev/pipeline/ml) rather than a uv workspace, per the plan's explicit instruction overriding STACK.md's workspace suggestion."
metrics:
  duration: "~35 min"
  completed: 2026-08-19
actuals:
  tokens: 42000
  tasks: 5
  commits: 6
status: complete
---

# Phase 1 Plan 1: Repo Foundation & CI Quality Gates — Tracer Slice Summary

One real function (`lib.months.month_range`) driven end-to-end through TDD, ruff, `mypy --strict`, 100%-coverage pytest, a digest-pinned Docker image, and a GitHub Actions PR run that published the image to GHCR — proving the entire Phase 1 quality-gate stack on the smallest possible real surface before Phase 2/3 build on it.

## What Was Built

- **Repo skeleton** (Task 3): `lib/`, `components/ingest/`, `pipelines/`, `serving/`, `dashboard/`, `tests/lib/` directory layout; `pyproject.toml` with `[project]`, `[project.optional-dependencies]` (`dev`/`pipeline`/`ml` per D-04), `[build-system]` (hatchling), `[tool.ruff]`/`[tool.ruff.lint]`, `[tool.mypy]` (strict, `lib/`-only per D-02), `[tool.pytest.ini_options]`, `[tool.coverage.run]`; `uv.lock` committed. `UV_PROJECT_ENVIRONMENT=path/to/venv uv sync --extra dev` verified idempotent across repeated `uv run --extra dev` calls (EXTRA-DEV RULE holds).
- **Tracer payload** (Task 4, TDD): `tests/lib/test_months.py` written and confirmed RED (`ModuleNotFoundError: No module named 'lib.months'`) before `lib/months.py` existed; `lib/months.py` then written GREEN — `month_range(start_month, end_month) -> list[str]`, fully typed, six exact-value test cases, 100% branch coverage. `components/ingest/main.py` is a thin argparse CLI (parse -> call `month_range` -> print). `components/ingest/Dockerfile`: `python:3.12-slim` pinned by digest `sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a` (resolved live via `docker buildx imagetools inspect`), OCI `source`/`revision` labels fed from build args, zero installed packages. Local proof: `docker build` + `docker run --start-month 2019-11 --end-month 2020-02` printed exactly `2019-11`, `2019-12`, `2020-01`, `2020-02`.
- **CI + remote + first publish** (Task 5): `.github/workflows/ci.yml` — four-job strict chain (`lint` -> `typecheck` -> `test` -> `build-push`, `needs:` chained), triggers on every `pull_request` (no path filter) and `push` to `master`, top-level `permissions: contents: read`, `concurrency` group with `cancel-in-progress`, every `uv run` uses `--frozen --extra dev`, image tag/OCI-revision both derive from a single job-level `env.IMAGE_TAG = github.event.pull_request.head.sha || github.sha`, every third-party action pinned to a 40-hex commit SHA with a version-tag comment. Opened PR #1 (`tracer/ci-proof` -> `master`) on the pre-existing `ToTheHien/nyc-trip-duration-kfp` remote; CI ran green after one fix (see Deviations); image proven pullable and runnable anonymously.

## Resolved Checkpoints (from prior conversation turns, not re-decided here)

- **D-05**: public repo, public GHCR packages — see `decisions` frontmatter.
- **Task 2 package legitimacy**: user-approved — see `decisions` frontmatter.

## TRACER_HEAD_SHA and Registry Proof

- **TRACER_HEAD_SHA:** `6f4a96925c9c7dd2a2add46260c3e84b84b83f0f` — the head commit of PR #1 (`tracer/ci-proof`) at the time its `build-push` job ran and succeeded. This is a real commit (`git cat-file -e` succeeds), not a synthesised `refs/pull/N/merge` SHA.
- **Green CI run:** https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32210503873 (run `32210503873`; all four jobs `lint`, `typecheck`, `test`, `build-push` concluded `success`).
- **Published image (actual resolved namespace, lowercase — see Deviations):** `ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:6f4a96925c9c7dd2a2add46260c3e84b84b83f0f`
- **Anonymous pull/run proof (D-05 = PUBLIC branch of the acceptance criteria):** ran `docker logout ghcr.io`, then `docker manifest inspect ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:6f4a96925c9c7dd2a2add46260c3e84b84b83f0f` (exit 0, no credentials), then `docker run --rm ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:6f4a96925c9c7dd2a2add46260c3e84b84b83f0f --start-month 2019-11 --end-month 2020-02` — pulled anonymously and printed exactly `2019-11`, `2019-12`, `2020-01`, `2020-02`.
- **Pinned action SHAs (with version tags actually written into `ci.yml`):**
  - `actions/checkout@11d5960a326750d5838078e36cf38b85af677262` # v4
  - `astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86` # v5
  - `docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c` # v4
  - `docker/login-action@dbcb813823bdd20940b903addbd779551569679f` # v4
  - `docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a` # v7
- **Base image digest:** `python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] ruff's markdown code-fence formatting swept `.planning/research/ARCHITECTURE.md`**
- **Found during:** Task 4, running `ruff format --check .` before writing the CI workflow.
- **Issue:** Ruff 0.16.x formats embedded Python code fences inside `.md` files by default (not just `.py`/`.pyi`/`.ipynb`). This flagged a pre-existing formatting inconsistency in `.planning/research/ARCHITECTURE.md` — a research doc unrelated to this task's code surface — which would have blocked the `ruff format --check .` acceptance gate on a file this plan neither owns nor should reformat (surgical-changes rule).
- **Fix:** Added `.planning` to `[tool.ruff] extend-exclude` in `pyproject.toml` so ruff's scope matches the intended code surface (`lib/`, `tests/`, `components/`).
- **Files modified:** `pyproject.toml`
- **Commit:** `326410d`

**2. [Rule 1 - Bug] GHCR image tag rejected: repository name must be lowercase**
- **Found during:** Task 5, first CI run (`32210411651`), `build-push` job.
- **Issue:** `github.repository` preserves the GitHub-display-cased owner (`ToTheHien`), producing the tag `ghcr.io/ToTheHien/nyc-trip-duration-kfp/ingest:<sha>`, which `docker buildx` rejected: `invalid tag ... repository name must be lowercase`. GitHub Actions expressions have no built-in `toLower()`.
- **Fix:** Added a step that lowercases `github.repository` into `$GITHUB_ENV` (`REPO_LC`) and referenced `${{ env.REPO_LC }}` in the `tags:` input. Re-verified all acceptance-criteria greps still pass after the edit.
- **Files modified:** `.github/workflows/ci.yml`
- **Commit:** `6f4a969` (pushed to `tracer/ci-proof`; triggered the second, green CI run `32210503873`)
- **Consequence for D-05's recorded namespace:** the GHCR namespace is actually lowercase — `ghcr.io/tothehien/nyc-trip-duration-kfp/ingest`, not the display-cased `ghcr.io/ToTheHien/nyc-trip-duration-kfp/ingest` recorded when D-05 was decided. This is standard OCI/GHCR behavior (registry paths are always lowercase); the GitHub repo itself (`ToTheHien/nyc-trip-duration-kfp`) keeps its display casing. Plan 01-03 and any Phase 3 `base_image=` references must use the lowercase form.

### Blocked / Deferred to Human Action

**3. PR #1 merge blocked by the runtime's own permission classifier**
- **What happened:** `gh pr merge 1 --merge` and `gh pr merge 1 --merge --delete-branch` were both denied by the Claude Code auto-mode permission classifier ("Blocked by classifier") — a runtime safety guardrail on mutating actions against the repository, independent of GSD's own checkpoint system. Per the harness's own instructions on receiving this denial, no workaround (e.g., a local `git merge` + `git push origin tracer/ci-proof:master` accomplishing the same effect through a different tool) was attempted, since that would route around the guardrail's evident intent.
- **Current state:** PR #1 (https://github.com/ToTheHien/nyc-trip-duration-kfp/pull/1) is **OPEN**, `mergeable: MERGEABLE`, branch `tracer/ci-proof` pushed with all Task 3-5 commits including the lowercase fix. CI is green (run `32210503873`). The image is already published and proven pullable/runnable anonymously (see above) — this does not depend on the merge landing.
- **What the developer needs to do:** merge PR #1 via the GitHub UI (https://github.com/ToTheHien/nyc-trip-duration-kfp/pull/1 -> "Merge pull request"), or grant a Bash permission rule for `gh pr merge` and re-run. TRACER_HEAD_SHA (`6f4a96925c9c7dd2a2add46260c3e84b84b83f0f`) is already captured above and is unaffected by however the merge is eventually performed (squash/merge/rebase) — per the plan's own guidance, it must never be re-derived from a post-merge `git rev-parse HEAD`.
- **Local `master`:** contains Tasks 3 and 4's commits (repo skeleton, `lib/months.py`, the ingest component, the Dockerfile) — these were committed directly to `master` before Task 5 branched. Local `master` does **not** yet contain the CI workflow file or its lowercase fix (those exist only on `tracer/ci-proof`, pending the PR merge). Local `master` is also 4 commits ahead of `origin/master` and has not been pushed, for the same reason: pushing `master` is the same class of mutating main-branch action the classifier denied for the merge.

## Known Stubs

None. `lib/months.py` and `components/ingest/main.py` are real, complete implementations — not placeholders.

## Threat Flags

None beyond what the plan's own `<threat_model>` already covers; no new network endpoints, auth paths, or trust-boundary-crossing surface was introduced beyond what Tasks 3-5 already accounted for (T-01-01 through T-01-08, all `mitigate`, all applied as specified: least-privilege `permissions:`, SHA-pinned actions, fork-PR push guard, `.gitignore` secret patterns, full-SHA image tagging).

## Self-Check: PASSED

- `lib/months.py` exists: FOUND
- `tests/lib/test_months.py` exists: FOUND
- `components/ingest/main.py` exists: FOUND
- `components/ingest/Dockerfile` exists: FOUND
- `.github/workflows/ci.yml` exists: FOUND
- Commit `d253cb8` (repo skeleton): FOUND in `git log --oneline --all`
- Commit `01a5ccd` (RED test): FOUND
- Commit `326410d` (GREEN + ruff-exclude fix): FOUND
- Commit `5187686` (CI workflow): FOUND
- Commit `6f4a969` (lowercase fix, on `tracer/ci-proof`): FOUND
- PR #1: OPEN, mergeable, CI green — confirmed via `gh pr view 1` and `gh run view 32210503873`
- Anonymous `docker manifest inspect` + `docker run` against the published GHCR image: both succeeded, printed the four expected lines
