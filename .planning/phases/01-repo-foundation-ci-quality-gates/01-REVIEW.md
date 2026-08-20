---
phase: 01-repo-foundation-ci-quality-gates
reviewed: 2026-08-20T02:48:21Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - components/ingest/Dockerfile
  - components/ingest/__init__.py
  - components/ingest/main.py
  - components/__init__.py
  - dashboard/.gitkeep
  - .github/workflows/ci.yml
  - .gitignore
  - lib/__init__.py
  - lib/months.py
  - .mcp.json
  - pipelines/.gitkeep
  - .pre-commit-config.yaml
  - pyproject.toml
  - .python-version
  - README.md
  - scripts/check_component_boundary.sh
  - scripts/qa.sh
  - serving/.gitkeep
  - tests/__init__.py
  - tests/lib/__init__.py
  - tests/lib/test_months.py
  - uv.lock
---

# Phase 01: Code Review Report

**Reviewed:** 2026-08-20T02:48:21Z
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

This phase's stated purpose is to prove the quality-gate stack (lint, type-check, test, boundary gate, CI, pre-commit) end-to-end on the smallest possible real surface. `lib/months.py` and its tests are correct and well covered. The CLI wrapper (`components/ingest/main.py`) and `Dockerfile` are simple and largely sound.

The most significant finding is in the boundary-gate script itself (`scripts/check_component_boundary.sh`), which is the one piece of this phase explicitly billed (in `README.md`) as mechanical, non-review-dependent enforcement of the architectural contract ("thin component, fat lib"). The regex used to catch plain `import pandas`/`import numpy` statements is end-anchored to the line, so any trailing content after the import — a `# noqa` comment, a second statement separated by `;`, a comma-separated second import — silently defeats the check. This was verified empirically (see finding CR-01). Because this is the exact mechanism the phase exists to validate, it is a Blocker.

Two additional Warnings concern the CI workflow: the `build-push` job tags images with the PR head SHA but (by default) builds from the checkout of the PR merge commit, so the tag does not always describe the tree that was actually built; and the container Dockerfile has no `USER` directive, so the published component image runs as root by default.

## Critical Issues

### CR-01: Component boundary gate's import check can be silently bypassed with trailing content on the import line

**File:** `scripts/check_component_boundary.sh:30`
**Issue:** `IMPORT_RE`'s plain-`import` alternative end-anchors the match to the line (`...([[:space:]]+as[[:space:]]+[A-Za-z_][A-Za-z0-9_]*)?[[:space:]]*$`). Any content after the import statement on the same physical line — a trailing comment, a `; import os`, or a comma-separated `import numpy, pandas` — prevents the alternative from matching, so `grep` reports no hit and the gate passes even though a forbidden import is present. This directly undermines the stated guarantee in `README.md` ("This is enforced mechanically, not by review discipline") for the one violation class (data-library imports) the gate exists to catch.

Verified empirically:
```
$ printf 'import pandas  # noqa: F401\ndf.head()\n' > components/ingest/_evil.py
$ scripts/check_component_boundary.sh
OK: boundary gate passed - ...   # false pass; pandas import present but undetected
```
(The `from pandas import ...` form is unaffected — its regex alternative has no trailing `$` anchor — only the plain `import pandas[.sub][ as alias]` form is exploitable.)

**Fix:** Drop the end-of-line anchor and instead require a word boundary / non-identifier character (or end of line) after the module name, and don't require the whole rest of the line to be consumed:
```bash
IMPORT_RE='^[[:space:]]*(import[[:space:]]+(pandas|numpy)([.,[:space:]]|$)|import[[:space:]]+[A-Za-z0-9_, ]*\b(pandas|numpy)\b|from[[:space:]]+(pandas|numpy)(\.[A-Za-z0-9_.]*)?[[:space:]]+import[[:space:]]+)'
```
or more robustly, drop the hand-rolled `$`-anchored form entirely and match on `\bimport\b.*\b(pandas|numpy)\b` scoped to the start of a logical import statement, then add a regression test file under a throwaway fixture that exercises `import pandas  # comment` and `import numpy, pandas` to prevent this regressing again.

## Warnings

### WR-01: `build-push` job can tag an image with a SHA that does not match the tree it built

**File:** `.github/workflows/ci.yml:52-69`
**Issue:** On `pull_request` events, `actions/checkout` (line 55, no `ref:` given) checks out the default `GITHUB_SHA` for that event — the ephemeral merge commit (`refs/pull/<n>/merge`), not the PR head commit. But `IMAGE_TAG` (line 53) is computed as `github.event.pull_request.head.sha || github.sha`, i.e. it uses the **head** commit SHA on PR runs. For a same-repo PR (the only case where `build-push` runs per the `if:` guard on line 47), the image actually built comes from the merge-commit tree (head merged into current base), while the pushed tag names the head commit alone. If `master`/`development` has moved since the PR branch was last rebased, the image content and its tag diverge — the tag no longer uniquely/accurately identifies what was built, contradicting the traceability claim in `README.md` ("tags the built image with the full 40-character SHA of the source commit that built it").
**Fix:** Explicitly pin checkout to the tag being used, so build input and tag always agree:
```yaml
- uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
  with:
    ref: ${{ github.event.pull_request.head.sha || github.sha }}
```

### WR-02: Ingest component image has no `USER` directive — runs as root

**File:** `components/ingest/Dockerfile:1-13`
**Issue:** The image is built `FROM python:3.12-slim` and never switches away from the default root user before `ENTRYPOINT`. The published, publicly-pullable GHCR image (per `README.md`'s D-05 public-visibility rationale) therefore runs the component's Python process as root inside its container by default when scheduled as a Kubernetes pod, unless every consumer remembers to set `runAsNonRoot`/`securityContext` at the pod-spec level. This is a defense-in-depth gap, not exploitable purely from this file, but it's a standard hardening step that costs nothing here since the entrypoint needs no root privileges (no package installs, no privileged ports, no writes outside `/app`).
**Fix:**
```dockerfile
WORKDIR /app
COPY lib/ /app/lib/
COPY components/ingest/main.py /app/main.py
ENV PYTHONPATH=/app
RUN useradd --no-create-home --uid 1000 appuser
USER appuser

ENTRYPOINT ["python", "/app/main.py"]
```

## Info

### IN-01: CI `push` trigger only watches `master`, never `development`

**File:** `.github/workflows/ci.yml:4-7`
**Issue:** `on.push.branches` lists only `master`. Per the project's branching rule (`.claude/rules/requirements.md`), `development` is the active integration branch that all feature branches merge back into. A direct/fast-forward merge into `development` (e.g. via `git merge` outside of a GitHub PR merge, or a squash-merge that GitHub performs as a single push) produces a `push` event on `development` that this workflow will not run against — only the `pull_request` event (opened/synchronize, prior to merge) exercises those commits. This means `development` itself has no guaranteed post-merge CI signal independent of what ran on the PR branch.
**Fix:** Consider adding `development` to `on.push.branches` if a fresh integration-branch signal (as opposed to relying solely on pre-merge PR checks) is desired:
```yaml
on:
  pull_request:
  push:
    branches:
      - master
      - development
```

### IN-02: Docker build context is the entire repository; no `.dockerignore`

**File:** `components/ingest/Dockerfile` (build invoked with `context: .` in `.github/workflows/ci.yml:66`)
**Issue:** There is no `.dockerignore`, so the full build context sent to the Docker daemon includes `.git/`, `.planning/`, `uv.lock`, and everything else in the repo root, even though only `lib/` and `components/ingest/main.py` are ever `COPY`'d. Currently harmless (nothing sensitive is copied into the image), but it's a footgun if a future `COPY . .`-style edit is made without someone re-checking what's in scope.
**Fix:** Add a `.dockerignore` scoping the context to what's actually needed (`lib/`, `components/`, and excluding `.git`, `.planning`, `tests`, `*.md`).

---

_Reviewed: 2026-08-20T02:48:21Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
