# Project Research Summary

**Project:** nyc-trip-duration-kfp — Batch ML training pipeline on Kubeflow Pipelines v2
**Domain:** Batch ML training pipeline (KFP v2 standalone on k3d, MLflow model registry, portfolio/interview-legible artifact)
**Researched:** 2026-08-11
**Confidence:** MEDIUM

## Executive Summary

This is a portfolio/skill-proof project, not a product: it demonstrates real batch ML orchestration expertise (Kubeflow Pipelines v2, custom CI-built component images, MLflow-gated model promotion) on a 16GB laptop within a 10-15h/1-week budget, for a hiring-manager audience. Experts build this as a monorepo with a strict "thin component, fat lib" boundary — a zero-KFP-dependency `lib/` package holding 100% of pandas/numpy/LightGBM logic (unit-testable without a cluster), thin `components/` wrappers that only shuttle typed KFP artifacts, and a `pipelines/` DAG file that does pure orchestration (`dsl.ParallelFor` fan-out over months, `dsl.Collected` fan-in, `dsl.If`/`dsl.OneOf` conditional promotion against an MLflow champion, `dsl.ExitHandler` for failure-path notification). The recommended stack is KFP SDK/backend 2.17.0 (pinned to match exactly), k3d for the local cluster, a dedicated MinIO pod for MLflow's artifact store, MLflow 3.15.1 with alias-based promotion (`@champion`/`@candidate`), LightGBM for the model, and pandera for ingest-boundary schema validation — all boringly standard choices deliberately avoiding scope-inflating alternatives (full multi-user Kubeflow, HPO frameworks, feature stores, distributed training).

The single biggest risk is resource exhaustion on a 16GB laptop combined with first-time Kubernetes unfamiliarity: k3d's memory flags are advisory, not hard cgroup limits, so uncapped `dsl.ParallelFor` fan-out (12 months = 12 pods) can OOM-kill the whole cluster, not just one pod — mitigated by capping `parallelism=2-3` and setting real per-component resource limits from the start, verified against a known KFP SDK/backend version-mismatch bug (#11390) that silently drops those limits if versions don't match exactly. A second cluster of risks is around "looks done but isn't" traps that are invisible until scale/re-run: non-idempotent backfills (KFP's default run-ID-scoped artifact paths mean two backfill runs never produce a diffable, byte-identical result unless components explicitly write to deterministic, month-keyed paths), cache-key surprises from mutable `:latest` image tags, GHCR image pulls failing inside the cluster despite working via local `docker login`, and MinIO/MLflow endpoint confusion (host-side `localhost` port-forward addresses vs. in-cluster service DNS). All of these are well-documented, avoidable failure modes if addressed as day-one design decisions (parallelism caps, git-SHA image tags, deterministic output keys, in-cluster DNS) rather than retrofits.

The recommended approach sequences work to de-risk the biggest unknown (Kubernetes, the user's stated skill gap) last among the low-risk items: build and fully test 100% of `lib/` logic offline first (ingest, schemas, features with a vectorization benchmark, train, evaluate, registry client), wire CI quality gates early for a visible green badge, then only after that foundation is solid, stand up k3d + KFP + MinIO + MLflow, prove the full chain end-to-end on a single component (ingest) before replicating the pattern across the remaining five, and finish by assembling the full DAG with fan-out/conditional promotion and the two "prove it" demos (cache invalidation, idempotent backfill) as the final polish layer — explicitly the safest work to cut first if time runs short.

## Key Findings

### Recommended Stack

The stack centers on KFP SDK+backend 2.17.0 pinned identically (mismatch causes both "unsupported pipeline spec" errors and, more dangerously, silently-dropped resource limits), running on k3d (lighter than minikube, gives a free local registry mirror) via the standalone kustomize overlay (no Istio/Dex — full multi-user Kubeflow is explicitly rejected as scope-inflating). MLflow 3.15.1 provides experiment tracking and an alias-based model registry (`@champion`/`@candidate` replacing deprecated stage transitions) — the direct mechanism for "register only if RMSE beats champion." A dedicated single-pod MinIO backs MLflow's artifact store (KFP standalone stopped bundling MinIO as of 2.15, now defaults to SeaweedFS — don't assume it's still there). LightGBM 4.7.0 is the "boring, no tuning theater" model; pandera 0.32.1 validates the ingest boundary. `uv` workspace manages the Python monorepo (one lockfile, per-component `pyproject.toml` for minimal Docker images); `ruff`+`mypy --strict`(on `lib/` only)+`pytest` form the CI quality gate. Deliberately deferred: pandas 3.0.x (too new, copy-on-write/string-dtype ecosystem risk not worth taking alongside a first-time-K8s learning curve) — pin pandas 2.3.x instead.

**Core technologies:**
- KFP SDK+backend 2.17.0 — pipeline authoring/orchestration engine; must be version-matched SDK-to-backend
- k3d v5.9.0 — local Kubernetes cluster with a free local registry mirror
- MLflow 3.15.1 — experiment tracking + alias-based model registry for champion/candidate promotion
- MinIO (dedicated pod) — S3-compatible artifact store for MLflow (not the same as KFP's internal SeaweedFS store)
- LightGBM 4.7.0 + pandera 0.32.1 — model training and ingest schema validation
- `uv` + `ruff` + `mypy --strict` + `pytest` — monorepo tooling and CI quality gates

### Expected Features

**Must have (table stakes — repo reads as "tutorial" without these):**
- Multi-stage DAG (ingest→validate→features→train→evaluate)
- Typed artifacts (`Input[Dataset]`, `Output[Model]`, `Output[Metrics]`) — never raw string paths
- `dsl.ParallelFor` fan-out over months
- Pipeline compiled to versioned IR YAML, published as a CI release artifact
- README with architecture diagram

**Should have (differentiators — prove "I know KFP," not "I ran the tutorial"):**
- Custom component images via CI-built GHCR tags, not `packages_to_install` (single highest-signal differentiator)
- `dsl.If`/`dsl.OneOf` conditional promotion against MLflow champion
- Idempotent backfill proof (deterministic month-keyed writes, diffed across two runs) — highest interview-value item
- Vectorized haversine + dtype downcasting + before/after benchmark table (concrete pandas/numpy evidence)
- pandera schema validation with real checks; cache-key invalidation demo; `ExitHandler` failure-path notification

**Defer (v2+/anti-features — explicitly do not build):**
- Full multi-user Kubeflow (Istio/Dex/multi-tenant), HPO/Katib tuning, feature store, distributed training, real-time/streaming ingestion, full alerting integration (Slack/PagerDuty), custom K8s operators/CRDs

### Architecture Approach

Monorepo with three strictly-separated layers: `lib/` (100% of pandas/LightGBM/MLflow-client logic, zero KFP imports, fully unit-tested offline), `components/` (one directory per pipeline stage, each its own Dockerfile/CI-built image, bodies are pure I/O glue: read artifact `.path` → call one `lib/` function → write artifact `.path`/`.metadata`), and `pipelines/` (the `@dsl.pipeline` DAG file wiring components into `ParallelFor`/`Collected`/`If`/`OneOf`/`ExitHandler` control flow, importing only from `components/`, never `lib/` directly). Typed artifacts are the only inter-component contract (never raw S3 path strings). MinIO/KFP's `pipeline_root` is ephemeral per-run plumbing; MLflow is the durable cross-run source of truth for "current champion," queried by `evaluate` and written by `register`.

**Major components:**
1. `lib/` — pandas/numpy/LightGBM logic, pandera schemas, MLflow client wrapper; 100% pytest-covered, cluster-independent
2. `components/` — six thin KFP component wrappers (ingest, validate, features, train, evaluate, register), each its own CI-built GHCR image
3. `pipelines/train_pipeline.py` — DAG assembly: ParallelFor fan-out, Collected fan-in, If/OneOf promotion gate, ExitHandler
4. KFP backend (standalone on k3d) + MinIO + MLflow — the runtime platform, each single-replica/local-dev-sized

### Critical Pitfalls

1. **k3d memory caps are advisory, not hard limits** — host OOM can kill the whole cluster, not just one pod. Set explicit per-component `resources.requests`/`.set_memory_limit()`, budget ~10-11GB usable of the 16GB, keep KFP+MinIO+MLflow as the only always-on services.
2. **KFP SDK/backend version mismatch silently drops resource limits** (confirmed bug #11390) — pin SDK to the exact backend manifest tag, and verify with `kubectl get pod -o yaml` that `resources:` actually landed, don't trust a clean compile.
3. **Unbounded `dsl.ParallelFor`** — no default concurrency cap means a 12-month backfill can spawn 12 simultaneous pods and OOM; pass `parallelism=2` (max 3) from the first version, not retrofitted after a smoke test "worked."
4. **Non-idempotent backfill via KFP's default run-ID-scoped artifact paths** — two identical backfill runs produce two different, non-diffable output paths unless components explicitly write to deterministic, month-keyed target keys. This must be a design decision before the first ingest component is written.
5. **GHCR ImagePullBackOff inside the cluster** despite working local `docker login` — k3d's containerd has separate, empty credential state; make packages public or wire `imagePullSecrets` explicitly, and verify pull-ability from a real pod, not just `docker push` succeeding.

## Implications for Roadmap

Based on combined research, suggested phase structure (aligned with the already-scoped 2-phase, 10-15h/1-week milestone):

### Phase 1: Repo Foundation — `lib/` Logic, CI Quality Gates, Component Images
**Rationale:** De-risks the "is the math/logic right" question fully offline before touching Kubernetes (the stated skill gap); produces the CI image-build pipeline that Phase 2's custom-image differentiator depends on. Low-risk, high-signal work sequenced first for early momentum and a demoable partial artifact even if Phase 2 overruns.
**Delivers:** `uv` workspace skeleton; 100%-unit-tested `lib/` (ingest, pandera schemas, vectorized features + benchmark table, train, evaluate, MLflow registry client wrapper); `ruff`/`mypy --strict`/`pytest` CI gates + pre-commit; per-component Dockerfiles building and pushing git-SHA-tagged images to GHCR, verified pull-able from a bare pod.
**Addresses (FEATURES.md):** `lib/` unit tests (P1 prerequisite), vectorized haversine + benchmark table, dtype downcasting, custom CI-built component images (foundation laid here even if wired into the DAG in Phase 2)
**Avoids (PITFALLS.md):** Pitfall 3 (GHCR ImagePullBackOff — verify pull as a CI-phase exit criterion), Pitfall 6 (cache-key surprises — establish git-SHA image tagging convention now), Pitfall 8 (business logic leaking into component wrappers — enforce the thin-component discipline before any component is written)

### Phase 2: Cluster + Pipeline Assembly — k3d/KFP/MinIO/MLflow, DAG, Promotion Gate
**Rationale:** Only after `lib/` and CI are proven does the highest-risk, least-familiar work (Kubernetes) begin — the previous phase's output remains independently demoable if this phase runs long. Sequenced internally as: cluster/platform up → one component end-to-end (smallest possible proof of the full chain) → remaining components (mechanical repetition) → full DAG assembly (ParallelFor before If/OneOf, since fan-out is more likely to surface resource issues) → "prove it" demos last (cache invalidation, idempotent backfill), which are safe to compress or cut if time runs short.
**Delivers:** k3d cluster + KFP standalone + dedicated MinIO + MLflow reachable; full `train_pipeline.py` DAG (ParallelFor fan-out capped at parallelism=2-3, Collected merge, If/OneOf champion-gated promotion, ExitHandler notification); deterministic month-keyed idempotent backfill; documented cache-invalidation demo; README with architecture diagram and benchmark table.
**Uses (STACK.md):** KFP 2.17.0 SDK+backend (exact match), k3d v5.9.0, dedicated MinIO pod, MLflow 3.15.1 with alias-based promotion, SQLite backend store for MLflow
**Implements (ARCHITECTURE.md):** Thin component/fat lib pattern; typed artifacts as sole cross-component contract; ParallelFor+Collected fan-out/fan-in; If/OneOf+ExitHandler conditional promotion and cleanup
**Avoids (PITFALLS.md):** Pitfall 1 (k3d memory not a hard cap — set resource requests, budget conservatively), Pitfall 2 (SDK/backend version mismatch — pin and verify via `kubectl get pod -o yaml`), Pitfall 4 (unbounded ParallelFor — cap `parallelism` in the same commit as the loop), Pitfall 5 (non-idempotent backfill — deterministic keys designed before first ingest component), Pitfall 7 (MinIO/MLflow storage collision — reuse one MinIO instance, in-cluster DNS not localhost)

### Phase Ordering Rationale

- **Offline-before-cluster ordering directly follows the risk profile in PITFALLS.md and ARCHITECTURE.md's suggested build order**: Kubernetes is the stated skill gap and highest-risk unknown, so everything that can be proven without a cluster (`lib/` logic, CI gates, image builds) is front-loaded, leaving a defensible, demoable partial artifact even under time pressure.
- **Custom component images (a Phase 2 differentiator) structurally depend on Phase 1's CI pipeline already existing** — FEATURES.md's dependency graph makes this explicit, confirming the 2-phase split.
- **Within Phase 2, idempotent-backfill design (deterministic keys) must precede ParallelFor wiring**, not follow it — both FEATURES.md and PITFALLS.md independently flag this as a "decide before writing the first ingest component" constraint, since retrofitting deterministic keys after ParallelFor is wired risks silent data corruption on re-run.
- **Conditional promotion (If/OneOf) is sequenced after ParallelFor**, not before, because fan-out is more likely to surface resource/parallelism issues — better to hit that complexity with a simpler downstream tail still to build.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (cluster install):** k3d + KFP standalone install path is genuinely thin/LOW-confidence in current research (community issue threads, not an authoritative install guide) — spike early to validate the exact install sequence and confirm SeaweedFS-vs-MinIO defaults for the pinned KFP version before committing time.
- **Phase 2 (MLflow/MinIO wiring):** Endpoint/credential configuration (in-cluster DNS vs. host port-forward) is a common, easy-to-hit gotcha (Pitfall 7) — worth a focused pre-check before wiring the `register`/`evaluate` components.

Phases with standard patterns (skip research-phase):
- **Phase 1:** `lib/` architecture, CI quality gates, and Docker/GHCR build-push patterns are HIGH-confidence, well-documented, standard 2025/2026 patterns (uv workspace, ruff/mypy/pytest, docker/build-push-action) — no additional research needed.
- **Phase 2 (DAG control flow):** KFP v2 SDK semantics (`ParallelFor`, `Collected`, `If`/`OneOf`, `ExitHandler`, typed artifacts) are HIGH-confidence, directly sourced from official Kubeflow docs — implement directly from ARCHITECTURE.md's worked examples.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Version numbers verified live against PyPI/GitHub during this session but not cross-checked against a second registry mirror; treat exact patch versions as a snapshot to re-verify at `uv add` time |
| Features | MEDIUM | KFP mechanics cross-checked against official docs/SDK reference (HIGH); portfolio-credibility/table-stakes-vs-differentiator judgment is directional synthesis, explicitly flagged LOW-confidence by the researcher |
| Architecture | MEDIUM | KFP v2 SDK semantics are HIGH confidence (official docs); k3d resource behavior and the exact "standalone on k3d" install path are LOW confidence (community threads, not authoritative) — flagged for a Phase 2 spike |
| Pitfalls | MEDIUM-HIGH | KFP/k8s mechanics are HIGH confidence (official docs + confirmed GitHub issues, e.g. #11390); exact behavior on this project's specific k3d/KFP version combo is unverified until Phase 1/2 install |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Exact k3d + KFP standalone install sequence for the pinned 2.17.0 version** is not authoritatively verified (community sources only) — validate with a timeboxed spike at the start of Phase 2 before building anything on top of it.
- **Whether KFP 2.17.0's standalone manifests bundle MinIO or default to SeaweedFS** needs a direct check against the manifest tree at install time (STACK.md notes MinIO was dropped as of 2.15) — confirms whether a dedicated MinIO pod for MLflow is additive or the only object store present.
- **Exact patch versions for all pinned packages** (kfp, mlflow, lightgbm, pandera, pandas, numpy, uv, ruff, mypy, pytest) should be re-verified with `uv add <pkg>` / `pip index versions <pkg>` at implementation time rather than trusted as hard pins from this research pass.
- **RAM headroom in practice** (16GB laptop running k3d + KFP's ~10-12 pods + MinIO + MLflow + task pods) is reported as right at the community-cited minimum threshold — treat the `parallelism=2-3` recommendation as a starting point to tune empirically during Phase 2, not a guaranteed-safe number.

## Sources

### Primary (HIGH confidence)
- kubeflow.org official docs — Control Flow, Containerized/Container Components, Data Types, Artifacts, Caching, Pipeline Root
- github.com/kubeflow/pipelines — releases, manifests/kustomize tree at tag 2.17.0, confirmed issue #11390 (resource limit key mismatch)
- PyPI package pages (live fetch) — kfp, mlflow, pandera, lightgbm, pandas, numpy, uv, ruff, mypy, pytest

### Secondary (MEDIUM confidence)
- mlflow.org docs — MLflow 3 breaking changes, model registry alias workflow
- pandas.pydata.org — Pandas 3.0 release notes / what's-new
- General MLOps/idempotent-backfill pattern write-ups (ml4devs, dev.to, Medium) — cross-referenced across multiple sources
- GitHub Actions Docker build-push patterns, dorny/paths-filter — well-established open-source patterns

### Tertiary (LOW confidence)
- blog.min.io KFP+MinIO setup post — predates the KFP 2.15 SeaweedFS migration, pattern-confirmation only
- kubeflow/website issue #2209, yuhuishi-convect/local-k3d-ml, k3d-io/k3d discussion #627 — community threads on k3d-specific install/resource behavior, not authoritative; flagged for Phase 2 spike validation
- Portfolio-credibility/table-stakes-vs-differentiator framing in FEATURES.md — this agent's own synthesis, not sourced from a single authoritative reference

---
*Research completed: 2026-08-11*
*Ready for roadmap: yes*
