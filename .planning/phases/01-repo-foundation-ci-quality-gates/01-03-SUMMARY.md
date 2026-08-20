---
phase: 01-repo-foundation-ci-quality-gates
plan: 03
subsystem: ci-quality-gates
tags: [github-actions, pre-commit, ruff, mypy, pytest, ghcr, docker, boundary-gate]

# Dependency graph
requires:
  - phase: 01-repo-foundation-ci-quality-gates (01-01)
    provides: TRACER_HEAD_SHA (positive control for the tag-derivation proof), lib/months.py, components/ingest/main.py, .github/workflows/ci.yml lint->typecheck->test->build-push chain
  - phase: 01-repo-foundation-ci-quality-gates (01-02)
    provides: scripts/qa.sh, scripts/check_component_boundary.sh, .pre-commit-config.yaml (five hooks), README.md
provides:
  - Evidence that each CI gate (lint, typecheck, test, boundary) independently blocks a real PR at its own stage with no downstream image published
  - Non-vacuous negative proof (four break SHAs unresolvable) validated against a positive control (two independent green-run SHAs now resolve under the same tag derivation)
  - README pre-commit/CI parity subsection (REQ-A5 literal proof)
  - scripts/qa.sh boundary output now identifies check_component_boundary.sh (fixes a REQ-A6 evidence gap discovered mid-plan)
affects: [Phase 1 exit criteria, Phase 2 (inherits a proven, demonstrated gate stack), Phase 3 (GHCR pull-ability precedent for in-cluster proof)]

# Actuals (#2632)
actuals:
  tokens: 900
  tasks: 2
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns: ["per-commit git-hook bypass (--no-verify) scoped strictly to deliberately-broken commits, never a hook uninstall", "positive-control-before-negative-proof ordering for absence-of-artifact assertions"]

key-files:
  created:
    - .planning/phases/01-repo-foundation-ci-quality-gates/01-03-break-shas.txt
    - .planning/phases/01-repo-foundation-ci-quality-gates/01-03-control-sha.txt
  modified:
    - README.md
    - scripts/qa.sh

key-decisions:
  - "Branching override (per this dispatch's orchestrator instructions, overriding the plan's literal 'default branch' wording): all five ci-proof/* branches were created from and (for ci-proof/clean) merged into development, never master. Every gh pr create used --base development explicitly."
  - "Rule 3 deviation: scripts/qa.sh's boundary subcommand delegated to check_component_boundary.sh silently, so no CI log ever contained that literal string, blocking the plan's own REQ-A6 acceptance criterion. Fixed with a one-line echo, committed directly to development (not as part of any break/revert cycle), then Cycle D was redone against the fixed baseline."

patterns-established:
  - "Pattern 1: Absence-of-artifact proofs (docker manifest inspect exit != 0) are only reported after a positive control resolves under the identical tag derivation in the same command sequence — otherwise a broken tag scheme masquerades as gate effectiveness."
  - "Pattern 2: Deliberate-defect commits use git commit --no-verify per-commit, immediately after an explicit pre-commit run --all-files has recorded the local verdict — the hook itself is never uninstalled, keeping the REQ-A5 parity proof live for every subsequent commit."

requirements-completed: [REQ-A2, REQ-A3, REQ-A4, REQ-A5, REQ-A6]

coverage:
  - id: D1
    description: "Lint gate (ruff F401 unused-import) blocks a real PR at the lint job; typecheck/test/build-push all report skipped, never success or failure"
    requirement: "REQ-A2"
    verification:
      - kind: e2e
        ref: "gh run view 32323395776 --json conclusion,jobs (run https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323395776)"
        status: pass
    human_judgment: true
    rationale: "Plan's own <human-check> requires visually confirming the job list (red lint, grey downstream) and that PR #2 is closed, not merged — user confirmed this in-session."
  - id: D2
    description: "Typecheck gate (mypy --strict assignment/operator errors) blocks a real PR at the typecheck job while lint stays green — isolation confirmed locally before the push"
    requirement: "REQ-A2"
    verification:
      - kind: e2e
        ref: "gh run view 32323494562 --json conclusion,jobs (run https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323494562)"
        status: pass
    human_judgment: true
    rationale: "Plan's own <human-check> requires visual confirmation of the run and that PR #3 is closed, not merged — user confirmed this in-session."
  - id: D3
    description: "Test gate (pytest) blocks a real PR at the test job via a behavioural regression (exclusive end_month) caught by the pre-existing exact-value assertions, without editing the test file"
    requirement: "REQ-A3"
    verification:
      - kind: e2e
        ref: "gh run view 32323571520 --json conclusion,jobs (run https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323571520)"
        status: pass
    human_judgment: true
    rationale: "Plan's own <human-check> requires visual confirmation of the run and that PR #4 is closed, not merged — user confirmed this in-session."
  - id: D4
    description: "Boundary gate blocks a real PR at the lint job's scripts/qa.sh boundary step, with check_component_boundary.sh named in the failing-step log"
    requirement: "REQ-A6"
    verification:
      - kind: e2e
        ref: "gh run view 32323816958 --log-failed | grep check_component_boundary.sh (run https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323816958)"
        status: pass
    human_judgment: true
    rationale: "Plan's own <human-check> requires visual confirmation of the run and that PR #6 is closed, not merged — user confirmed this in-session."
  - id: D5
    description: "No published image exists at any of the four break-branch head SHAs, proven non-vacuous by a positive control (TRACER_HEAD_SHA) that resolves under the identical tag derivation"
    requirement: "REQ-A4"
    verification:
      - kind: integration
        ref: "docker manifest inspect ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:<sha> — control 6f4a969... exits 0; all four break SHAs exit non-zero"
        status: pass
    human_judgment: false
  - id: D6
    description: "Clean PR drives all four CI jobs green and publishes a pullable, runnable image tagged with its head commit SHA under the D-05 public posture"
    requirement: "REQ-A4"
    verification:
      - kind: e2e
        ref: "gh run view 32324841172 --json conclusion,jobs; docker logout ghcr.io && docker pull && docker run ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:d8ee6b84e092f78559433098fbbf9b8e0311a0f9"
        status: pass
    human_judgment: true
    rationale: "Plan's own <human-check> requires visually confirming the build-push digest in the run and the package's Public visibility on the GHCR package page — user confirmed both in-session."
  - id: D7
    description: "pre-commit run --all-files reaches the identical pass/fail verdict as the corresponding CI run on all five commits exercised (four break cycles + the clean commit), including the pytest-hook test-regression case"
    requirement: "REQ-A5"
    verification:
      - kind: unit
        ref: "local pre-commit run --all-files output per cycle (A: ruff-check Failed; B: mypy-strict Failed; C: pytest Failed; D: boundary Failed; clean: all Passed) matching each cycle's CI job conclusions"
        status: pass
    human_judgment: false
  - id: D8
    description: "README documents the five pre-commit checks mapped onto the CI job running the same scripts/qa.sh subcommand, and states pre-commit/CI reach the same verdict, citing Cycle C's run as the pytest-hook demonstration"
    requirement: "REQ-A5"
    verification:
      - kind: other
        ref: "grep -c 'scripts/qa.sh test' README.md (=2); grep -c 'scripts/qa.sh test' .pre-commit-config.yaml (=1)"
        status: pass
    human_judgment: false

duration: ~40min
completed: 2026-08-20
status: complete
---

# Phase 1 Plan 3: Prove the Quality Gates Fire — CI Proof Summary

**Four deliberate-defect PRs (lint/typecheck/test/boundary), each blocked at its own CI stage with no image published — validated against a positive control that does resolve, plus one clean PR that published a pullable/runnable GHCR image and closed the REQ-A5 pre-commit/CI parity claim in README.**

## Performance

- **Duration:** ~40 min execution time (two brief pauses for the plan's mandatory `<human-check>` browser verifications are excluded from this estimate)
- **Started:** 2026-08-20T02:02Z (approx, immediately after Wave 2 merge)
- **Completed:** 2026-08-20T02:38Z
- **Tasks:** 2 (both complete)
- **Files modified:** 6 touched — 2 permanent (`scripts/qa.sh`, `README.md`), 2 evidence files created, 2 transiently modified and reverted byte-identical (`lib/months.py`, `components/ingest/main.py`)

## Accomplishments

- Cycle A (lint): unused-import defect on `ci-proof/lint` failed the `lint` job; `typecheck`/`test`/`build-push` all `skipped`.
- Cycle B (typecheck): mypy assignment/operator defect on `ci-proof/typecheck` passed `lint`, failed `typecheck`; isolation confirmed locally (`scripts/qa.sh lint`/`format` exit 0, `scripts/qa.sh typecheck` exit non-zero) before the push.
- Cycle C (test): exclusive-`end_month` behavioural regression on `ci-proof/test` passed `lint`/`typecheck`, failed `test` — caught by the pre-existing exact-value assertions in `tests/lib/test_months.py`, which was never touched.
- Cycle D (boundary): pandas usage added to `components/ingest/main.py` on `ci-proof/boundary` failed `lint` at the `scripts/qa.sh boundary` step, with `check_component_boundary.sh` named in the failing-step log (after a mid-plan fix — see Deviations).
- Non-vacuous negative proof: `docker manifest inspect` fails for all four break SHAs, run in the same command sequence as a positive control (`TRACER_HEAD_SHA`, plan 01-01) that succeeds.
- Clean path: `ci-proof/clean` PR drove all four CI jobs green, merged into `development`, and published `ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:d8ee6b84e092f78559433098fbbf9b8e0311a0f9` — pulled anonymously (after `docker logout ghcr.io`) and run, printing exactly the four expected month lines.
- README now documents the five pre-commit hooks mapped to their CI jobs and states plainly (with a citation to Cycle C's run) that `pre-commit run --all-files` and CI reach the same verdict on the same commit — closing REQ-A5 literally, not just by assertion.
- The pre-commit git hook survived all five cycles: `.git/hooks/pre-commit` remained installed and wired throughout; the four defect commits used a per-commit `--no-verify` bypass (after their local verdict was explicitly recorded), and the clean commit was accepted by the hook unaided.

## Task Commits

Both tasks, plus one mid-plan deviation fix, were committed atomically on `development`:

1. **Task 1 (deviation fix): identify `check_component_boundary.sh` in `qa.sh boundary` output** — `1b37d89` (fix)
2. **Task 1: record break-cycle and control SHAs** — `a5caa20` (test)
3. **Task 2: pre-commit/CI parity README subsection** — `d8ee6b8` (docs, on `ci-proof/clean`, merged via `abd8249`)

**Plan metadata:** _pending — see final commit below_

_Note: the four break-cycle defect commits (`f8c0d6e`, `eb5f498`, `0ebac98`, and the superseded `39aa9a2` / final `8ed1d89`) were pushed to throwaway `ci-proof/*` branches, never merged, and the branches were deleted via `gh pr close --delete-branch`. They do not appear in `development`'s history._

## Files Created/Modified

- `.planning/phases/01-repo-foundation-ci-quality-gates/01-03-break-shas.txt` — four break-branch head commit SHAs, one per line, written as each cycle produced it
- `.planning/phases/01-repo-foundation-ci-quality-gates/01-03-control-sha.txt` — one line, `TRACER_HEAD_SHA` (plan 01-01's positive control)
- `README.md` — new "Pre-commit / CI Parity" subsection under the existing CI section
- `scripts/qa.sh` — one-line echo identifying `check_component_boundary.sh` before delegating to it in the `boundary` subcommand (deviation fix)
- `lib/months.py` — modified transiently across Cycles A/B/C, reverted byte-identical after each cycle
- `components/ingest/main.py` — modified transiently across Cycle D (both attempts), reverted byte-identical after each

## Gate-Effectiveness Evidence (verbatim from `gh`)

| Cycle | Branch | Break SHA | Run URL | Conclusion | Job outcomes |
|---|---|---|---|---|---|
| A — lint | `ci-proof/lint` | `f8c0d6ebe8abff8830431ae677a03f7f2c0e0212` | https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323395776 | `failure` | `lint: failure`, `typecheck: skipped`, `test: skipped`, `build-push: skipped` |
| B — typecheck | `ci-proof/typecheck` | `eb5f498c0d9877ea4d439f616318f8a1994cc932` | https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323494562 | `failure` | `lint: success`, `typecheck: failure`, `test: skipped`, `build-push: skipped` |
| C — test | `ci-proof/test` | `0ebac981cb211158034b797f66165e9679024966` | https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323571520 | `failure` | `lint: success`, `typecheck: success`, `test: failure`, `build-push: skipped` |
| D — boundary (invalidated first attempt) | `ci-proof/boundary` (PR #5) | `39aa9a24f9036423e6ec3974cad4fab1b027c1ea` | https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323667231 | `failure` | `lint: failure`, others `skipped` — superseded because its failed-step log did not literally contain `check_component_boundary.sh` (see Deviations) |
| D — boundary (final) | `ci-proof/boundary` (PR #6) | `8ed1d891279e3a4d5c0595b96a6b828cb835520e` | https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32323816958 | `failure` | `lint: failure`, `typecheck: skipped`, `test: skipped`, `build-push: skipped`; `gh run view --log-failed` line: `Running scripts/check_component_boundary.sh` (immediately followed by the `VIOLATION:` line) |
| Clean | `ci-proof/clean` (PR #7) | `d8ee6b84e092f78559433098fbbf9b8e0311a0f9` | https://github.com/ToTheHien/nyc-trip-duration-kfp/actions/runs/32324841172 | `success` | `lint: success`, `typecheck: success`, `test: success`, `build-push: success` |

**Positive control:** `TRACER_HEAD_SHA` = `6f4a96925c9c7dd2a2add46260c3e84b84b83f0f` (plan 01-01). `docker manifest inspect ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:6f4a96925c9c7dd2a2add46260c3e84b84b83f0f` exits 0 — the tag derivation demonstrably resolves for a green run.

**Negative proof:** the same command against each of the four break SHAs above (`f8c0d6e...`, `eb5f498...`, `0ebac98...`, `8ed1d89...`) exits non-zero for all four — no image was ever published at any deliberately-broken commit.

**Second positive control (clean run):** `docker manifest inspect ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:d8ee6b84e092f78559433098fbbf9b8e0311a0f9` exits 0 — a second, independent green run resolving under the identical derivation.

**Coverage line (verbatim from run `32324841172`'s `test` job log):**
```
TOTAL              24      0     10      0   100%
Required test coverage of 100% reached. Total coverage: 100.00%
```

**Published image / digest:** `ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:d8ee6b84e092f78559433098fbbf9b8e0311a0f9` @ `sha256:0f051acf3b846851c05a1e0d71d83d69533e0d7684a9435740aa5996509f3b08`

**Anonymous pull/run proof (D-05 = PUBLIC):** `docker logout ghcr.io` → `docker pull` succeeded → `docker run --rm <image> --start-month 2019-11 --end-month 2020-02` printed exactly `2019-11`, `2019-12`, `2020-01`, `2020-02` (4 lines).

**Package visibility (human-confirmed via browser, this dispatch):** the `ingest` GHCR package's visibility is **Public**, matching D-05 as recorded in `01-01-SUMMARY.md`.

## Local pre-commit Verdicts (`pre-commit run --all-files`, per cycle)

| Cycle | `ruff-check` | `ruff-format` | `mypy-strict` | `boundary` | `pytest` | Matches CI? |
|---|---|---|---|---|---|---|
| A | **Failed** (F401 unused `json`) | Passed | Passed | Passed | Passed | Yes — CI failed at `lint` |
| B | Passed | Passed | **Failed** (assignment + operator errors on `suffix`) | Passed | Passed | Yes — CI failed at `typecheck` |
| C | Passed | Passed | Passed | Passed | **Failed** (3 of 6 tests, exclusive-end regression) | Yes — CI failed at `test` |
| D | Passed | Passed | Passed | **Failed** (pandas import in `components/ingest/main.py`) | Passed | Yes — CI failed at `lint` (boundary step) |
| Clean | Passed | Passed | Passed | Passed | Passed | Yes — CI all four jobs `success` |

All five verdicts matched CI exactly, including the test-regression commit (Cycle C) — the direct proof that plan 01-02's D-03a-approved `pytest` hook closes the REQ-A5 gap.

**Git hook survival:** `test -x .git/hooks/pre-commit` and `grep -q 'pre-commit' .git/hooks/pre-commit` both passed after all five cycles — the hook installed by plan 01-02 was never uninstalled; each defect commit used a per-commit `git commit --no-verify` bypass only, after its local verdict was explicitly recorded above.

## Decisions Made

- **Branching override (orchestrator dispatch, not the plan's literal text):** this repository's workflow rule reserves `master` for release-sync points and requires all implementation work to branch from and merge back into `development`. Every `ci-proof/*` branch was created from `development`, every `gh pr create` used `--base development` explicitly, and `ci-proof/clean` was merged into `development` (commit `abd8249`), not `master`. All of the plan's `<default-branch>`-phrased acceptance criteria (`git log <default-branch>`, `git diff <default-branch>`) were evaluated against `development`.
- **Fix `scripts/qa.sh` before redoing Cycle D:** see Deviations below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] `scripts/qa.sh boundary` never identified `check_component_boundary.sh` in CI output**
- **Found during:** Task 1, Cycle D's first attempt (PR #5, run `32323667231`).
- **Issue:** The plan's own acceptance criterion requires `gh run view --log-failed` output to contain the literal string `check_component_boundary.sh` for the boundary-gate cycle. `scripts/qa.sh`'s `boundary)` case (`"$REPO_ROOT/scripts/check_component_boundary.sh"`) delegated silently — the sub-script's own `VIOLATION:` output never named the script itself, so the failing-step log never contained the required string. Confirmed empirically: `gh run view 32323667231 --log` grep for `check_component_boundary` returned zero hits.
- **Fix:** Added a one-line `echo "Running scripts/check_component_boundary.sh"` immediately before the delegation in `scripts/qa.sh`'s `boundary)` case. Committed directly to `development` as a standalone, permanent fix (not part of any break/revert cycle, since it strengthens observability rather than injecting or reverting a defect). Cycle D was then re-run from scratch against the fixed baseline: PR #5/run `32323667231` was closed (superseded, not a false result — its own claims about job-level red/skip were still accurate), and PR #6/run `32323816958` is the run of record, whose log now contains `Running scripts/check_component_boundary.sh`.
- **Files modified:** `scripts/qa.sh`
- **Verification:** `gh run view 32323816958 --log-failed | grep check_component_boundary.sh` returns a match; local `scripts/qa.sh boundary` and `pre-commit run --all-files` on the clean tree both still exit 0/Passed with the new echo present.
- **Committed in:** `1b37d89`

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking issue)
**Impact on plan:** Necessary to satisfy REQ-A6's own literal acceptance criterion; no gate was weakened (the fix only adds an identifying log line, changes no pattern, scope, or rule) and no scope crept beyond what Task 1's acceptance criteria already demanded.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Phase 1 is now fully complete (3/3 plans). Every REQ-A1–REQ-A6 requirement is implemented AND demonstrated on real, `gh`-verified CI runs — not just present in config. `development` is clean (`git status --porcelain` empty aside from the pre-existing, out-of-scope `.gsd/` untracked directory), no `ci-proof/*` branch remains locally or on the remote, and the full local `scripts/qa.sh lint && format && typecheck && test && boundary` chain passes on the merged tree. Phase 2 (`lib/` data & model engineering) can begin against a gate stack proven — not merely asserted — to block bad code at the correct stage.

Remaining pre-existing blocker (carried from 01-01, unaffected by this plan): none — PR #1 was already merged before this plan started, per `git log` (`d5cde00`).

---
*Phase: 01-repo-foundation-ci-quality-gates*
*Completed: 2026-08-20*

## Self-Check: PASSED

- `README.md` exists: FOUND
- `scripts/qa.sh` exists: FOUND
- `.planning/phases/01-repo-foundation-ci-quality-gates/01-03-break-shas.txt` exists, 4 lines: FOUND
- `.planning/phases/01-repo-foundation-ci-quality-gates/01-03-control-sha.txt` exists: FOUND
- Commit `1b37d89` (boundary-echo fix): FOUND in `git log --oneline --all`
- Commit `a5caa20` (break/control SHA evidence): FOUND
- Commit `d8ee6b8` (README parity subsection, on `ci-proof/clean`): FOUND
- Commit `abd8249` (merge PR #7 into `development`): FOUND
- `git status --porcelain` on `development`: clean aside from pre-existing, out-of-scope `.gsd/`
- No `ci-proof/*` branch remains locally or on `origin`: confirmed
- `scripts/qa.sh lint && format && typecheck && test && boundary` on `development` HEAD: all exit 0
