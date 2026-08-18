# Phase 1: Repo Foundation & CI Quality Gates - Context

**Gathered:** 2026-08-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up the monorepo skeleton (`components/`, `pipelines/`, `lib/`, `serving/`, `dashboard/`, `tests/`), `uv` dependency management, `ruff` + `mypy --strict` on `lib/`, `pytest` unit tests, GitHub Actions CI (lint → typecheck → test → build component image → push to GHCR), `pre-commit`, and the thin-component/fat-lib architectural boundary. No pandas/Kubernetes logic yet — this phase proves the quality-gate scaffolding works before any real feature code exists.

</domain>

<decisions>
## Implementation Decisions

### CI Trigger Scope
- **D-01:** The GHCR component image build+push stage runs on every PR (not just merge to main). Rationale: proves the full CI pipeline (lint→typecheck→test→build→push) end-to-end from the very first PR, which matters for a repo whose whole point is demonstrating CI quality gates.

### mypy --strict Scope
- **D-02:** `mypy --strict` runs on `lib/` only, exactly matching REQ-A2. `components/` and `tests/` stay untyped in CI for this phase — avoids type-checking scaffolding/thin-wrapper code that doesn't really exist until Phase 3's components land.

### pre-commit Hook Set
- **D-03:** `pre-commit` config mirrors CI exactly: `ruff` + `mypy --strict` on `lib/`, nothing more. No added hygiene hooks (trailing-whitespace, YAML/TOML validation, etc.) — minimize setup friction for the 10-15h solo budget. — **Amended by D-03a below; read the two together.**
- **D-03a (amendment, ruled 2026-08-18 during Phase 1 plan-checker revision):** A fifth pre-commit hook running the test suite (`scripts/qa.sh test`) is an approved addition on top of D-03's hygiene scope. It was added to make REQ-A5's acceptance criterion — "`pre-commit run --all-files` matches CI pass/fail on the same commit" — literally true rather than merely documented as a known divergence: with only lint and typecheck hooks, a commit whose sole defect is a behavioural regression passes pre-commit and fails CI, and the two verdicts do not match. D-03's "nothing more" is read as scoping the HYGIENE hook set at the time of that decision (excluding trailing-whitespace, end-of-file-fixer, YAML/TOML validators and similar noise, per its stated setup-friction rationale), not as a prohibition on later closing a specific requirement gap. The developer was offered the alternative of amending REQ-A5's wording instead and chose to make pre-commit stricter. Cost is negligible — the `lib/` suite is a handful of pure-function assertions running in well under a second. Implemented in plan 01-02 Task 2 (hook 5, `id: pytest`); demonstrated by plan 01-03 Task 1 Cycle C, where pre-commit fails locally on a behavioural regression exactly as CI does. — **Reversibility:** reversible — removing one hook entry from `.pre-commit-config.yaml` restores D-03's original hook set, at the cost of reopening the REQ-A5 gap.

### pyproject Dependency Groups
- **D-04:** `pyproject.toml` defines optional-dependency groups now (`dev`, `pipeline`, `ml`) even though `pipeline`/`ml` start mostly empty/stubbed. Rationale: Phase 2 (pandas/lightgbm/mlflow) and Phase 3 (kfp) additions get a clear home from day one instead of a flat list needing restructuring later. — **Reversibility:** reversible — restructuring a flat list into groups later is a mechanical pyproject.toml edit, not a breaking change.

### Claude's Discretion
- Exact repo scaffolding details not covered above (file naming within `lib/`, `.gitignore` entries beyond what's already committed, README skeleton structure) are left to planner/executor judgment — REQUIREMENTS.md and research/STACK.md already specify the substantive parts (uv, ruff, mypy, pytest versions).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Scope
- `.planning/REQUIREMENTS.md` §Category A (REQ-A1–A6) — the locked requirements this phase implements
- `.planning/PROJECT.md` — project vision, constraints (10-15h/1 week, 16GB RAM), Key Decisions table

### Research
- `.planning/research/STACK.md` — pinned tool versions (uv, ruff, mypy, pytest, Python 3.12) and setup commands; this phase should follow its recommended versions rather than re-deriving them
- `.planning/research/FEATURES.md` §Table Stakes / §MVP Definition — why `lib/`-first architecture and CI quality gates matter for this project's actual goal (portfolio/interview signal, not just "having CI")

### Roadmap
- `.planning/ROADMAP.md` §Phase 1 — goal statement and success criteria this phase must satisfy

No external specs/ADRs beyond the project's own planning docs — this is a greenfield repo with no prior code.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
None — greenfield repo. Only planning docs and initial commits (`PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, research files) exist on disk.

### Established Patterns
None yet — this phase establishes the first patterns (thin-component/fat-lib boundary, CI shape) that later phases will follow.

### Integration Points
N/A for this phase — nothing to integrate with yet.

</code_context>

<specifics>
## Specific Ideas

No specific implementation ideas beyond the 4 decisions above — user deferred all other Phase 1 mechanics to planner/executor discretion, grounded in REQUIREMENTS.md and research/STACK.md.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope. No scope-creep suggestions arose.

</deferred>

---

*Phase: 1-Repo Foundation & CI Quality Gates*
*Context gathered: 2026-08-14*
