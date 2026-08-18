# Phase 1: Repo Foundation & CI Quality Gates - Pattern Map

**Mapped:** 2026-08-14
**Files analyzed:** 12 (scaffold/config files implied by CONTEXT.md decisions D-01..D-04 and REQUIREMENTS.md §Category A)
**Analogs found:** 0 / 12

## Repo State (verified)

This is a **fully greenfield repository**. Confirmed via `find`/`ls` at repo root:

```
./CLAUDE.MD
./.claude/settings.local.json
./.gitignore
./Inital_plan.txt
./.mcp.json
./.planning/**          (docs only: PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, research/)
./path/                 (empty directory)
```

No `pyproject.toml`, no `lib/`, `components/`, `pipelines/`, `serving/`, `dashboard/`, `tests/`, `.github/workflows/`, or `.pre-commit-config.yaml` exist anywhere in the tree. There is no prior commit history containing source code (`git log` shows only planning-doc commits: PROJECT.md, REQUIREMENTS.md, MCP config, roadmap).

**Conclusion:** there are no existing codebase analogs to copy patterns from for this phase. Every file below is a first-of-its-kind for this repo. The planner must derive structure directly from `.planning/research/STACK.md` (pinned versions + install commands) and CONTEXT.md's four locked decisions (D-01..D-04), not from an in-repo analog.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|-----------------|---------------|
| `pyproject.toml` (root, `[tool.uv.workspace]`) | config | batch (dependency resolution) | none | no analog |
| `lib/pyproject.toml` | config | batch | none | no analog |
| `lib/__init__.py` + placeholder module | model/utility | transform | none | no analog |
| `tests/` (pytest suite for `lib/`) | test | batch | none | no analog |
| `.pre-commit-config.yaml` | config | event-driven (git hook) | none | no analog |
| `.github/workflows/ci.yml` | config | event-driven (CI trigger on PR/push) | none | no analog |
| `components/` (thin wrapper skeleton dir + placeholder Dockerfile) | controller (thin wrapper) | request-response (invoked by pipeline) | none | no analog |
| `pipelines/` (skeleton dir) | service/orchestration | event-driven | none | no analog |
| `serving/` (skeleton dir) | service | request-response | none | no analog |
| `dashboard/` (skeleton dir) | component | request-response | none | no analog |
| `README.md` (repo root) | docs | N/A | none | no analog |
| `.gitignore` (extend existing) | config | N/A | `.gitignore` (already exists, 63 bytes) | existing file to extend, not a fresh analog |

## Pattern Assignments

No in-repo pattern assignments are possible — there is nothing to extract excerpts from. Instead, the planner should treat `.planning/research/STACK.md` as the canonical source for concrete setup commands and versions. Key excerpts already vetted by research (reproduced here for convenience so planner doesn't need to re-open STACK.md):

### `pyproject.toml` / uv workspace setup
**Source:** `.planning/research/STACK.md` "Installation" section
```bash
uv init --workspace                                      # once, at repo root
uv add --package lib pandas==2.3.* numpy pyarrow pandera
uv add --package lib --dev pytest pandas-stubs mypy ruff
```
Per CONTEXT.md D-04: define optional-dependency groups (`dev`, `pipeline`, `ml`) in the root `pyproject.toml` now, even if `pipeline`/`ml` start empty/stubbed.

### Tool versions to pin (from STACK.md "Development Tools" table)
- `uv` 0.12.x
- `ruff` 0.16.x
- `mypy` 2.3.x (strict mode scoped to `lib/` only per CONTEXT.md D-02)
- `pytest` 9.1.x
- Python 3.12 (`uv python install 3.12`)

### CI pipeline shape (GitHub Actions)
**Source:** STACK.md "Development Tools" — `docker/build-push-action@v7`, `docker/login-action@v4`, `docker/setup-buildx-action@v4`, with `cache-from: type=gha` / `cache-to: type=gha,mode=max`.

Per CONTEXT.md D-01: the GHCR component image build+push stage runs on **every PR**, not just merge to main — so the workflow trigger should be `pull_request` (not `push: branches: [main]` alone) for the full lint → typecheck → test → build → push chain.

### pre-commit config shape
Per CONTEXT.md D-03: mirror CI exactly — `ruff check`, `ruff format --check`, `mypy --strict` on `lib/` only. No extra hygiene hooks (trailing-whitespace, YAML/TOML validators) — explicitly deferred to minimize setup friction.

## Shared Patterns

None extractable from the codebase (greenfield). The only "shared pattern" for this phase is internal consistency between the three files that must agree on the same check set:
1. `.pre-commit-config.yaml`
2. `.github/workflows/ci.yml`
3. `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]` config blocks)

All three must invoke the same `ruff`/`mypy --strict` scope (`lib/` only) to satisfy CONTEXT.md D-02/D-03 — the planner should treat these three files as a matched set, not independent artifacts.

## No Analog Found

All files in this phase have no existing analog — this is expected and correct for the repo's first phase.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `pyproject.toml` | config | batch | Greenfield repo, no prior Python packaging config exists |
| `lib/pyproject.toml` | config | batch | No `lib/` package exists yet |
| `.pre-commit-config.yaml` | config | event-driven | No git hooks configured yet |
| `.github/workflows/ci.yml` | config | event-driven | No `.github/` directory exists yet |
| `components/*` | controller | request-response | No component scaffolding exists yet (Phase 3 will add real logic) |
| `pipelines/*` | service | event-driven | No pipeline DSL code exists yet (Phase 3) |
| `serving/*`, `dashboard/*` | component/service | request-response | Later-phase concerns; this phase only creates skeleton dirs |
| `tests/*` | test | batch | No test suite exists yet |

**Recommendation for planner:** use `.planning/research/STACK.md` §Installation and §Development Tools as the substitute for "analog code" — those sections contain concrete, version-pinned commands that function as the ground truth for how each config file should be authored, since no in-repo precedent exists.

## Metadata

**Analog search scope:** entire repository root (`find . -maxdepth 3`, excluding `.git/` and `.planning/`)
**Files scanned:** 5 non-planning files at root (`CLAUDE.MD`, `.gitignore`, `Inital_plan.txt`, `.mcp.json`, `.claude/settings.local.json`) — none are code analogs for CRUD/service/controller patterns
**Pattern extraction date:** 2026-08-14
</content>
</invoke>

