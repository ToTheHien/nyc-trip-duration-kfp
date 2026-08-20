---
phase: 01
slug: repo-foundation-ci-quality-gates
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-08-20
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| PR author → GitHub Actions runner | Untrusted branch content (including fork branches, on this public repo) is checked out and executed by the workflow | Source code, workflow-triggered secrets access |
| GitHub Actions runner → GHCR | The runner holds a registry-write credential and publishes an artifact consumed later by the Phase 3 cluster | Registry-write token, published image layers |
| PyPI / Docker Hub / GitHub Marketplace → build environment | Third-party code enters the build via `uv sync`, the Docker base image, and `uses:` action references | Third-party package/action code |
| Developer workstation → public git remote | Local content becomes permanently public once pushed (D-05) | Source code, commit history |
| Deliberately broken branch → CI runner | Plan 01-03 intentionally pushes defective code to a public repository | Source code (reverted after proof) |
| GHCR → local Docker daemon | The pull proof deliberately drops credentials to test anonymous access | Registry credentials (cleared) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-01 | Elevation of Privilege | `ci.yml` token scope | high | mitigate | `pull_request` trigger only; top-level `permissions: contents: read`; `packages: write` scoped to `build-push` job only | closed |
| T-01-02 | Information Disclosure | GHCR credential handling | high | mitigate | Auth only via `docker/login-action` with `secrets.GITHUB_TOKEN`; never echoed or passed as build-arg/ENV | closed |
| T-01-03 | Tampering | Third-party Actions via mutable ref | high | mitigate | Every `uses:` pinned to a full-length commit SHA with version comment | closed |
| T-01-SC | Tampering | PyPI/base-image supply chain | high | mitigate | `uv.lock` committed, `uv sync --frozen`; base image pinned by `sha256` digest | closed |
| T-01-05 | Spoofing | Fork PR obtaining registry-write access | high | mitigate | `build-push` guarded on `head.repo.full_name == github.repository` | closed |
| T-01-06 | Information Disclosure | Secrets committed to a public repo | medium | mitigate | `.gitignore` blocks `.env`/`.env.*`/`*.pem`; GitHub secret scanning + push protection enabled | closed |
| T-01-07 | Repudiation | Published image tag untraceable to source commit | medium | mitigate | Tag is full 40-char PR-head SHA (never the ephemeral merge-ref SHA); OCI labels stamped | closed |
| T-01-08 | Denial of Service | Unbounded concurrent workflow runs | low | accept | `concurrency` group with `cancel-in-progress` bounds runs per branch | closed (accepted) |
| T-01-09 | Tampering | Component boundary gate import/method detection | high | mitigate | Statement-boundary regex (`(^\|[;:])`) replaces line-start anchor; dynamic-import detection added; `DataFrame`/`Series` added to method blocklist | closed |
| T-01-10 | Spoofing | Third-party pre-commit mirror repos | medium | mitigate | `repo: local` hooks only; no `repo: https://` entries | closed |
| T-01-11 | Tampering | `qa.sh` / `check_component_boundary.sh` executed by CI and git hooks | medium | mitigate | Plain reviewable shell, `set -uo pipefail`, no network calls | closed |
| T-01-12 | Information Disclosure | README publishing repo internals under public D-05 | low | accept | README documents only layout/install/CI shape, no credentials/endpoints | closed (accepted) |
| T-01-13 | Elevation of Privilege | `ci.yml` refactor widening permissions or unpinning an action | high | mitigate | Regression-guard greps reassert plan 01-01 invariants after every refactor | closed |
| T-01-14 | Tampering | Deliberately broken commit reaching default branch or being published | high | mitigate | Every break lives on a `ci-proof/*` branch, closed unmerged; no image at any break SHA | closed |
| T-01-15 | Repudiation | Gate-effectiveness claims not independently re-checkable | high | mitigate | Every claim cites a real GitHub Actions run URL + `gh`-read conclusion | closed |
| T-01-16 | Elevation of Privilege | Weakening a gate to restore green after a deliberate break | high | mitigate | Reverts are pure removals; every later `scripts/` delta is a strict tightening (CR-01, T-01-09 fixes) | closed |
| T-01-17 | Information Disclosure | `docker logout` clearing a credential relied on elsewhere | low | accept | Local `gh` token carries no package scopes | closed (accepted) |
| T-01-18 | Spoofing | Anonymous pull proof passing via stale cached layer | medium | mitigate | Pull proof runs after `docker logout`, uses `--rm` on the freshly pulled SHA tag | closed |
| T-01-19 | Repudiation | Vacuous negative proof (empty break-SHA loop) | high | mitigate | `01-03-break-shas.txt` committed, non-empty, exactly 4 lines; positive control must resolve first | closed |
| T-01-20 | Elevation of Privilege | Uninstalling the pre-commit git hook to make breaks committable | high | mitigate | Per-commit `--no-verify` bypass instead; hook still installed and wired at phase end | closed |
| T-01-21 | Tampering | Boundary gate's `grep` exit-status handling in rules 3(b)/3(c) treats `rc≥2` as "no violation" instead of "check failed", so a tracked-but-deleted-unstaged file can silently skip the DataFrame-method and `packages_to_install` checks while the gate reports `OK` | medium | mitigate | Not CI-reachable (`actions/checkout` always produces a complete worktree); reachable only locally via pre-commit after an unstaged `rm`. Known fix: mirror rule 3(a)'s `-n "$HITS"` test instead of gating on grep's exit status, in both remaining rules. | **open — below `block_on: high` threshold (non-blocking)** |

*Status: open · closed · open — below `block_on` threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-08 | Public repo has unmetered Actions minutes; `concurrency` group already bounds per-branch runs. Residual risk acceptable for a single-developer portfolio repo. | Developer (D-01 context) | 2026-08-20 |
| AR-02 | T-01-12 | README documents only layout, install command, and CI shape — no credentials, endpoints, or secrets. This is the intended portfolio signal under the public D-05 posture. | Developer (D-05 context) | 2026-08-20 |
| AR-03 | T-01-17 | The `gh` token used in this environment carries no `read:packages`/`write:packages` scopes, so the Docker credential cleared by `docker logout` is not load-bearing for any other workflow. | Developer | 2026-08-20 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open (blocking) | Run By |
|------------|---------------|--------|------------------|--------|
| 2026-08-20 | 20 | 19 | 1 (T-01-09) | gsd-security-auditor (opus) |
| 2026-08-20 | 20 | 20 | 0 | gsd-security-auditor (opus) — re-verified T-01-09 fix at L3 depth (33/33 attack probes caught, 12/12 false-positive guards clean); surfaced new non-blocking T-01-21 |

**T-01-09 remediation:** `scripts/check_component_boundary.sh` — statement-boundary alternation `(^|[;:])[[:space:]]*` replaces the line-start anchor, closing compound-statement, conditional, star-import, and dynamic-import (`__import__`/`importlib.import_module`) bypasses; `DataFrame`/`Series` added to the method-call blocklist. Also added `development` to `ci.yml`'s `push` trigger, since gate-configuration changes were landing on the active integration branch with zero CI coverage — the exact condition that let T-01-09 ship unnoticed. Fixed via PR #8, verified green on all 4 CI jobs, merged to `development` at `fe24fcd`.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed (T-01-21 is open but below `block_on: high`, non-blocking by design)
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-20
