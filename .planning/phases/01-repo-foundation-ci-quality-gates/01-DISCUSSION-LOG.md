# Phase 1: Repo Foundation & CI Quality Gates - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-14
**Phase:** 1-Repo Foundation & CI Quality Gates
**Areas discussed:** CI trigger scope, mypy --strict scope, pre-commit hook set, pyproject dependency groups

---

## CI Trigger Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Every PR | Builds/pushes a PR-tagged image on every PR — costs more CI minutes/storage, but proves the full CI pipeline works from day one | ✓ |
| Merge to main only | Cheaper, closer to typical production practice, but image-build stage stays unexercised until first merge | |

**User's choice:** Every PR (Recommended)
**Notes:** None beyond the recommendation rationale.

---

## mypy --strict Scope

| Option | Description | Selected |
|--------|-------------|----------|
| lib/ strict, rest untyped for now | Matches REQ-A2 exactly; components/ and tests/ stay untyped until Phase 3 adds real component code | ✓ |
| lib/ strict + components/tests non-strict | Also runs plain mypy on components/ and tests/ from day one | |

**User's choice:** lib/ strict, rest untyped for now (Recommended)
**Notes:** None.

---

## pre-commit Hook Set

| Option | Description | Selected |
|--------|-------------|----------|
| CI-mirrored only | ruff + mypy --strict on lib/ — exactly mirrors CI, nothing more | ✓ |
| CI-mirrored + hygiene hooks | Adds trailing-whitespace, end-of-file-fixer, YAML/TOML validation, no-large-files | |

**User's choice:** CI-mirrored only (Recommended)
**Notes:** Minimizes setup friction for the 10-15h solo budget.

---

## pyproject Dependency Groups

| Option | Description | Selected |
|--------|-------------|----------|
| Set up groups now | Define dev/pipeline/ml optional-dependency groups now, empty/stub where not yet needed | ✓ |
| Flat list, grow phase by phase | Just dev deps now; add pandas/lightgbm/kfp/mlflow as flat deps when each phase needs them | |

**User's choice:** Set up groups now (Recommended)
**Notes:** Avoids restructuring a flat list later when Phase 2/3 dependencies land.

---

## Claude's Discretion

Repo scaffolding details not explicitly discussed (exact file naming within `lib/`, `.gitignore` entries beyond what's already committed, README skeleton structure) — left to planner/executor judgment, grounded in REQUIREMENTS.md and research/STACK.md.

## Deferred Ideas

None — discussion stayed within Phase 1 scope.
