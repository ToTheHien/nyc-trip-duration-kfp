---
phase: 01-repo-foundation-ci-quality-gates
verified: 2026-08-20T10:30:00Z
status: passed
score: 15/15 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 1: Repo Foundation & CI Quality Gates Verification Report

**Phase Goal:** A reviewer can clone the repo, install with one command, and see automated quality gates protecting `lib/` on every PR — before a single line of pandas or KFP logic exists.
**Verified:** 2026-08-20T10:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `uv sync --extra dev` from a fresh clone produces a working env with ruff/mypy/pytest (REQ-A1) | ✓ VERIFIED | No `.venv` created; `path/to/venv/bin/{ruff,mypy,pytest}` present and executable; six directories individually have tracked files (`lib`, `components`, `pipelines`, `serving`, `dashboard`, `tests`) |
| 2 | `ruff check .`, `ruff format --check .`, `mypy --strict lib` all exit 0 (REQ-A2, D-02) | ✓ VERIFIED | Ran directly: `scripts/qa.sh lint && scripts/qa.sh format && scripts/qa.sh typecheck` all exit 0 on current tree |
| 3 | `pytest` exits 0, 100% coverage on `lib/`, exact-value assertions (REQ-A3) | ✓ VERIFIED | `scripts/qa.sh test` run directly: 6 passed, `lib/months.py` 24 stmts/10 branches, 100% cover, `--cov-fail-under=100` satisfied; `tests/lib/test_months.py` inspected — every assertion is an exact-value comparison or `pytest.raises`, none is absence-of-exception only |
| 4 | Every local tool invocation goes through `uv run --extra dev`; no bare `uv run` | ✓ VERIFIED | `grep -Ec 'uv run --(frozen --)?extra dev' scripts/qa.sh` ≥ 1; `grep -Ec 'uv run (ruff|mypy|pytest)' scripts/qa.sh` = 0; ran `qa.sh lint/typecheck/test` back-to-back, venv tools still present afterward |
| 5 | Opening a PR runs lint→typecheck→test→build→push and publishes `ghcr.io/<owner>/<repo>/ingest:<pr-head-sha>` (REQ-A4, D-01) | ✓ VERIFIED | `.github/workflows/ci.yml` inspected: 4-job `needs:` chain intact; real green run `32324841172` (PR #7) shows all four jobs `success`; image at `ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:d8ee6b84e092f78559433098fbbf9b8e0311a0f9` confirmed pullable via `docker manifest inspect` (ran directly, exit 0) |
| 6 | Tag derived from `pull_request.head.sha \|\| github.sha`, never bare `github.sha` | ✓ VERIFIED | `ci.yml` line 53: `IMAGE_TAG: ${{ github.event.pull_request.head.sha || github.sha }}`; no bare `ingest:${{ github.sha }}` pattern present |
| 7 | Strict stage order lint→typecheck→test→build-push, `needs: [lint, typecheck, test]` | ✓ VERIFIED | `ci.yml`: `typecheck` needs `[lint]`, `test` needs `[lint, typecheck]`, `build-push` needs `[lint, typecheck, test]` |
| 8 | No `paths:`/`paths-ignore:` filter — every PR runs all stages | ✓ VERIFIED | `grep -Ec 'paths(-ignore)?:' .github/workflows/ci.yml` = 0 |
| 9 | `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` | ✓ VERIFIED | Present verbatim in `ci.yml` lines 12-14 |
| 10 | Every image tag is a real, resolvable 40-char git SHA — no mutable tag | ✓ VERIFIED | `git cat-file -e` succeeds for TRACER_HEAD_SHA (`6f4a969...`) and CLEAN_HEAD_SHA (`d8ee6b8...`); no `:latest` in workflow; `docker manifest inspect` resolves both under the real registry |
| 11 | The pushed image runs and prints exactly the four expected month lines | ✓ VERIFIED | Ran directly: local rebuild of `components/ingest/Dockerfile` from the current tree, `docker run ... --start-month 2019-11 --end-month 2020-02` prints exactly `2019-11`, `2019-12`, `2020-01`, `2020-02` |
| 12 | `pre-commit run --all-files` and CI check stages reach identical verdicts (REQ-A5) | ✓ VERIFIED | Ran directly: all 5 hooks Passed on clean tree; 01-03-SUMMARY.md's 5-cycle break-vs-clean table (independently re-derivable via the same qa.sh subcommands) shows per-cycle local/CI match; `.pre-commit-config.yaml` hooks in CI stage order (ruff-check, ruff-format, mypy-strict, boundary, pytest), all `entry: scripts/qa.sh <subcommand>`, `repo: local` only |
| 13 | `scripts/check_component_boundary.sh` catches pandas/numpy imports, DataFrame methods, `packages_to_install`; exits 0 clean; refuses to pass vacuously (REQ-A6) | ✓ VERIFIED | Ran directly: clean tree passes (3 modules scanned); fail-first probe with the CR-01 bypass string (`import pandas  # noqa`) now correctly caught (exit 1); comma-separated form (`import os, pandas as pd`) caught; false-positive guard (`import pandas_helper`) correctly passes; empty-scan-set refusal logic present in script (`REFUSED: ...` message, tested in 01-02) |
| 14 | Boundary gate runs in both CI (`lint` job step) and pre-commit | ✓ VERIFIED | `ci.yml` lint job has `scripts/qa.sh boundary` step; `.pre-commit-config.yaml` has `boundary` hook calling the same subcommand |
| 15 | README states thin-component/fat-lib contract, one-command install, CI order, D-05 tradeoff | ✓ VERIFIED | `README.md` read in full: all sections present — Quick Start (`uv sync --extra dev`), Repository Layout (all 6 dirs), Architectural Contract (3 violation classes named), CI (job order, GHCR namespace), D-05 visibility tradeoff explicit |

**Score:** 15/15 truths verified (0 present, behavior-unverified)

### CR-01 Fix Verification (dispatch-specific)

The orchestrator reported fixing a boundary-gate regex bypass (`scripts/check_component_boundary.sh`'s import check was end-anchored, defeatable by trailing content such as `# noqa`) in commit `4a50022`, merged to `development` at `5bc7cc8`. Independently verified, not trusting the commit message:

- Current `IMPORT_RE` in `scripts/check_component_boundary.sh` drops the end-of-line anchor; uses a boundary-after-module-name alternative plus a comma-separated-list alternative.
- Fail-first proof (re-run live, not reused from SUMMARY): `printf 'import pandas  # noqa\n'` → gate correctly exits 1 and names the offending file:line. Under the pre-fix regex this bypass was empirically confirmed exploitable (per `01-REVIEW.md` CR-01 finding); the current tree no longer exhibits it.
- Additional case: `import os, pandas as pd` (comma-separated) → correctly exits 1.
- False-positive guard: `import pandas_helper` → correctly exits 0 (does not over-match unrelated module names).
- Full clean-tree gate run after each probe: exits 0, 3 modules scanned — no regression.

**Caveat (non-blocking, noted for transparency):** commit `4a50022` was merged directly into `development` via a local branch + merge (not through a GitHub PR), so `gh api .../commits/4a50022/status` shows zero CI statuses — this specific fix has not been exercised by a live GitHub Actions run, only verified locally in this dispatch and presumably by the author locally. The phase's original REQ-A6 CI proof (01-03 Cycle D, run `32323816958`) used a plain `import pandas as pd` with no trailing content, which both the pre-fix and post-fix regex catch identically, so that live-CI proof remains valid and unaffected by the fix. This is recorded as an anti-pattern/info item below, not a gap — it does not fail the truth that the boundary gate is present, effective, and demonstrated in CI.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | Root metadata, D-04 groups, config blocks | ✓ VERIFIED | All 7 blocks present; `dev`/`pipeline`/`ml` groups exact |
| `uv.lock` | Committed, reproducible | ✓ VERIFIED | Tracked, clean working tree |
| `lib/months.py` | `month_range` fully typed/tested | ✓ VERIFIED | Matches interface contract exactly, 100% coverage |
| `tests/lib/test_months.py` | 6 exact-value cases | ✓ VERIFIED | All 6 cases present, all exact-value or `pytest.raises` |
| `components/ingest/main.py` | Thin wrapper, zero pandas | ✓ VERIFIED | Argparse → `month_range` → stdout only |
| `components/ingest/Dockerfile` | Digest-pinned base image | ✓ VERIFIED | `FROM python:3.12-slim@sha256:...` digest present |
| `.github/workflows/ci.yml` | lint→typecheck→test→build-push | ✓ VERIFIED | 4-job strict chain, SHA-pinned actions, no `:latest` |
| `scripts/qa.sh` | Shared entrypoint | ✓ VERIFIED | 5 subcommands, resolves REPO_ROOT from own path |
| `scripts/check_component_boundary.sh` | Mechanical boundary gate | ✓ VERIFIED | 3 violation classes + non-vacuous guard, CR-01 fix confirmed effective |
| `.pre-commit-config.yaml` | 5 local hooks, CI order | ✓ VERIFIED | `repo: local` only, order matches CI stages |
| `README.md` | Install/layout/contract/CI/D-05 | ✓ VERIFIED | All required content present, no forbidden Phase-3 sections |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `components/ingest/main.py` | `lib/months.py` | `from lib.months import month_range` | ✓ WIRED | Confirmed by direct read |
| `.github/workflows/ci.yml` | `components/ingest/Dockerfile` | `file: components/ingest/Dockerfile` | ✓ WIRED | Confirmed in build-push step |
| `.github/workflows/ci.yml` | `ghcr.io` | `docker/login-action` + PR-head-SHA tag expression | ✓ WIRED | Confirmed, image pull verified live |
| `.pre-commit-config.yaml` | `scripts/qa.sh` | every hook `entry:` | ✓ WIRED | 5/5 hooks bind to `scripts/qa.sh <subcommand>` |
| `.github/workflows/ci.yml` | `scripts/qa.sh` | job steps | ✓ WIRED | lint/typecheck/test jobs call `scripts/qa.sh` |
| `scripts/qa.sh` | `scripts/check_component_boundary.sh` | `boundary` subcommand delegation | ✓ WIRED | Confirmed by direct read and live run |

### Data-Flow Trace (Level 4)

Not applicable in the conventional sense (no UI/DB layer this phase) — the equivalent "data flow" is CLI arg → `month_range` → stdout, and CI tag-derivation → image push → registry resolution. Both traced live above (docker run output, `docker manifest inspect`).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 5 quality gates pass on committed tree | `scripts/qa.sh lint && format && typecheck && test && boundary` | exit 0, 6 tests passed, 100% coverage, boundary OK | ✓ PASS |
| pre-commit parity | `uv run --extra dev pre-commit run --all-files` | All 5 hooks Passed | ✓ PASS |
| Boundary gate catches CR-01 bypass | fail-first probe with `import pandas  # noqa` | exit 1, violation reported | ✓ PASS |
| Boundary gate false-positive guard | probe with `import pandas_helper` | exit 0 | ✓ PASS |
| Local Docker image build+run reproduces tracer output | `docker build` + `docker run --start-month 2019-11 --end-month 2020-02` | printed exactly 4 expected lines | ✓ PASS |
| Positive control resolves | `docker manifest inspect` on TRACER_HEAD_SHA and CLEAN_HEAD_SHA | both exit 0 | ✓ PASS |
| Negative proof (break SHAs unresolvable) | `docker manifest inspect` on all 4 break-branch head SHAs | all exit non-zero | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| REQ-A1 | 01-01 | Monorepo skeleton, `uv sync` clean install | ✓ SATISFIED | Directory layout, lockfile, no `.venv` created |
| REQ-A2 | 01-01, 01-03 | ruff + mypy --strict on `lib/`, break proof | ✓ SATISFIED | Local run clean; real CI runs 32323395776 (lint fail) and 32323494562 (typecheck fail) |
| REQ-A3 | 01-01, 01-03 | pytest exact-value assertions, ~100% coverage | ✓ SATISFIED | 100% coverage verified live; real CI break run 32323571520 (test fail via behavioral regression, test file untouched) |
| REQ-A4 | 01-01, 01-03 | CI lint→typecheck→test→build→push, blocked at failing stage | ✓ SATISFIED | Green run 32324841172 all 4 jobs success; 4 break SHAs proven unpublished against positive-control SHA that resolves |
| REQ-A5 | 01-02, 01-03 | pre-commit mirrors CI verdicts | ✓ SATISFIED | 5 local hooks bound to identical `qa.sh` subcommands; live parity run confirmed; README documents no divergence |
| REQ-A6 | 01-02, 01-03 | `lib/` holds pandas logic; `components/` thin, grep-verifiable | ✓ SATISFIED | Mechanical gate in CI+pre-commit; real CI break run 32323816958 names `check_component_boundary.sh`; CR-01 bypass fix independently re-verified effective |

No orphaned requirements — REQUIREMENTS.md maps only REQ-A1..A6 to Phase 1, all six are claimed across the three plans' `requirements:` frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any phase-modified file | — | None |
| `.github/workflows/ci.yml` | 55 | (Info, from 01-REVIEW.md WR-01, unresolved) `build-push`'s checkout has no `ref:` pinned to `IMAGE_TAG`; on a same-repo PR the built tree is the ephemeral merge-ref commit while the tag names the PR head SHA — these can diverge if the base branch moved since the PR branch's last rebase | ⚠️ Warning | Does not fail any must-have in this phase's plans (which specify only the tag-expression, not checkout-ref pinning) but is a real traceability gap the review correctly flagged; left unresolved by the orchestrator's single CR-01 fix |
| `components/ingest/Dockerfile` | 1-13 | (Info, from 01-REVIEW.md WR-02, unresolved) No `USER` directive — component image runs as root | ⚠️ Warning | Standard hardening gap, not exploitable via this file alone; unresolved |
| `.github/workflows/ci.yml` | 4-7 | (Info, from 01-REVIEW.md IN-01) `push` trigger only watches `master`, not `development` — a direct/fast-forward merge to `development` produces no independent post-merge CI signal | ℹ️ Info | Mitigated in practice: all break/clean cycles in 01-03 used real PRs (`pull_request` has no branch filter), and the project's own branching rule requires branch+merge, not direct push |
| `scripts/check_component_boundary.sh` | — | CR-01 fix commit (`4a50022`) has no associated GitHub Actions run (merged via local branch, not PR) | ℹ️ Info | Fix independently re-verified effective in this dispatch via local fail-first probes; the base REQ-A6 CI proof (Cycle D) remains valid since it used a plain import unaffected by the original bug |

None of the above rise to Blocker — they are pre-existing, already-classified Warning/Info findings from the phase's own code-review pass (`01-REVIEW.md`), correctly left unresolved since only the Blocker (CR-01) was in scope for the fix the orchestrator applied.

### Human Verification Required

None. All must-haves were verifiable via direct command execution, file inspection, and live `gh`/`docker` queries against the real GitHub Actions runs and the real GHCR registry.

### Gaps Summary

No gaps. All 15 must-have truths verified against the live codebase and, where applicable, against real GitHub Actions run data and a live GHCR registry (not SUMMARY.md claims alone). The CR-01 boundary-gate regex fix was independently re-verified effective via fresh fail-first and false-positive probes run in this dispatch. Two pre-existing Warning-level findings (WR-01 checkout/tag mismatch on cross-base PRs, WR-02 root user in the component image) and two Info-level findings (IN-01 push-trigger branch scope, and the CR-01 fix lacking its own live CI run) remain from the phase's own code review — none of these were must-haves in any of the three plans' frontmatter, so they do not block phase completion, but are worth carrying forward as known technical debt for Phase 2/3 consideration.

---

_Verified: 2026-08-20T10:30:00Z_
_Verifier: Claude (gsd-verifier)_
