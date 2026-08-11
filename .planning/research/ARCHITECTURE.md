# Architecture Research

**Domain:** Batch ML training pipeline on Kubeflow Pipelines v2 (standalone, on k3d)
**Researched:** 2026-08-11
**Confidence:** MEDIUM (KFP v2 SDK semantics are well-documented and stable/HIGH; k3d resource behavior and exact "standalone on k3d" install path are thinner/LOW — validate with a spike early in Phase 2)

## Standard Architecture

### System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│  Monorepo (this repo)                                               │
│  ┌───────────┐   ┌───────────┐   ┌──────────────────────────────┐  │
│  │  lib/     │◄──┤components/│◄──┤ pipelines/train_pipeline.py   │  │
│  │ (pandas   │   │ (thin CLI │   │ (dsl.pipeline DAG definition, │  │
│  │  logic,   │   │  wrappers,│   │  compiled to YAML)            │  │
│  │  100%     │   │  1 per    │   └──────────────────────────────┘  │
│  │  unit     │   │  stage,   │                                     │
│  │  tested)  │   │  own      │                                     │
│  │           │   │  Dockerfile)                                    │
│  └───────────┘   └───────────┘                                     │
├────────────────────────────────────────────────────────────────────┤
│  CI (GitHub Actions)                                                 │
│  lint(ruff) → typecheck(mypy) → test(pytest) → build+push(GHCR)     │
│  → compile pipeline YAML → attach as release artifact               │
├────────────────────────────────────────────────────────────────────┤
│  k3d cluster (local, 16GB laptop)                                    │
│  ┌─────────────────────┐  ┌─────────┐  ┌────────────────────────┐  │
│  │ KFP standalone       │  │  MinIO  │  │  MLflow tracking +     │  │
│  │ (API server, driver, │  │ (S3-    │  │  model registry        │  │
│  │  launcher, Argo/     │  │ compat  │  │  (backed by MinIO for  │  │
│  │  Workflows engine,   │  │ artifact│  │   artifacts, sqlite/   │  │
│  │  MySQL metadata)     │  │ store)  │  │   Postgres for meta)   │  │
│  └──────────┬───────────┘  └────┬────┘  └───────────┬────────────┘  │
│             │  each task pod pulls its component image from GHCR    │
│             │  writes/reads typed artifacts via pipeline_root       │
│             └────────────────────┴──────────────────────┘           │
└────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|-------------------------|
| `lib/` | All pandas/numpy logic: parsing, schema validation, feature engineering, training, evaluation. Zero KFP imports. | Plain Python package, pandera schemas, pytest with tiny synthetic DataFrames, 100% coverage target |
| `components/` | One thin module per pipeline stage (ingest, validate, features, train, evaluate, register). Each: reads typed KFP artifact paths → calls one `lib/` function → writes typed KFP artifact paths. | `@dsl.component(base_image=...)` or `@dsl.container_component` functions; no business logic, only I/O plumbing + artifact metadata (e.g. `model.metadata["rmse"] = ...`) |
| `pipelines/` | Wires components into the DAG: sequencing, `ParallelFor` fan-out, `If`/`OneOf` branching, `ExitHandler`, caching config. | `@dsl.pipeline` function compiled via `kfp.compiler.Compiler()` to a YAML `PipelineSpec` |
| MinIO | S3-compatible object store backing the KFP `pipeline_root` — where every `Input[...]`/`Output[...]` artifact's actual bytes (Parquet, joblib/pickle model, JSON metrics) live. | In-cluster deployment, one bucket (e.g. `mlpipeline`), referenced via `minio://` or `s3://` URI in the `kfp-launcher` ConfigMap |
| MLflow | Model registry + experiment tracking — the durable "champion" record that pipeline runs read to decide promotion, and write to on promotion. | Tracking server + registry backed by MinIO for artifact storage; queried/written from inside the `evaluate`/`register` components, not by KFP itself |
| GHCR | Distribution point for the 5-6 component images CI builds. KFP task pods pull images from here at run time. | `ghcr.io/<org>/<repo>/<component-name>:<tag>` per component, built by a matrix CI job |

## Recommended Project Structure

```
mlops/
├── lib/                        # 100% unit-tested pandas/numpy logic, zero KFP deps
│   ├── ingest.py                # read raw TLC parquet for a given month
│   ├── schemas.py               # pandera schemas (raw + validated)
│   ├── features.py              # vectorized haversine, dtype downcast, feature build
│   ├── train.py                 # LightGBM fit given a features DataFrame
│   ├── evaluate.py               # RMSE + comparison-vs-champion logic
│   └── registry.py              # thin MLflow client wrapper (register, get champion)
├── components/                  # one dir per KFP component = one image
│   ├── ingest/
│   │   ├── Dockerfile
│   │   ├── component.py          # @dsl.component, calls lib.ingest
│   │   └── main.py               # optional CLI entrypoint if using container_component
│   ├── validate/
│   ├── features/
│   ├── train/
│   ├── evaluate/
│   └── register/
├── pipelines/
│   └── train_pipeline.py        # @dsl.pipeline DAG: the ParallelFor + If/OneOf assembly
├── serving/                     # out of scope this milestone (stub/README only)
├── dashboard/                   # out of scope this milestone (stub/README only)
├── tests/
│   ├── lib/                     # unit tests, one file per lib module
│   └── pipelines/               # optional: compile-time DAG shape assertions
├── .github/workflows/
│   └── ci.yml                   # lint → typecheck → test → build/push → compile
└── pyproject.toml               # uv-managed, single workspace
```

### Structure Rationale

- **`lib/` has zero KFP imports.** This is what makes 100% unit testing cheap and fast — tests run in plain `pytest` with no cluster, no Docker, no KFP SDK compile step. It is also what makes each component's Dockerfile small (component images don't need the full KFP SDK compiler toolchain, only `kfp` runtime + `lib/` + component-specific deps).
- **One directory per component under `components/`** because each becomes an independently built/tagged/pushed Docker image in CI. A flat `components.py` file would force all components to share one image, defeating the point of demonstrating per-component image builds and cache-key isolation (changing `train/` shouldn't bust `ingest/`'s cache).
- **`pipelines/` only imports from `components/`**, never from `lib/` directly — the DAG file should only reason about artifact wiring and control flow, not pandas logic. This boundary is what lets you review the DAG file as "pure orchestration" in an interview/portfolio context.
- **`tests/` mirrors `lib/`, not `components/`.** Component wrapper logic is intentionally too thin to need unit tests beyond a smoke test; the value-bearing logic lives in `lib/` and gets tested there.

## Architectural Patterns

### Pattern 1: Thin component, fat lib

**What:** Every `@dsl.component`/`@dsl.container_component` function body is I/O glue only: read `.path` off typed artifact inputs, call exactly one `lib/` function, write results to `.path`/`.metadata` of typed artifact outputs. No pandas logic inside `components/`.
**When to use:** Always, for this project — it's an explicit repo constraint (`lib/` = 100% of pandas/feature logic).
**Trade-offs:** Slightly more indirection than inlining logic in the component; pays off because `lib/` tests run in <1s with no cluster, and component images can be minimal (fewer deps = smaller image = faster CI + faster pod pulls on a resource-constrained cluster).

**Example:**
```python
# components/features/component.py
from kfp import dsl
from kfp.dsl import Input, Output, Dataset

@dsl.component(
    base_image="ghcr.io/ORG/REPO/features:latest",  # pre-built, CI-pushed image
)
def build_features(
    validated: Input[Dataset],
    features: Output[Dataset],
) -> None:
    from lib.features import build_feature_frame
    import pandas as pd

    df = pd.read_parquet(validated.path)
    out = build_feature_frame(df)          # 100% unit-tested pure function
    out.to_parquet(features.path)
    features.metadata["n_rows"] = len(out)
```

### Pattern 2: Typed artifacts as the only cross-component contract

**What:** Components never pass raw strings (S3 keys, bucket names) as parameters. They declare `Input[Dataset]`, `Output[Dataset]`, `Output[Model]`, `Output[Metrics]` and let the KFP launcher resolve `.path` to the actual `pipeline_root`-relative MinIO location. Scalar metadata (row counts, RMSE, month string) rides on `artifact.metadata[...]` or plain typed pipeline parameters (`str`, `float`), never smuggled into artifact bytes.
**When to use:** Every inter-component data handoff in `pipelines/train_pipeline.py`.
**Trade-offs:** Slightly more ceremony than "just pass a path string" — but it's precisely what makes lineage, caching, and the KFP UI's artifact graph work, and it's an explicit project requirement ("no raw S3 path strings").

**Example:**
```python
from kfp import dsl
from kfp.dsl import Dataset, Model, Metrics, Input, Output

@dsl.component(base_image="ghcr.io/ORG/REPO/evaluate:latest")
def evaluate(
    model: Input[Model],
    test_features: Input[Dataset],
    metrics: Output[Metrics],
) -> float:                      # scalar output usable by dsl.If downstream
    from lib.evaluate import score_model
    import joblib, pandas as pd

    m = joblib.load(model.path)
    df = pd.read_parquet(test_features.path)
    rmse = score_model(m, df)
    metrics.log_metric("rmse", rmse)
    return rmse
```

### Pattern 3: ParallelFor fan-out + dsl.Collected merge

**What:** `dsl.ParallelFor(months) as month:` runs `ingest`+`validate`+`features` once per month as independent, cacheable, independently-retriable tasks. `dsl.Collected(features_task.outputs['features'])` gathers the per-month `Dataset` artifacts into a `List[Dataset]` consumed by a single downstream `merge_features` task before training. This is the current (KFP v2 GA), backend-supported replacement for manually threading artifact lists — confirmed against the official Kubeflow control-flow docs (2026).
**When to use:** The `ingest → validate → features` stage per month, capped with `parallelism=N` (start at 2-3 on a 16GB laptop; tune up only if the cluster has headroom).
**Trade-offs:** Each loop iteration is a full pod (scheduling/image-pull overhead) — on constrained hardware, over-parallelizing thrashes the node more than it saves wall-clock time. Nested nested nested loops flatten artifact lists but nest parameter lists — irrelevant here since this DAG only loops one level over months.

**Example:**
```python
from kfp import dsl
from kfp.dsl import Dataset

@dsl.pipeline
def train_pipeline(months: list, parallelism: int = 2):
    with dsl.ParallelFor(months, parallelism=parallelism) as month:
        ingest_task = ingest(month=month)
        validate_task = validate(raw=ingest_task.outputs["raw"])
        features_task = build_features(validated=validate_task.outputs["validated"])

    merged = merge_features(
        parts=dsl.Collected(features_task.outputs["features"])
    )
    trained = train(features=merged.outputs["merged"])
    evaluated = evaluate(model=trained.outputs["model"], test_features=merged.outputs["merged"])

    with dsl.If(evaluated.outputs["rmse"] < champion_rmse, "beats-champion"):
        register(model=trained.outputs["model"], metrics=evaluated.outputs["metrics"])
```

### Pattern 4: If/OneOf conditional promotion, wrapped in ExitHandler

**What:** `dsl.If(challenger_rmse < champion_rmse)` gates the `register` task. Because only one branch may run, if the pipeline also needs a "no promotion" output message downstream, wrap both branches (`If`/`Else`) and collect with `dsl.OneOf` into one channel. Wrap the whole pipeline body in `dsl.ExitHandler(notify_task)` so a notification/cleanup component runs on both success and failure paths (use `PipelineTaskFinalStatus` input on the exit task to branch its message on pass/fail).
**When to use:** Model promotion decision (registration should never be unconditional) and end-of-run notification/cleanup (explicit project requirement: failure path, not just happy path).
**Trade-offs:** `ExitHandler` adds one more image/component to build (can be a very small one — e.g. write a JSON summary to a known path, or `print()` a structured log line for the demo). Don't over-invest here: a single lightweight `notify` component satisfies the requirement without needing real alerting infra (Slack/email) for a portfolio project.

## Data Flow

### Training Run Flow

```
months param (list[str], e.g. ["2019-01", ..., "2020-01"])
    ↓ dsl.ParallelFor(parallelism=2-3)
  ingest(month) → Output[Dataset] raw            [MinIO: .../ingest-<month>/raw]
    ↓
  validate(raw) → Output[Dataset] validated        [pandera schema check; fails loudly on bad month]
    ↓
  build_features(validated) → Output[Dataset] features [vectorized haversine, dtype downcast]
    ↓ dsl.Collected(...)
  merge_features(parts: List[Dataset]) → Output[Dataset] merged
    ↓
  train(merged) → Output[Model] model, Output[Metrics] train_metrics
    ↓
  evaluate(model, merged/test-split) → Output[Metrics] eval_metrics, float rmse
    ↓ dsl.If(rmse < champion_rmse)
  register(model, eval_metrics) → writes to MLflow Model Registry
    ↓ (always, via ExitHandler)
  notify(status) → summary of run result
```

### Artifact Store / Registry Split

```
KFP pipeline_root (MinIO, s3://mlpipeline/...)      MLflow (tracking + registry, MinIO-backed)
├── per-run, per-task artifact bytes                ├── experiment runs (params, metrics, per-run)
│   (Parquet datasets, joblib model, metrics.json)  ├── registered model versions + aliases
│   — ephemeral/run-scoped, addressed by KFP         │   (e.g. @champion, @candidate)
│   via typed artifact URIs                          └── durable/queryable across runs — this is
└── lineage: KFP UI graph, driven by artifact              what `evaluate`/`register` query to find
    input/output edges between tasks                       "the current champion RMSE"
```

Key distinction: MinIO/`pipeline_root` is KFP's own working storage for a single run's intermediate data — treat it as ephemeral/plumbing. MLflow is the durable source of truth for "what's the champion model right now" — `evaluate` reads the champion RMSE from MLflow (not from a prior KFP run's artifacts), and `register` writes the new version + promotes an alias in MLflow. This is what makes runs comparable across pipeline executions instead of only within one DAG run.

### Key Data Flows

1. **Fan-out ingestion:** `months` pipeline parameter → N parallel `ingest→validate→features` chains, each independently cached/retriable by month. A single bad month fails its branch without failing siblings (unless you configure `exit_task`/fail-fast — default KFP behavior lets other ParallelFor branches continue).
2. **Fan-in training:** `dsl.Collected` merges N per-month `Dataset` artifacts into one list, consumed by a single `merge_features` task that concatenates into the training frame — this is the one deliberate serialization point in an otherwise parallel DAG.
3. **Promotion decision:** `evaluate` never talks to MinIO for champion info — it reads current champion RMSE from MLflow, computes challenger RMSE, and passes a boolean-driving `float` scalar (not an artifact) into `dsl.If`. `register` on the winning branch writes model + metrics to MLflow registry.
4. **CI image flow:** developer pushes → CI detects which `components/<name>/` dirs changed (or on first build, builds all) → builds+pushes N images to GHCR tagged with commit SHA (and `:latest` on main) → `pipelines/train_pipeline.py` references those exact tags in `base_image=`/`ContainerSpec(image=...)` → `kfp.compiler.Compiler().compile(...)` emits a pinned YAML that is fully reproducible from a given commit.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|---------------------------|
| This project (12 months, 16GB laptop, single dev) | `ParallelFor(parallelism=2-3)`; single-node k3d with 1 server + 1-2 agents; MinIO/MLflow as single-replica in-cluster deployments; no autoscaling needed |
| Larger window (e.g. 36+ months) or team use | Raise `ParallelFor` parallelism only after moving off a single laptop (managed k8s node pool); consider chunked/streaming ingest per month instead of full in-memory load; externalize MLflow/MinIO to managed services (RDS/S3) so pipeline runs don't compete with them for the same 16GB |
| Production multi-tenant | This is explicitly out of scope (no multi-user Kubeflow/Istio) — if ever needed, it's a platform migration (KFP standalone → full Kubeflow distribution), not an incremental change to this DAG |

### Scaling Priorities

1. **First bottleneck (immediate, this project):** RAM contention between k3d control plane + KFP backend (API server, MySQL, Argo Workflows controller) + MinIO + MLflow + task pods, all on one 16GB machine. Official KFP guidance already recommends 16GB as a *minimum* for KFP alone — mitigate by capping `ParallelFor` parallelism low (2-3), keeping the dataset window to 12 months, and downcasting dtypes at the features stage (already a stated requirement) to shrink per-task pod memory.
2. **Second bottleneck (if scope grows):** Image pull latency for each `ParallelFor` iteration's pod — every iteration pulls the same component image. Mitigate with `imagePullPolicy: IfNotPresent` (image already cached on the node after the first pull) and keeping component images small (thin components, minimal deps per Dockerfile).

## Anti-Patterns

### Anti-Pattern 1: Passing S3/MinIO paths as plain string parameters

**What people do:** Define a component as `def train(features_path: str) -> str` and manually construct/parse `s3://bucket/key` strings between components.
**Why it's wrong:** Breaks KFP's lineage graph (the UI can't show artifact provenance), breaks caching (string params don't carry the same content-addressed semantics as artifact inputs tied to producing-task identity), and is exactly the anti-pattern this project's requirements explicitly forbid ("no raw S3 path strings").
**Do this instead:** Always type artifact I/O as `Input[Dataset]`/`Output[Model]`/`Output[Metrics]` etc.; let the KFP launcher resolve the actual MinIO location under `pipeline_root`.

### Anti-Pattern 2: `packages_to_install` for component dependencies

**What people do:** Use `@dsl.component(packages_to_install=["pandas", "lightgbm", ...])` with the default base image, so KFP `pip install`s deps at task start time.
**Why it's wrong:** Slow (every task run re-installs deps from PyPI, no build-time caching), fragile (no version pin gets baked into an artifact you can point to later), and skips the CI image-build/GHCR-push pipeline this project is explicitly built to demonstrate.
**Do this instead:** Build one Docker image per component in CI (`components/<name>/Dockerfile`), push to GHCR with a commit-SHA tag, reference it via `base_image=` (Python-function components) or `dsl.ContainerSpec(image=...)` (container components).

### Anti-Pattern 3: Business logic inside `@dsl.component` bodies

**What people do:** Write pandas transformations, feature engineering, or model training directly inside the component function decorated with `@dsl.component`.
**Why it's wrong:** Makes the logic untestable without a KFP SDK compile step or cluster; violates this repo's explicit `lib/`-owns-100%-of-logic constraint; also bloats component images with test-irrelevant KFP SDK coupling.
**Do this instead:** Component body = read artifact `.path` → call one `lib/` function → write artifact `.path`/`.metadata`. All logic and all tests live in `lib/`.

### Anti-Pattern 4: Over-parallelizing ParallelFor on constrained hardware

**What people do:** Set `parallelism` to the full month count (e.g. 12) to "maximize speed."
**Why it's wrong:** On a 16GB laptop already running k3d + KFP backend + MinIO + MLflow, spawning 12 concurrent ingest/validate/features pods will exhaust memory and cause pod evictions/OOMKills, producing flaky failures that look like pipeline bugs but are resource starvation.
**Do this instead:** Cap `parallelism` at 2-3 for local runs; treat it as a pipeline parameter so it's trivial to raise later on better hardware.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|----------------------|-------|
| MinIO | In-cluster deployment; KFP `pipeline_root` and `kfp-launcher` ConfigMap point at it via `minio://` or `s3://` URI + endpoint/credentials | Confirm actual manifest bundled with the KFP standalone install you use — as of KFP 2.15 the *default* bundled object store shifted to SeaweedFS, so you may need to explicitly deploy/wire MinIO rather than assume it's default (verify version pinned before Phase 2 starts) |
| MLflow | Separate in-cluster (or `docker compose`) deployment; tracking URI passed to `train`/`evaluate`/`register` components as a plain string param (it's a service endpoint, not a data artifact, so a string param here is correct, not an anti-pattern) | Point its artifact store at the same MinIO bucket (different prefix) to avoid running a third storage backend |
| GHCR | GitHub Actions `docker/login-action` + `docker/build-push-action`, one job per component (matrix strategy), tagged `ghcr.io/<org>/<repo>/<component>:<sha>` and `:latest` on main | Use `dorny/paths-filter` (or simpler: build all on every push given only 6 components and a 1-week project — matrix complexity may not be worth it at this scale) to avoid rebuilding unchanged images |
| k3d | Local cluster via `k3d cluster create` with `--agents-memory`/`--servers-memory` flags | k3d does not hard-enforce these limits the way a VM-based tool (e.g. Minikube) would — it's advisory, not a hard cap; real protection comes from capping `ParallelFor` parallelism and setting pod resource requests/limits on components |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|----------------|-------|
| `lib/` ↔ `components/` | Direct Python import (`from lib.features import build_feature_frame`) | One-directional: `components/` imports `lib/`, never the reverse. `lib/` must have zero `kfp` import so it stays cluster-independent and trivially unit-testable |
| `components/` ↔ `pipelines/` | KFP SDK task/artifact wiring (`.outputs[...]` chaining) inside `@dsl.pipeline` | `pipelines/` never touches `lib/` directly — keeps the DAG file legible as pure orchestration |
| `pipelines/` (compiled DAG) ↔ KFP backend | Compiled `PipelineSpec` YAML submitted via KFP client/UI | CI compiles this YAML and attaches it as a release artifact — this is the reproducibility guarantee (given a commit SHA, the exact YAML + exact image tags it references are recoverable) |
| `evaluate`/`register` components ↔ MLflow | MLflow Python client (`mlflow.set_tracking_uri`, `MlflowClient`) inside the component, using `lib/registry.py` as the thin wrapper | This is the one place business logic (the actual champion-comparison decision could live in `lib/evaluate.py`, but registry I/O calls) crosses into external-service talk — keep it in `lib/registry.py` so it's still unit-testable with a mocked client |

## Suggested Build Order (10-15h budget)

Ordered so each step produces something independently demoable/verifiable, and later steps never block on unfinished earlier ones:

1. **Monorepo skeleton + `uv` + `lib/` stub + `pytest` running green on a trivial function.** (Phase 1 start) Unblocks everything — CI needs something to lint/test immediately, even before real logic exists.
2. **`ruff` + `mypy --strict` + `pytest` wired into CI on every PR, `pre-commit` mirroring it.** Fast, config-only work; gives you a green CI badge early — the single most interview-visible "quality gate" artifact, cheap to get right first.
3. **`lib/ingest.py`, `lib/schemas.py` (pandera) + tests with synthetic DataFrames.** First real logic; small in scope (one month's read + schema check), fully offline (no cluster needed yet) — highest ratio of "provable engineering rigor" to time spent.
4. **`lib/features.py` (vectorized haversine, dtype downcast) + before/after benchmark + tests.** Still fully offline; this is the other README-required artifact (perf benchmark table) — do it before touching Kubernetes so a slow k3d setup doesn't eat into this budget.
5. **`lib/train.py`, `lib/evaluate.py`, `lib/registry.py` (MLflow client wrapper, mockable) + tests.** Completes 100% of `lib/` logic before any KFP work starts — de-risks the "is the math right" question independently of "does Kubernetes work," which is the harder unknown given the user's stated Kubernetes inexperience.
6. **k3d cluster up + KFP standalone install + MinIO + MLflow reachable (`kubectl port-forward`, basic UI smoke test).** This is the highest-risk, least-familiar step (per PROJECT.md, Kubernetes is the explicit skill gap) — start it with a real time-box; if it overruns, the previous 5 steps are still a demoable, fully-tested `lib/` package with CI, which is itself defensible partial progress.
7. **One component end-to-end (`ingest`): Dockerfile → CI build/push to GHCR → single-task pipeline compiles and runs successfully on the cluster.** Proves the entire chain (image build → registry → typed artifact → cluster execution) on the smallest possible surface before multiplying it by 6 components. This is the single most valuable checkpoint — once this works, the remaining components are repetition of a proven pattern.
8. **Remaining components (`validate`, `features`, `train`, `evaluate`, `register`) using the same pattern.** Mechanical once step 7 works.
9. **Assemble full DAG: `ParallelFor` fan-out → `Collected` merge → train → evaluate → `If`/`OneOf` promotion → `ExitHandler`.** Do `ParallelFor` before `If`/`OneOf` — fan-out is more likely to surface resource/parallelism issues, better to hit that with a simpler linear tail still to build/debug against.
10. **Caching demo (run twice, show cache hit; change one component, show invalidation) + idempotent backfill demo (`start_month`/`end_month`, run twice, diff outputs) + README/ADRs.** Do last — both are "prove it" exercises on top of an already-working DAG, not new capability, so they're safe to compress or cut first if the budget runs short.

If time runs out, the safe cut line is: stop after step 7 or 8 (a working single- or few-component pipeline on the cluster) rather than after step 6 (cluster up, nothing running on it) — a partially-populated real DAG is more demoable than fully-tested `lib/` code with no cluster proof at all, once Kubernetes setup itself is de-risked.

## Sources

- [Kubeflow: Control Flow (dsl.ParallelFor, dsl.Collected, dsl.If/Elif/Else, dsl.OneOf)](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/control-flow/) — HIGH confidence (official docs, fetched directly)
- [Kubeflow: Containerized Python Components](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/containerized-python-components/) — HIGH confidence (official docs)
- [Kubeflow: Container Components](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/container-components/) — MEDIUM confidence (search-summarized, not directly fetched)
- [Kubeflow: Create, use, pass, and track ML artifacts](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/) — MEDIUM confidence
- [Kubeflow: Pipeline Root](https://www.kubeflow.org/docs/components/pipelines/concepts/pipeline-root/) and [Object Store Configuration](https://www.kubeflow.org/docs/components/pipelines/operator-guides/configure-object-store/) — MEDIUM confidence (search-summarized; includes the KFP 2.15 SeaweedFS-default note, flagged as needing version verification)
- [Kubeflow: Use Caching](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/caching/) — MEDIUM confidence
- [kubeflow/website Issue #2209 — Deploying KFP Standalone on kind/k3s](https://github.com/kubeflow/website/issues/2209) — LOW confidence (community issue thread, not authoritative install guide; validate with a spike)
- [yuhuishi-convect/local-k3d-ml](https://github.com/yuhuishi-convect/local-k3d-ml) — LOW confidence (community reference repo for KFP-on-k3d)
- [k3d-io/k3d Discussion #627 — resource allocation](https://github.com/k3d-io/k3d/discussions/627) — LOW confidence (community discussion; confirms k3d memory flags are advisory, not hard-enforced)
- [dorny/paths-filter](https://github.com/dorny/paths-filter) and general GHA monorepo/GHCR build-push patterns — MEDIUM confidence (well-established open-source Action, widely used pattern)
- MLflow champion/challenger model registry pattern (aliases, comparison gate) — MEDIUM confidence (search-summarized across MLflow docs and MLOps pattern write-ups, not a single authoritative source)

---
*Architecture research for: Batch ML pipeline platform on Kubeflow Pipelines v2 (KFP standalone, k3d, MinIO, MLflow)*
*Researched: 2026-08-11*
