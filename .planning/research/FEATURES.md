# Feature Research

**Domain:** KFP v2 batch ML training pipeline (interview/onboarding-legible skill-proof, not a product)
**Researched:** 2026-08-11
**Confidence:** MEDIUM (KFP mechanics cross-checked against kubeflow.org official docs + SDK readthedocs + GitHub issues; portfolio-credibility claims are directional/LOW — treated as such below)

## Framing Note

This isn't a consumer product, so "users" below means the two audiences that actually evaluate this repo: **a hiring manager/interviewer skimming the code and README**, and **future-you doing a real backfill**. "Table stakes" = missing it makes the repo read as a copy-pasted tutorial. "Differentiator" = signals you've hit and solved a real production concern, not just called an SDK function. "Anti-feature" = the JD doesn't ask for it, or the 16GB/1-week budget can't safely absorb it.

## Feature Landscape

### Table Stakes (Repo Reads as "Tutorial" Without These)

Every KFP getting-started tutorial has a linear DAG of `@dsl.component(packages_to_install=[...])` functions. These are the floor — present in nearly every public KFP example — so their absence (not their presence) is what a reviewer notices.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Multi-stage DAG (ingest→validate→features→train→evaluate) | Minimum shape of "a pipeline" vs a single script | LOW | Already scoped in PROJECT.md |
| Typed artifacts (`Input[Dataset]`, `Output[Model]`, `Output[Metrics]`) | KFP v2's headline feature over v1; raw string paths between components is the #1 "didn't read the v2 docs" tell | LOW–MEDIUM | Declare even output artifacts as function args per KFP convention. Must precede ParallelFor/conditional work — everything downstream depends on artifacts being typed, not stringly-typed |
| `dsl.ParallelFor` fan-out | JD explicitly names batch/Kubeflow; a pipeline that processes one month serially signals "ran the tutorial once" | LOW–MEDIUM | Requires typed artifacts + `dsl.Collected` for fan-in first |
| Pipeline compiled to versioned YAML (IR) | Table stakes for "this is a real deployable artifact," not a notebook | LOW | Already scoped — CI-produced release artifact |
| README with architecture diagram | Minimum bar for "I can explain what I built" in an interview | LOW | Diagram > prose wall; reviewers skim |
| Basic metrics output surfaced via `Output[Metrics]` | KFP UI/lineage is pointless if nothing typed shows up in it | LOW | Feeds the conditional-promotion gate below |

### Differentiators (Prove "I Know KFP," Not "I Ran the Tutorial")

These are the features that separate a copy-paste tutorial repo from one that demonstrates applied judgment. Order below is roughly increasing complexity/signal.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Custom component images via `@dsl.container_component`/`ContainerSpec` pointing at CI-built GHCR tags (not `packages_to_install`) | `packages_to_install` installs pip deps at *runtime* on every execution — fine for a Colab demo, a smell in anything CI-graded. Referencing a pre-built, tested, immutable image tag is the actual production pattern and directly exercises "build component images in CI" from the JD | MEDIUM | Depends on Phase 1's CI image-build pipeline existing first. This is the single highest-signal differentiator in scope — it's the tell reviewers who've run real KFP look for |
| pandera schema validation at ingest boundary | Shows "I know raw data lies" — a `validate` stage that's a no-op passthrough is decorative; one with real `Check`s that reject bad months is not | LOW–MEDIUM | Depends on typed `Dataset` artifact existing to validate against. Use `strict=True` (or explicit column list) so unexpected TLC schema drift (columns TLC has added/renamed across months) fails loud instead of silently passing |
| Vectorized haversine + dtype downcasting + chunked reads, with a before/after benchmark table in README | Directly answers the JD's pandas/numpy ask with *evidence*, not a claim. A benchmark table is unusually rare in portfolio repos — most people vectorize and never prove it mattered | LOW–MEDIUM | The `.apply(axis=1)` → vectorized numpy rewrite is 5–10x+ faster even at ~10k rows and the gap widens with N; that delta is exactly what a benchmark table should show. Downcasting (float64→float32, category dtypes) is the cheapest, highest-ROI memory win and matters concretely on a 16GB box |
| `dsl.If`/`dsl.OneOf` conditional model promotion vs MLflow champion | This is where "orchestration" becomes "MLOps" — proves the pipeline makes a decision, not just executes steps in order | MEDIUM | Depends on Metrics artifact + an MLflow query/comparison step existing first. `OneOf` specifically (not just `If`) is the part most tutorials skip — it's needed to thread a single typed output back out of mutually-exclusive branches, and its correct use is a genuine v2-fluency signal |
| Cache-key invalidation demonstrated (not just enabled) | Anyone can turn caching on. Deliberately changing a component input, re-running, and documenting in the README exactly what invalidated the key (base image hash / command / input value) proves you understand the mechanism instead of trusting a UI checkbox | LOW | No hard dependency, but most illustrative once ≥2 real stages exist to compare |
| Idempotent backfill proof (`start_month`/`end_month` params, byte-identical re-run) | Backfill is the single most-asked "have you actually operated a pipeline" interview question in data/ML eng. A repo that *proves* idempotency (checksum or diff of two runs) rather than asserting it in prose is rare and highly credible | MEDIUM | Requires deterministic, partition-style writes keyed by the month parameter (overwrite by month, not append) — this must be a design decision made *before* writing the ingest/merge components, not bolted on after |
| `ExitHandler` for failure-path cleanup/notification | Most tutorials only show the happy path. An exit handler that fires on failure (not just success) demonstrates you've thought about ops reality, not just the demo run | LOW–MEDIUM | Keep scope tight: log/notify on failure is enough; don't build a full alerting integration (see anti-features). Note KFP limitation — exit task can't consume outputs of in-scope tasks, only `PipelineTaskFinalStatus` |
| `lib/` unit-tested independent of KFP (pandas logic testable without a cluster) | Proves the "thin component / fat lib" architecture wasn't just an aspiration — reviewers can literally run `pytest` without k3d and see the feature logic pass | LOW | Already scoped in Phase 1; listing here because it's what makes several differentiators above *provable* rather than asserted |

### Anti-Features (Do Not Build — Scope/Time/Hardware Reasons)

| Feature | Why It Seems Good | Why Problematic Here | Alternative |
|---------|--------------------|-----------------------|-------------|
| Full multi-user Kubeflow (Istio, auth, multi-tenant profiles) | "More Kubeflow = more credible" | Burns a disproportionate share of the 10–15h budget on cluster plumbing that teaches nothing the JD asks for; Istio debugging alone can eat a full session | KFP standalone on k3d (already decided in PROJECT.md) |
| Hyperparameter tuning (Katib, Optuna sweeps) | Shows "ML sophistication" | Orchestration is the point of this project, not modeling; tuning theater dilutes the pipeline-engineering signal and adds real compute/time cost on a 16GB laptop | Single boring LightGBM config, documented as a deliberate choice in an ADR |
| Real-time/streaming ingestion or serving | Feels "more production" | Out of scope by design (batch JD ask, no serving this milestone); real-time infra is a different skill entirely and not what's being interviewed for | Batch monthly ingest only |
| Full email/Slack/PagerDuty integration on ExitHandler | "Real ops teams get paged" | KFP's ExitHandler can't easily wire external secrets/webhooks without extra infra (SMTP creds, Slack app) — that's a second project, not a pipeline feature | Log-based or local-file notification stub in the exit task; document "next step: wire to Slack" in README |
| Full 2009–present TLC history ingestion | "More data = more realistic" | Infeasible to ingest/backfill on 16GB laptop in a week; doesn't add signal over a bounded window that already spans a real drift event | 12-month window spanning pre/post-COVID collapse (already decided) |
| Custom Kubernetes operators / CRDs for pipeline steps | "Shows deep K8s skill" | Not what KFP or the JD asks for — KFP already abstracts this; hand-rolling operators is orthogonal complexity with a steep learning curve this budget can't absorb | Use KFP's existing container-component abstraction |
| Feature store (Feast, Tecton) | "Feature reuse is a real MLOps concern" | Adds a whole new stateful service to run alongside k3d+MinIO+MLflow on 16GB; the JD doesn't ask for a feature store, and Phase 2's `lib/`-based feature functions already demonstrate the reusable-logic concept without the infra cost | Document as a roadmap extension in README's "next steps" |
| Distributed training (multi-node, Ray, Horovod) | "Scales the story" | LightGBM on 12 months of TLC data (a few GB) doesn't need distributed training; adding it would be pure complexity theater given the model is intentionally "boring" | Single-node LightGBM training component |
| Hand-rolled retry/backoff logic in components | "More resilient" | KFP already has task-level retry policies (`set_retry`); reimplementing this is wasted effort that doesn't demonstrate anything KFP-specific | Use `.set_retry(num_retries=N)` on tasks if retries are wanted at all — likely unnecessary for a local k3d demo |

## Feature Dependencies

```
Custom component images (CI-built GHCR)
    └──requires──> Phase 1 CI image-build/push pipeline

Typed artifacts (Dataset/Model/Metrics)
    └──enables──> ParallelFor fan-out (needs typed Dataset per item to fan out cleanly)
    └──enables──> dsl.Collected fan-in after ParallelFor
    └──enables──> Metrics-driven dsl.If/dsl.OneOf conditional promotion
    └──enables──> pandera validation (validates the Dataset's underlying frame)

ParallelFor fan-out
    └──requires──> Typed artifacts
    └──requires──> Idempotent, partition-keyed ingest/validate components (each iteration must write deterministically by month, or re-runs corrupt merge output)
    └──enables──> merge stage (fan-in via dsl.Collected)

Idempotent backfill (start_month/end_month, byte-identical re-run)
    └──requires──> partition-overwrite design in ingest/merge (deterministic month-keyed writes)
    └──conflicts-if-skipped──> ParallelFor fan-out (non-idempotent per-iteration writes silently break backfill correctness)

Conditional model promotion (dsl.If/dsl.OneOf)
    └──requires──> Metrics artifact from evaluate stage
    └──requires──> MLflow champion-lookup step (compare against tracked best model)
    └──enables──> "prove it" moment for interview narrative (pipeline makes a decision)

Cache-key invalidation demo
    └──requires──> ≥2 pipeline stages with caching enabled to compare before/after

ExitHandler (failure-path cleanup/notification)
    └──wraps──> entire pipeline DAG (outermost scope, added last — easiest to bolt on after the happy-path DAG works)

Vectorized haversine / dtype downcasting / chunked reads + benchmark table
    └──lives in──> lib/ (testable independent of KFP)
    └──enables──> credible pandas/numpy JD-answer with evidence, not claim

lib/ unit tests
    └──requires──> lib/ feature logic extracted from components (Phase 1 architecture decision)
    └──enables──> provability of vectorization claims, pandera schema correctness
```

### Dependency Notes

- **Typed artifacts must land before ParallelFor, conditional promotion, or pandera validation make sense.** Building fan-out or a conditional gate on raw string paths is exactly the "ran the tutorial" pattern this project is trying to avoid — get typed I/O right first, then layer control flow on top.
- **Idempotent, partition-keyed writes must be a design decision *before* ParallelFor is wired**, not retrofitted. If each ParallelFor iteration doesn't write deterministically by month, a second backfill run silently duplicates or corrupts merge output — the bug won't show up until someone actually re-runs a backfill, which is exactly the scenario this feature exists to prove works.
- **Custom component images depend on Phase 1's CI pipeline** already building and pushing images to GHCR — this is the reason Phase 1 (repo/CI quality gates) is correctly sequenced before Phase 2 in the roadmap.
- **ExitHandler is the safest "add last"** — it wraps the outer DAG scope and has no hard dependency on any other differentiator, making it a good buffer-time feature if the week runs short elsewhere.
- **Benchmark table (vectorization) has no pipeline dependency** — it's pure `lib/` work, testable and demonstrable without a running cluster, so it's a good target for early-week momentum before k3d setup friction hits.

## MVP Definition

Given the 2-phase, 1-week/10-15h scope already fixed in PROJECT.md, "MVP" here means the minimum feature set that avoids the project reading as a tutorial, in priority order if time runs short.

### Must Land (non-negotiable for the "not a tutorial" bar)

- [ ] Typed artifacts throughout (Dataset/Model/Metrics) — everything else depends on this
- [ ] Custom component images from CI-built GHCR tags, not `packages_to_install` — single highest-signal differentiator, and it's mostly Phase 1 work paying off
- [ ] `ParallelFor` fan-out with capped parallelism (2–3) — directly the JD's "batch pipelines" ask
- [ ] `dsl.If`/`dsl.OneOf` conditional promotion against MLflow champion — the "pipeline makes a decision" moment
- [ ] Idempotent backfill proof (param-driven, byte-identical re-run check) — highest-value differentiator per hour invested, and the most commonly-asked interview question this repo can pre-answer
- [ ] Vectorized haversine + dtype downcasting + before/after benchmark table — cheapest, most concrete JD-pandas/numpy proof

### Add If Time Permits (v1.x within this same milestone)

- [ ] pandera schema validation with real `Check`s (not passthrough) — do this if ingest boundary is stable early enough to add checks against actual TLC schema quirks
- [ ] ExitHandler failure-path notification — safe to bolt on last since it has no downstream dependents
- [ ] Cache-key invalidation demo + README writeup — quick to demonstrate once ≥2 stages are working, low risk to defer to the final polish pass

### Explicitly Deferred (documented as roadmap extensions, not built this milestone)

- [ ] Serving (KServe), dashboard, recurring/scheduled runs — already out of scope per PROJECT.md
- [ ] Feature store, distributed training, HPO, real-time ingestion — see Anti-Features above

## Feature Prioritization Matrix

| Feature | Interview Signal Value | Implementation Cost | Priority |
|---------|------------------------|----------------------|----------|
| Typed artifacts | HIGH (foundational) | LOW | P1 |
| Custom CI-built component images | HIGH | MEDIUM | P1 |
| ParallelFor fan-out (capped) | HIGH | MEDIUM | P1 |
| Idempotent backfill proof | HIGH | MEDIUM | P1 |
| Conditional promotion (If/OneOf) | HIGH | MEDIUM | P1 |
| Vectorized haversine + benchmark table | HIGH | LOW | P1 |
| dtype downcasting + chunked reads | MEDIUM | LOW | P1 |
| pandera validation (real checks) | MEDIUM | LOW–MEDIUM | P2 |
| Cache-key invalidation demo | MEDIUM | LOW | P2 |
| ExitHandler (failure path) | MEDIUM | LOW–MEDIUM | P2 |
| lib/ unit tests | HIGH (proves everything else) | LOW | P1 (Phase 1, prerequisite) |
| Multi-user Kubeflow / Istio | LOW (misdirected effort) | HIGH | Anti-feature |
| HPO / Katib | LOW (dilutes narrative) | HIGH | Anti-feature |
| Feature store | LOW (out of JD scope) | HIGH | Anti-feature |

**Priority key:**
- P1: Must land for the repo to clear the "not a tutorial" bar
- P2: Should have if the week's time budget allows; safe to defer to polish pass
- Anti-feature: Deliberately excluded — document as "next steps" in README, do not build

## Sources

- [Control Flow — Kubeflow](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/control-flow/) — dsl.If/dsl.Else/dsl.OneOf, dsl.ParallelFor, dsl.ExitHandler semantics (official docs, MEDIUM confidence)
- [kfp.dsl — Kubeflow Pipelines SDK docs](https://kubeflow-pipelines.readthedocs.io/en/latest/source/dsl.html) — SDK reference for dsl module
- [Use Caching — Kubeflow](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/caching/) — cache key composition and invalidation
- [Containerized Python Components — Kubeflow](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/containerized-python-components/) — base_image vs packages_to_install
- [Container Components — Kubeflow](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/container-components/) — dsl.container_component / ContainerSpec pattern
- [Data Types — Kubeflow](https://www.kubeflow.org/docs/components/pipelines/v2/data-types/) — typed artifacts (Dataset/Model/Metrics)
- [Create, use, pass, and track ML artifacts — Kubeflow](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/) — artifact lineage via MinIO + ML Metadata
- [pandera documentation — DataFrame Schemas](https://pandera.readthedocs.io/en/stable/dataframe_schemas.html) and [Checks](https://pandera.readthedocs.io/en/stable/checks.html) — schema validation patterns (official docs)
- [Vectorizing Haversine Distance Calculation in Python](https://www.pythontutorials.net/blog/vectorizing-haversine-distance-calculation-in-python/) and [Vectorized GPS distance/speed calculation for pandas](https://www.tjansson.dk/2021/03/vectorized-gps-distance-speed-calculation-for-pandas/) — vectorization benchmark data
- [Mastering Memory Optimization for Pandas DataFrames](https://thinhdanggroup.github.io/pandas-memory-optimization/) — dtype downcasting and chunked reads guidance
- [Backfilling Historical Data With Idempotent Data Pipelines](https://www.ml4devs.com/what-is/backfilling-data/) and [Designing Robust Data Pipelines: Idempotency, Replays & Backfills](https://medium.com/@manjindersingh_10145/designing-robust-data-pipelines-idempotency-replays-backfills-explained-640c9920f7b9) — idempotent backfill patterns
- Portfolio-credibility framing (table-stakes vs differentiator judgment calls) is this agent's synthesis, informed by general MLOps hiring commentary — treated as LOW-confidence/directional, not sourced from a single authoritative reference; validate against actual JD language and interviewer feedback where possible

---
*Feature research for: KFP v2 batch ML training pipeline (taxi-mlops, Phase 1-2 milestone)*
*Researched: 2026-08-11*
