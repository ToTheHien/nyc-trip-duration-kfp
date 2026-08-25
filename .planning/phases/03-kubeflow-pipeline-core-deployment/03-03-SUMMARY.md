---
phase: 03-kubeflow-pipeline-core-deployment
plan: 03
subsystem: docs
tags: [readme, adr, mermaid, documentation, kfp]

# Dependency graph
requires:
  - phase: 03-kubeflow-pipeline-core-deployment
    plan: 02
    provides: "The full nine-stage compiled DAG (pipelines/train_pipeline.py) and nine components/ directories this plan's diagram and ADR set document"
provides:
  - "README ## Architecture section: rendered mermaid diagram of the real nine-stage DAG, the thin-component/fat-lib tier prose, and the KFP pipeline_root / MLflow+MinIO artifact-store-registry split (REQ-E1)"
  - "README ## Cluster Deployment section: the four deploy/ scripts in execution order with one-line purpose and verification command each, plus the platform-agnostic-overlay and MinIO-memory footguns"
  - "README ## ADRs section: ten ADR entries covering PROJECT.md's four Key Decisions and D-10 through D-13 plus the two Phase 3 design decisions (REQ-E2)"
  - "README ## Next Steps section: explicit deferred-scope statement plus P2-requirement status (REQ-E3)"
  - "tests/test_readme.py: five new regression tests guarding all four new sections, reusing the existing _section_body helper"
  - "PROJECT.md Key Decisions table: all four Outcome cells filled in, each pointing at its README ADR identifier"
affects: [03-04-cluster-deployment, 03-05-pipeline-run-evidence]

actuals:
  tokens: 6420
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "README regression-guard sections: one ## heading + one test_* function reusing _section_body, extended (not duplicated) for Architecture/Cluster Deployment/ADRs/Next Steps exactly as it already existed for Feature Engineering Benchmark/Dataset and Drift Window"
    - "Filesystem-derived assertions in tests/test_readme.py: component/deploy-script names are read from components/ and deploy/ directories rather than hardcoded literal lists, so a renamed or added stage/script makes the guard speak up"

key-files:
  created: []
  modified:
    - README.md
    - tests/test_readme.py
    - .planning/PROJECT.md

key-decisions:
  - "Placed ## Architecture and ## Cluster Deployment immediately after ## Architectural Contract (before ## CI), and ## ADRs/## Next Steps after ## Dataset and Drift Window (before ## Full Plan) - matching the plan's explicit ordering instruction for the first pair and the natural narrative flow (facts before decisions before deferred scope) for the second."
  - "The nine-stage-name filesystem-discovery test filters out __pycache__ (and any other dunder-prefixed directory) from components/'s directory listing - a build artifact, not a pipeline stage - rather than asserting an exact literal count of 9 against the raw listing."
  - "Cluster Deployment section documents scripts/submit_pipeline.py usage and the kubectl get secret credential-readback command even though deploy/ does not exist yet at this plan's commit (03-04 creates it in the same wave) - the section text and its guarding test were both written to match 03-04-PLAN.md's committed script names and behavior exactly, and the test skips cleanly rather than failing until deploy/ exists."

patterns-established:
  - "ADR entries follow a fixed Context/Decision/Consequences shape, one per recorded decision, cross-referencing existing README sections (e.g. ADR-003 points at ## Dataset and Drift Window rather than restating its numbers) instead of duplicating content."

requirements-completed: [REQ-E1, REQ-E2, REQ-E3]

coverage:
  - id: D1
    description: "## Architecture section with a rendered mermaid diagram covering all nine real DAG stages (expand_months, ingest, validate, features, merge, train, evaluate, register, notify), the ParallelFor/Collected/If/ExitHandler control flow, the three-tier thin-component/fat-lib prose, and the KFP pipeline_root / MLflow+MinIO artifact-store-registry split"
    requirement: REQ-E1
    verification:
      - kind: unit
        ref: "tests/test_readme.py::test_architecture_section_contains_a_rendered_diagram"
        status: pass
      - kind: unit
        ref: "tests/test_readme.py::test_architecture_heading_does_not_alias_the_contract_section"
        status: pass
    human_judgment: false
  - id: D2
    description: "## Cluster Deployment runbook naming the four deploy/ scripts in execution order with a verification command each, plus the platform-agnostic-overlay and MinIO-memory-request footguns, with no credential value anywhere in README"
    requirement: REQ-E1
    verification:
      - kind: other
        ref: "grep -Eic credential-pattern README.md -> 0; grep -c platform-agnostic/env-dev README.md -> present"
        status: pass
    human_judgment: false
  - id: D3
    description: "## ADRs section with ten entries: PROJECT.md's four Key Decisions (ADR-001..004) plus D-10..D-13 (ADR-005..008) plus the two Phase 3 design decisions (ADR-009, ADR-010), each with Context/Decision/Consequences"
    requirement: REQ-E2
    verification:
      - kind: unit
        ref: "tests/test_readme.py::test_adr_section_covers_every_recorded_decision"
        status: pass
    human_judgment: false
  - id: D4
    description: "## Next Steps section naming every deferred-scope item from REQUIREMENTS.md's Out of Scope list with its deferral reason, plus a P2-requirement status statement"
    requirement: REQ-E3
    verification:
      - kind: unit
        ref: "tests/test_readme.py::test_next_steps_section_names_deferred_scope"
        status: pass
    human_judgment: false
  - id: D5
    description: "PROJECT.md's Key Decisions table Outcome column filled in for all four rows, each naming its README ADR identifier"
    verification:
      - kind: other
        ref: "grep -c 'Pending' within the Key Decisions table region -> 0; grep -c 'ADR-00' -> 4"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-08-25
status: complete
---

# Phase 3 Plan 3: README Documentation - Architecture, Cluster Deployment, ADRs & Next Steps Summary

**Four new README sections (rendered mermaid architecture diagram, a four-script cluster deployment runbook, ten ADR entries covering every recorded Phase 3 decision, and an explicit deferred-scope statement), each guarded by a standing regression test, plus PROJECT.md's Key Decisions table closed out with cross-referencing outcomes.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-08-25
- **Tasks:** 3 (all executed, no checkpoints)
- **Files modified:** 3 (README.md, tests/test_readme.py, .planning/PROJECT.md)

## Accomplishments

- `## Architecture`: a rendered mermaid flowchart whose node names are the nine real `@dsl.component` functions in `components/`, showing the `ParallelFor` fan-out, `dsl.Collected` fan-in, `dsl.If`-gated `register`, and `notify` as the `ExitHandler` exit path — plus prose on the thin-component/fat-lib tiers and the explicit KFP `pipeline_root` (ephemeral, run-scoped) vs. MLflow+MinIO (durable, queryable-across-runs) artifact-store/registry split, including the separate `backfill` bucket's rationale.
- `## Cluster Deployment`: the four `deploy/` scripts in execution order (named ahead of plan 03-04 landing them, matching its committed filenames exactly), one-line purpose and verification command each, the `env/platform-agnostic`-vs-`env/dev` overlay footgun, the MinIO 16Gi default-memory-request footgun, and the credential-readback command (`kubectl get secret ... -o jsonpath ... | base64 -d`) — no credential value anywhere in the section.
- `## ADRs`: ten `### ADR-NNN` entries in Context/Decision/Consequences form — the four PROJECT.md Key Decisions (ADR-001..004), D-10 through D-13 (ADR-005..008), and the two Phase 3 design decisions locked in 03-01/03-02 (`dsl.If` without `dsl.OneOf`, uniform component style + the `platform-agnostic` overlay choice).
- `## Next Steps`: 13 deferred-scope bullets sourced from `REQUIREMENTS.md`'s Out of Scope list, each with its deferral reason, plus an explicit P2-requirement status statement (all P2 requirements land within this phase; none silently dropped).
- `tests/test_readme.py` extended with five new tests reusing the existing `_section_body` helper, two of them deriving their expected values from the filesystem (`components/`, `deploy/`) rather than a hardcoded list.
- `PROJECT.md`'s Key Decisions table: all four `Pending` outcomes replaced with a one-clause outcome plus the matching README ADR identifier.

## Task Commits

Each task was committed atomically:

1. **Task 1: Architecture section with a rendered diagram, and the cluster deployment runbook** - `a13a9bc` (feat)
2. **Task 2: ADR set and the deferred-scope statement** - `6ec0d7e` (feat)
3. **Task 3: Standing regression tests for the new sections, and PROJECT.md decision outcomes** - `2f04319` (test)

## Files Created/Modified

- `README.md` - `## Architecture`, `## Cluster Deployment`, `## ADRs`, `## Next Steps` sections added
- `tests/test_readme.py` - five new `test_*` functions, module docstring extended to name REQ-E1/E2/E3, `COMPONENTS_DIR`/`DEPLOY_DIR` module-level path constants added
- `.planning/PROJECT.md` - Key Decisions table Outcome column populated for all four rows

## Decisions Made

- **Section placement.** `## Architecture`/`## Cluster Deployment` placed immediately after `## Architectural Contract: Thin Component, Fat Lib` (before `## CI`), per the plan's explicit instruction. `## ADRs`/`## Next Steps` placed after `## Dataset and Drift Window` (before `## Full Plan`) — not explicitly specified by the plan, chosen so ADR-003 can cross-reference the drift-window numbers immediately above it rather than forward-referencing a section not yet read.
- **`__pycache__` filtered out of the filesystem-derived component-name discovery.** The plan's acceptance criteria implicitly assume `components/`'s directory listing yields exactly the nine stage directories; in this checked-out tree `components/__pycache__/` also exists as a build artifact. Filtered by excluding dunder-prefixed directory names rather than hardcoding a count workaround.
- **Cluster Deployment section and its guarding test were written against `deploy/`'s not-yet-existing content**, sourced from `03-04-PLAN.md`'s committed `files_modified` list (`01-cluster-up.sh`, `02-kfp-install.sh`, `03-storage-tracking.sh`, `04-upload-raw-data.sh`) rather than guessed — this plan runs before 03-04 lands `deploy/` in the same wave, so the guarding test (`test_cluster_deployment_section_names_every_deploy_script`) is written to skip cleanly when `deploy/` is absent, exactly as the plan specifies, rather than asserting anything about a directory that does not exist yet.

## Deviations from Plan

None - plan executed exactly as written. The `__pycache__`-filtering adjustment above is a straightforward implementation detail of the plan's own "derive from the filesystem" instruction, not a deviation from it.

## Issues Encountered

- The initial filesystem-derived component-name test failed once (`assert 10 == 9`) because `components/__pycache__/` is present in this checked-out tree from prior test runs. Fixed by excluding dunder-prefixed directory names from the listing before the count assertion, then re-ran `scripts/qa.sh test` to confirm all 148 tests pass.

## User Setup Required

None - no external service configuration required. This plan is documentation-only and cluster-independent by design (its purpose, per the plan's own objective, is to survive intact even if 03-04's cluster install falls back to the safe cut line).

## Next Phase Readiness

- `deploy/` does not exist yet at this plan's commit; `test_cluster_deployment_section_names_every_deploy_script` will start asserting real coverage the moment 03-04 lands that directory in the same wave — no further action needed on this plan's side.
- `## Pipeline Run Evidence` (03-05's deliverable) is the next README section expected; this plan's `## Next Steps` P2-requirement status statement already names it as where REQ-B9/REQ-B10's live-cluster evidence will land, so 03-05 has a pre-established anchor to extend rather than introduce fresh.
- All four PROJECT.md Key Decisions now cross-reference their README ADR entry bidirectionally (ADR prose names the decision; PROJECT.md Outcome names the ADR), so a future reader starting from either document finds the other half of the record.

---
*Phase: 03-kubeflow-pipeline-core-deployment*
*Completed: 2026-08-25*

## Self-Check: PASSED

All 3 modified files (README.md, tests/test_readme.py, .planning/PROJECT.md) verified present on disk with the expected sections/tests/table changes; all three task commits (`a13a9bc`, `6ec0d7e`, `2f04319`) verified present in `git log --oneline --all`.
