# Phase 3: Kubeflow Pipeline Core & Deployment - Research

**Researched:** 2026-08-24
**Domain:** KFP v2 standalone on k3d, in-cluster MLflow/MinIO deployment, KFP control-flow (ParallelFor/Collected/If/ExitHandler), backfill idempotency proof
**Confidence:** MEDIUM-HIGH — the five open questions this research targets were answered with primary-source evidence (official GitHub repos read directly, one empirical test run in this repo's own pinned environment). General KFP/k3d mechanics remain covered by the existing `research/ARCHITECTURE.md`, `research/STACK.md`, `research/PITFALLS.md` docs, which this file does not duplicate.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-10 (cluster install risk handling):** No dedicated `/gsd-spike` before planning, no forced early-checkpoint gate. Attempt the k3d + KFP standalone install directly during phase execution with a firm time-box; if it overruns, fall back to `research/ARCHITECTURE.md`'s "safe cut line" (a fully-tested `lib/` + CI + at least one component proven end-to-end on the cluster is defensible partial progress). Plan should sequence component image build/push proof (steps 1-5 of `ARCHITECTURE.md`'s Suggested Build Order) before the riskiest step (full cluster install). Reversible.
- **D-11 (ExitHandler / notify scope):** The `ExitHandler`'s notify component is intentionally minimal: a single structured log/print line (run status, run id, RMSE if applicable) satisfying REQ-B9. No run-summary artifact file, no webhook/desktop notification, no extra image beyond what's needed to prove the exit-path wiring works on both success and failure branches.
- **D-12 (MLflow deployment topology):** MLflow (tracking server + registry) deploys **in-cluster** on k3d from the start — not the RAM-pressure host-process fallback. Backed by a dedicated MinIO pod (its own bucket, not KFP's internal SeaweedFS) and a SQLite backend store (no separate Postgres pod). If RAM pressure becomes severe during execution, the host-process fallback remains available as a documented escape hatch (same MLflow client code, deployment-only change). Reversible.
- **D-13 (idempotent backfill proof scope):** REQ-B8's "run the same `start_month`/`end_month` range twice, prove byte-identical output" is demonstrated on a **small 2-3 month subset**, not the full 12-month window. Reversible.

### Claude's Discretion

- Exact k3d/KFP/MinIO/MLflow install commands and manifest choices beyond what `research/STACK.md`'s Installation section already specifies — executor follows STACK.md directly (this file supplements STACK.md with newer/more-precise findings; see "Drift vs. STACK.md" below).
- Internal `components/` module structure and whether each stage uses `@dsl.component(base_image=...)` vs `@dsl.container_component`.
- Whether the existing tracer component (`components/ingest/main.py`, `components/ingest/Dockerfile`) is extended in place to become the real `ingest` component, or replaced.
- Exact input changed to demonstrate cache-key invalidation (REQ-B10).
- Registered model name, MLflow experiment naming convention, exact resource `requests`/`limits` per component.
- Notify task's exact log line format/fields (D-11 sets scope, not exact shape — see this research's finding below that RMSE cannot flow into the exit task via KFP's task-output graph).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 3 scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-B1 | KFP standalone on k3d, no Istio namespace | `env/platform-agnostic` overlay confirmed current at 2.17.0, no Istio dependency (verified below) |
| REQ-B2 | Typed artifacts throughout, no raw string paths | Pattern already documented in `ARCHITECTURE.md`; this research adds the deterministic-output-key nuance required by REQ-B8 without breaking typed-artifact semantics |
| REQ-B3 | Custom CI-built/GHCR-hosted images, no `packages_to_install` | Unchanged from `ARCHITECTURE.md`/`PITFALLS.md`; package-legitimacy audit below covers the two new pipeline-group packages (`kfp`, `kfp-kubernetes`) |
| REQ-B4 | Full DAG compiles and reaches `register`/skip-branch | Validation Architecture section maps this to a compile-time automated check + a manual cluster-run checkpoint |
| REQ-B5 | `ParallelFor` capped 2-3 concurrent | Unchanged from `PITFALLS.md` Pitfall 4; Validation Architecture adds an automated static check on the compiled YAML |
| REQ-B6 | `dsl.Collected` fan-in before train | Unchanged from `ARCHITECTURE.md` Pattern 3 |
| REQ-B7 | Conditional promotion both directions | Unchanged; `lib/evaluate.py`'s `beats_champion` and `lib/registry.py`'s `ModelRegistry` already implement this against an injectable client — Phase 3 wires a real one |
| REQ-B8 | Idempotent backfill, byte-identical, 2-3 month subset (D-13) | **Answered below (Q3):** empirically verified no non-deterministic metadata in Parquet/LightGBM output bytes given this repo's pinned library versions; deterministic-key design still required per `PITFALLS.md` Pitfall 5 |
| REQ-B9 | `ExitHandler` covers failure path | **Answered below (Q4):** exact `dsl.ExitHandler` + `PipelineTaskFinalStatus` code pattern from official docs, plus a load-bearing constraint (exit task cannot consume task outputs from inside its own scope) that changes what D-11's log line can contain |
| REQ-B10 | Caching enabled, deliberately invalidated | Unchanged from `PITFALLS.md` Pitfall 6 |
| REQ-B11 | Compiled YAML as CI release artifact | Unchanged; CI wiring is additive to the existing `.github/workflows/ci.yml` |
| REQ-E1 | README architecture diagram | `ARCHITECTURE.md`'s System Overview diagram is the base; Validation Architecture section below proposes a `test_readme.py`-pattern regression test |
| REQ-E2 | ADRs for the 4 PROJECT.md Key Decisions | Content source is CONTEXT.md's D-10/D-11/D-12/D-13 plus PROJECT.md; no new research needed |
| REQ-E3 | README "Next Steps" (deferred scope) | Content source is `REQUIREMENTS.md`'s Out of Scope section; no new research needed |

</phase_requirements>

## Summary

The five targeted questions in this research all resolved with primary-source evidence, and three produced findings that materially update or add to `research/STACK.md`/`ARCHITECTURE.md`/`PITFALLS.md`:

1. **KFP install path confirmed, with a drift correction.** KFP 2.17.0 is still the current release (verified against the live GitHub tags list). The kubeflow.org docs page now *recommends* the `env/dev` kustomize overlay for "development/non-production" installs — but `env/dev`'s own kustomization file (read directly at the `2.17.0` tag) repoints every component image to the floating `master` tag and pulls in GCP-specific resources (`gcp/inverse-proxy`, Cloud Console `Application` CRD wiring). That is a *worse* choice for this project than STACK.md's existing recommendation, `env/platform-agnostic`, which has no image overrides (so it inherits the base manifests' images pinned to `2.17.0` exactly) and no cloud-provider dependency. **STACK.md's overlay choice is correct and should be kept as-is; do not follow the current kubeflow.org "quick start" verbatim.**

2. **MLflow now has an official Helm chart, which STACK.md predates.** `github.com/mlflow/mlflow/tree/master/charts` ships `oci://ghcr.io/mlflow/charts/mlflow`, with `Chart.yaml appVersion: "3.15.1"` — an exact match to this project's pinned `mlflow==3.15.1`. Its `values.yaml` directly supports the D-12 topology (SQLite `backendStoreUri`, a `storage.enabled` PVC for the SQLite file, `defaultArtifactRoot: s3://...` for a MinIO-backed artifact store, and an `env:` list for S3 credentials/endpoint). This is a cleaner in-cluster deployment path than hand-rolling a Deployment/PVC/Service manifest, and directly supersedes STACK.md's plain `mlflow server` host-process snippet for the D-12 in-cluster topology. `resources:` defaults to `{}` (no limits) — must be set explicitly.

3. **Byte-identical idempotency is achievable with a plain checksum — empirically verified in this repo's own environment.** `pandas.to_parquet` output and LightGBM's native model-text dump are both byte-for-byte identical across repeated writes/fits with this repo's pinned versions and deterministic training config (`n_jobs=1`, `deterministic=True`, fixed `random_state`). No KFP-injected or library-injected timestamp/run-ID exists in the artifact bytes themselves. The only non-determinism risk is architectural, not byte-level: KFP's default `pipeline_root` layout is run-ID-scoped (already documented in `PITFALLS.md` Pitfall 5) — the deterministic-key design there remains the real prerequisite, not any metadata-stripping step.

4. **A load-bearing KFP constraint that changes D-11's notify-log scope.** `dsl.ExitHandler`'s exit task is constructed *before* the `with` block and cannot consume outputs from any task inside that block (confirmed via kubeflow.org docs and `kubeflow/pipelines#10187`). Since `evaluate` (which computes RMSE) runs *inside* the ExitHandler's scope, **the notify task cannot receive RMSE as a task-output parameter** — only `PipelineTaskFinalStatus` fields (`state`, `pipeline_job_resource_name`, `pipeline_task_name`, `error_code`, `error_message`) and pipeline-level parameters known at construction time. The planner should scope D-11's log line to status/run-id/error fields only, or explicitly accept dropping "RMSE if applicable" (it was illustrative in CONTEXT.md, not a hard requirement — Claude's Discretion already covers exact log-line shape).

5. **MinIO's community Helm chart is the concrete deployment path for the dedicated MinIO pod**, with one footgun: its default `resources.requests.memory` is **16Gi** unless overridden — a certain OOM/scheduling failure on a 16GB laptop. The chart's own "toy setup" example disables persistence entirely (ephemeral); for this project's champion/candidate story to survive across separate pipeline runs, persistence should stay enabled with a small PVC instead.

**Primary recommendation:** Follow STACK.md's `env/platform-agnostic` KFP overlay unchanged (do not switch to `env/dev`). Deploy MLflow via its official Helm chart (SQLite + `env:`-injected MinIO S3 credentials) rather than a hand-rolled manifest. Deploy the dedicated MinIO pod via MinIO's community Helm chart with an explicit (small) memory request and persistence enabled. Design the deterministic output-key strategy for `ingest`/`validate`/`features` before writing the first non-tracer component — the idempotency proof is a plain SHA256 checksum comparison once that key strategy exists. Scope the ExitHandler notify log line to status/run-id/error fields; do not attempt to route `evaluate`'s RMSE into it.

## Architectural Responsibility Map

This project is a batch ML pipeline, not a web app — the generic Browser/SSR/API/CDN/DB tiers below are re-mapped to this domain's actual layers (orchestration, compute, artifact storage, registry, distribution).

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| DAG sequencing, ParallelFor/Collected/If/ExitHandler control flow | Orchestration (`pipelines/train_pipeline.py`, KFP backend) | — | Pure wiring; no business logic belongs here per `ARCHITECTURE.md` Pattern 1 |
| Ingest/validate/features/train/evaluate/register business logic | Compute (`lib/` via thin `components/` wrappers, running as K8s pods) | — | `lib/` is 100% pandas/LightGBM/pandera logic, zero KFP imports; `components/` is I/O glue only |
| Typed artifact bytes (Parquet, model files, metrics) for a single run | Artifact Storage (KFP `pipeline_root`, backed by KFP's own bundled SeaweedFS) | — | Ephemeral/run-scoped; lineage-tracked by KFP itself, not queried across runs |
| Champion/candidate model versions, RMSE history, aliasing | Registry (MLflow tracking + model registry, backed by the dedicated MinIO pod) | Artifact Storage (MinIO holds the actual model artifact bytes MLflow references) | Durable, queryable across runs — this is what makes promotion decisions comparable across separate pipeline executions, per `ARCHITECTURE.md`'s Artifact Store / Registry Split |
| Component image build, versioning, distribution | Distribution (GitHub Actions CI, GHCR) | — | Images are the reproducibility unit; `pipelines/` only ever references a GHCR tag, never rebuilds |
| Cluster lifecycle, resource limits, image pulls | Cluster/Infra (k3d, K8s scheduler) | — | Where Pitfalls 1-4 (memory, resource-limit silent-drop, ImagePullBackOff, unbounded fan-out) all live |

## Standard Stack

### Core (unchanged from STACK.md — re-verified this session)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `kfp` | 2.17.0 | Pipeline SDK, compiles to IR YAML | [VERIFIED: PyPI `pip index versions kfp` this session — 2.17.0 is latest] Confirmed still the current KFP release via `kubeflow/pipelines` GitHub tags (no 2.18+ exists as of this research date) |
| `kfp-kubernetes` | 2.17.0 (match `kfp` exactly) | K8s-specific pipeline extensions | [VERIFIED: PyPI `pip index versions kfp-kubernetes` this session — 2.17.0 is latest, same release cadence as `kfp`] |
| KFP backend (standalone) | 2.17.0, `env/platform-agnostic` overlay | Runs API server, Argo Workflows, MLMD, cache server | [VERIFIED: `github.com/kubeflow/pipelines` manifests/kustomize tree at tag `2.17.0`, read directly via `gh api` this session — see Drift note below] |
| `mlflow` | 3.15.1 | Tracking + registry | [VERIFIED: pyproject.toml already pins `mlflow==3.15.1`; MLflow's own official Helm chart `Chart.yaml appVersion` matches exactly, read via `gh api` this session] |
| k3d | v5.9.0 | Local k3s-in-Docker cluster | [VERIFIED: `gh release list --repo k3d-io/k3d` this session — v5.9.0 is latest] |

### Supporting (new this phase)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `helm` | v3.x (any current) | Deploy MLflow's official chart and MinIO's community chart | Not currently installed on the dev machine (see Environment Availability) — install before Phase 3 execution. STACK.md's Installation section did not mention Helm at all; this is a net-new required tool this research surfaces. |
| MLflow Helm chart | `oci://ghcr.io/mlflow/charts/mlflow` (chart repo `version: 0.1.0` in-repo at research time; confirm exact published tag with `helm show chart oci://ghcr.io/mlflow/charts/mlflow` at execution time) | In-cluster MLflow deployment (D-12) | Use instead of hand-rolled Deployment/PVC/Service YAML — see Code Examples below |
| MinIO community Helm chart | `minio/minio` from `https://charts.min.io/` (chart version drifts frequently; confirm with `helm search repo minio/minio` at execution time) | Dedicated MinIO pod for MLflow's artifact store (D-12) | [CITED: github.com/minio/minio/blob/master/helm/minio/README.md, read directly this session] Community-maintained per MinIO's own README (not MinIO's officially-supported Operator path, which is heavier and not needed here) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `env/platform-agnostic` KFP overlay | `env/dev` (per current kubeflow.org quick-start docs) | Rejected: `env/dev` floats all images to `:master` (breaks reproducibility/pinning) and pulls in GCP-only resources irrelevant to k3d |
| MLflow official Helm chart | Hand-rolled Deployment/PVC/Service YAML (STACK.md's original snippet) | Helm chart is maintained by the MLflow project itself, version-matched to the pinned client, and already exposes every knob D-12 needs (SQLite URI, S3 artifact root, PVC) — less manifest-authoring risk for a 10-15h budget |
| MinIO community Helm chart | Hand-rolled Deployment/PVC/Service, or MinIO's official Operator | Operator is explicitly the "production" path per MinIO's own README and is unnecessary ceremony for a single dev-mode pod; hand-rolled YAML works too (STACK.md's original suggestion) but the Helm chart is one command and has the memory-request footgun already documented below |

## Package Legitimacy Audit

| Package | Registry | Age (latest release) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----------------------|-----------|--------------|---------|-------------|
| `kfp` | PyPI | 2.17.0 released 2025-07-09 | Unknown to the legitimacy checker (no download-count signal wired up) | `github.com/kubeflow/pipelines/tree/master/sdk` | SUS (`unknown-downloads` only) | **Approved** — official Kubeflow project SDK, matches this project's already-pinned version and repo already imports it per plan |
| `kfp-kubernetes` | PyPI | 2.17.0 released 2025-07-09 | Unknown to the legitimacy checker | `github.com/kubeflow/pipelines/tree/master/kubernetes_platform/python` | SUS (`unknown-downloads` only) | **Approved** — official companion package to `kfp`, same repo, same release cadence |
| `boto3` | PyPI | latest patch published 2026-08-21 | Unknown to the legitimacy checker | `github.com/boto/boto3` | SUS (`unknown-downloads`, `too-new` — flagged only because AWS ships near-daily patch releases) | **Approved** — official AWS SDK for Python, needed for MLflow's S3-compatible (MinIO) artifact client; the "too-new" signal is an artifact of AWS's release cadence, not a legitimacy concern |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `kfp`, `kfp-kubernetes`, `boto3` — all three flagged solely because the legitimacy-check seam has no package-download-count data source wired up in this environment (`unknown-downloads`), not because of any actual red flag (all three resolve to well-known, high-reputation GitHub organizations: `kubeflow/pipelines` and `boto/boto3`). Per protocol this still requires the planner to add a lightweight `checkpoint:human-verify` before the `uv add` step that installs them — treat it as a formality confirming the pin matches `kfp==2.17.0` (already matched to the installed backend) rather than a real risk investigation.

## Architecture Patterns

(See `research/ARCHITECTURE.md` for the full System Overview diagram, Component Responsibilities, Patterns 1-4, Data Flow, Anti-Patterns, and Suggested Build Order — unchanged and not reproduced here. This section adds only what that document does not cover.)

### Pattern 5: Deterministic output key for backfill idempotency (REQ-B8/D-13)

**What:** Every `ingest`/`validate`/`features` component writes its artifact bytes to a location whose identity is derived from the pipeline parameter (`month`), not from KFP's auto-generated run-ID-scoped `pipeline_root` path. The typed-artifact *object* (`Output[Dataset]`) is still what downstream components consume — the determinism requirement is about the **content-addressed key** the bytes eventually land at, which is a property the component body must construct explicitly.
**When to use:** `ingest`, `validate`, `features` (any component in the per-month `ParallelFor` branch) — decide this before writing the first non-tracer component, since retrofitting after the loop is wired risks silent data corruption on re-run (per `PITFALLS.md` Pitfall 5, unchanged from prior research).
**Idempotency proof mechanics (this research's Q3 answer):** once the deterministic key exists, "byte-identical" is a plain `hashlib.sha256(file_bytes)` comparison — no exclusion/normalization step is needed for Parquet or LightGBM model files produced by this repo's pinned library versions (empirically verified this session). The one caveat: both runs being diffed must use the *same component image* (same pinned `pandas`/`pyarrow`/`lightgbm` versions) — if the image were rebuilt with different pinned library versions between the two backfill runs, the Parquet footer's embedded `pandas_version`/`creator` metadata would differ even though the data is identical. Document this precondition next to the checksum table in README rather than treating it as implicit.

### Pattern 6: ExitHandler notify task cannot see task outputs from its own scope

**What:** `dsl.ExitHandler(exit_task=notify_task)` requires `notify_task` to be constructed *before* entering the `with` block. Because of this construction order, the exit task can only be parameterized with pipeline-level inputs known at compile time, plus the backend-injected `PipelineTaskFinalStatus` — never a `.output`/`.outputs[...]` reference to a task defined inside the block (confirmed via `kubeflow/pipelines#10187`).
**When to use:** Any time D-11's "RMSE if applicable" is being designed — since `evaluate` (which computes RMSE) necessarily runs inside the `ExitHandler`'s scope (it must run before the exit condition is known), RMSE cannot be threaded into the notify task's parameters.
**Trade-off:** Accept that the notify log line is limited to `status.state`/`status.pipeline_job_resource_name`/`status.pipeline_task_name`/`status.error_code`/`status.error_message` plus any pipeline-level param (e.g. `months` or `start_month`/`end_month`) passed at construction time. Querying MLflow from inside the notify task to fetch "the most recent RMSE" is technically possible but reintroduces exactly the coupling/complexity D-11 explicitly says to avoid — not recommended.

## Don't Hand-Roll

(Extends `ARCHITECTURE.md`'s existing guidance — this phase adds two more.)

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| In-cluster MLflow deployment (Deployment + PVC + Service + ConfigMap wiring) | A hand-authored set of K8s manifests | MLflow's official Helm chart (`oci://ghcr.io/mlflow/charts/mlflow`) | Chart is maintained by the MLflow project itself, version-matched to the pinned `mlflow==3.15.1` client, and already exposes every D-12 knob (SQLite URI, S3 artifact root, PVC, resource limits) — writing this by hand risks subtle misconfiguration (wrong probe paths, missing `fsGroup` for the PVC-mounted SQLite file, etc.) for no benefit in a time-boxed phase |
| Byte-identical output verification tooling | A custom Parquet-metadata-stripping/normalization script before hashing | Plain `hashlib.sha256(path.read_bytes())` | Empirically verified this session: no non-deterministic metadata exists in this repo's Parquet/LightGBM outputs given pinned library versions — building a normalization step would be solving a problem that does not exist here, and would itself be unverified/untested extra code |

**Key insight:** Both additions above are "don't reinvent what upstream already ships correctly" — the theme is consistent with `ARCHITECTURE.md`'s existing Anti-Pattern guidance (don't hand-roll what the ecosystem already solved), just extended to the two infrastructure pieces this research specifically dug into.

## Common Pitfalls

(Extends `research/PITFALLS.md`'s 8 documented pitfalls — this section adds three new ones this research surfaced; the original 8 are unchanged and not reproduced here.)

### Pitfall 9: Following kubeflow.org's current "quick start" literally deploys unpinned images

**What goes wrong:** The current kubeflow.org standalone-install docs recommend `kubectl apply -k ".../env/dev?ref=$PIPELINE_VERSION"`. Despite the `?ref=2.17.0` in the URL (which only controls which git tag the kustomize *manifests themselves* are read from), `env/dev`'s own `kustomization.yaml` at that tag contains an `images:` block that repoints every KFP component image to `newTag: master` — a floating tag that moves independently of the release you thought you pinned. You end up running whatever is on `kubeflow/pipelines`'s `master` branch at pull time, not the tested 2.17.0 release.
**Why it happens:** The `env/dev` overlay was designed as an "always-latest" convenience path for active KFP contributors testing against `master`, not as a reproducible-install path for downstream users — this distinction is not surfaced in the docs page's prose.
**How to avoid:** Use `env/platform-agnostic` (STACK.md's original recommendation) — it has no `images:` override block, so it inherits the base manifests' `newTag: 2.17.0` pins unmodified. Verify after install with `kubectl get pods -n kubeflow -o jsonpath='{.items[*].spec.containers[*].image}'` and confirm every `ghcr.io/kubeflow/kfp-*` image shows `:2.17.0`, not `:master`.
**Warning signs:** Component image tags in `kubectl get pods -o yaml` showing `:master` instead of `:2.17.0` — a rebuild upstream between your install and a later re-install could silently change cluster behavior with no code change on your side.
**Phase to address:** Phase 3 (cluster install step, D-10's time-boxed attempt) — verify image tags immediately after the first successful `kubectl wait ... --for condition=ready`, before building anything on top.

### Pitfall 10: MinIO's Helm chart defaults to a 16Gi memory request

**What goes wrong:** Installing `minio/minio` via Helm without `--set resources.requests.memory=<value>` requests 16Gi of memory for a single pod by default — on a 16GB laptop already running k3d + KFP's own ~10-12 pods, this either fails to schedule (`Pending`, `Insufficient memory`) or, worse, schedules and starves everything else.
**Why it happens:** The chart's production-oriented default assumes a real cluster with dedicated nodes, not a single-laptop dev setup sharing RAM with everything else.
**How to avoid:** Always pass `--set resources.requests.memory=512Mi` (or similar) explicitly — this is documented in the chart's own README as the "toy setup" pattern, but is easy to miss if you only skim the plain `helm install minio/minio` command shown first.
**Warning signs:** `kubectl get pods -n mlflow` (or wherever MinIO lands) shows the MinIO pod stuck `Pending` with a `FailedScheduling`/`Insufficient memory` event.
**Phase to address:** Phase 3 (MLflow/MinIO deployment step, D-12).

### Pitfall 11: ExitHandler's exit task cannot read outputs from tasks inside its own scope

**What goes wrong:** A natural first attempt at D-11's "log the RMSE" is to write `notify_task = notify(rmse=evaluate_task.outputs['rmse'])` and pass that into `dsl.ExitHandler(exit_task=notify_task)`. This fails to compile (or compiles incoherently) because `notify_task` must be constructed *before* `evaluate_task` exists in the `with` block's scope — `dsl.ExitHandler`'s documented pattern always constructs the exit task first, then enters the `with` block.
**Why it happens:** The natural mental model ("the exit handler is just another downstream consumer of the DAG's outputs") doesn't match KFP's actual execution model, where the exit task must be resolvable even when the tasks inside the handler's scope never ran (e.g., total pipeline failure before `evaluate` executes) — there is no RMSE to pass in that case, so the SDK doesn't allow the dependency at all, success or failure.
**How to avoid:** Scope the notify task to only `PipelineTaskFinalStatus` fields and pipeline-level parameters set before the `with` block. Do not design the notify log line around a value computed inside the handler's scope.
**Warning signs:** A KFP compile error mentioning the exit task depending on a task inside its own group, or (depending on SDK version) a confusing DAG-shape error when compiling.
**Phase to address:** Phase 3 (ExitHandler wiring step) — decide the notify log line's exact fields against this constraint before writing the component, not after a failed compile.

## Code Examples

### MLflow official Helm chart install (D-12, in-cluster, SQLite + MinIO S3 artifact store)

```bash
# Source: github.com/mlflow/mlflow/tree/master/charts (values.yaml, Chart.yaml — read directly this session)
kubectl create secret generic mlflow-minio-creds \
  --namespace mlflow \
  --from-literal=AWS_ACCESS_KEY_ID=<minio-access-key> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<minio-secret-key>

helm install mlflow oci://ghcr.io/mlflow/charts/mlflow \
  --namespace mlflow --create-namespace \
  --set storage.enabled=true \
  --set storage.size=2Gi \
  --set mlflow.backendStoreUri="sqlite:////mlflow/mlflow.db" \
  --set mlflow.defaultArtifactRoot="s3://mlflow-artifacts/" \
  --set resources.requests.cpu=250m \
  --set resources.requests.memory=256Mi \
  --set resources.limits.memory=512Mi \
  --set-string env[0].name=MLFLOW_S3_ENDPOINT_URL \
  --set-string env[0].value="http://minio.mlflow.svc.cluster.local:9000" \
  --set env[1].name=AWS_ACCESS_KEY_ID \
  --set env[1].valueFrom.secretKeyRef.name=mlflow-minio-creds \
  --set env[1].valueFrom.secretKeyRef.key=AWS_ACCESS_KEY_ID \
  --set env[2].name=AWS_SECRET_ACCESS_KEY \
  --set env[2].valueFrom.secretKeyRef.name=mlflow-minio-creds \
  --set env[2].valueFrom.secretKeyRef.key=AWS_SECRET_ACCESS_KEY
```

Uses the in-cluster MinIO service DNS name (`minio.mlflow.svc.cluster.local`), never `localhost`, per `PITFALLS.md` Pitfall 7's existing guidance — this session's finding only supplies the exact Helm values that wire it, the DNS-not-localhost rule itself is unchanged prior research.

### MinIO community Helm chart install (dedicated pod, D-12)

```bash
# Source: github.com/minio/minio/blob/master/helm/minio/README.md — read directly this session
helm repo add minio https://charts.min.io/
helm install minio minio/minio \
  --namespace mlflow \
  --set mode=standalone \
  --set replicas=1 \
  --set resources.requests.memory=512Mi \
  --set persistence.enabled=true \
  --set persistence.size=2Gi \
  --set rootUser=<minio-access-key> \
  --set rootPassword=<minio-secret-key>
```

Note `persistence.enabled=true` here deliberately diverges from the chart's own "toy setup" example (which sets `persistence.enabled=false`) — this project's champion/candidate promotion story (REQ-B7) needs MinIO-backed model artifacts to survive across separate pipeline runs, not just within one.

### ExitHandler + PipelineTaskFinalStatus minimal notify pattern (D-11, REQ-B9)

```python
# Source: kubeflow.org control-flow docs (fetched via context7 this session)
from kfp import dsl
from kfp.dsl import PipelineTaskFinalStatus


@dsl.component(base_image="ghcr.io/ORG/REPO/notify:latest")
def notify(status: PipelineTaskFinalStatus) -> None:
    # D-11: a single structured log line — no artifact file, no external call.
    # RMSE is deliberately absent: evaluate runs inside the ExitHandler's own
    # scope, so its output cannot be threaded into this exit task (Pitfall 11).
    print(
        f"run_status={status.state} "
        f"run_id={status.pipeline_job_resource_name} "
        f"failed_task={status.pipeline_task_name or ''} "
        f"error_code={status.error_code or ''} "
        f"error_message={status.error_message or ''}"
    )


@dsl.pipeline
def train_pipeline(months: list, start_month: str, end_month: str, parallelism: int = 2):
    notify_task = notify()  # constructed before the with-block, per SDK requirement
    with dsl.ExitHandler(exit_task=notify_task):
        with dsl.ParallelFor(months, parallelism=parallelism) as month:
            ingest_task = ingest(month=month)
            # ... validate, features, merge, train, evaluate, dsl.If(...) as in ARCHITECTURE.md Pattern 3/4
```

### Idempotency checksum comparison (D-13, REQ-B8)

```python
# Empirically verified this session against this repo's pinned pandas==2.3.3 /
# pyarrow==25.0.1 / lightgbm==4.7.0 — no exclusion/normalization needed.
import hashlib
from pathlib import Path


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# README documents: sha256_of(run1_features_2019-07.parquet) == sha256_of(run2_features_2019-07.parquet)
# for every month in the 2-3 month subset (D-13), using the *same* component
# image for both runs (see Pattern 5's caveat on cross-image-rebuild diffs).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Hand-rolled MLflow K8s manifests (STACK.md's original plain `mlflow server` snippet, host-process oriented) | MLflow's own official Helm chart (`oci://ghcr.io/mlflow/charts/mlflow`) | Chart exists on the `master` branch of `mlflow/mlflow` as of this research date, `appVersion` matches the exact pinned client version | Removes a whole category of manifest-authoring risk for the D-12 in-cluster topology |
| kubeflow.org's "development" quick-start recommending `env/dev` | `env/platform-agnostic` (unpinned-image risk avoided) | The `env/dev` overlay's `images: newTag: master` behavior is unchanged in substance from when `ARCHITECTURE.md`/`STACK.md` were researched (2026-08-11) but was not previously verified at the file level — this research reads the actual kustomization source, not just the docs prose | Confirms STACK.md's existing choice was already correct; prevents a plan-time regression toward the docs' now-more-prominent `env/dev` recommendation |

**Deprecated/outdated:** Nothing new deprecated this session — MLflow's registry-stage API (`transition_model_version_stage`) remains deprecated in favor of the alias API `lib/registry.py` already uses; this is unchanged from Phase 2 research and is *not* what this project's own `.claude/skills/mlflow` generic skill demonstrates (that skill's "Model Stages" section shows the deprecated stage-transition API — do not follow it for this project; `lib/registry.py`'s existing alias-based pattern is correct and should be followed instead).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | Exact published OCI tag of the MLflow Helm chart (`Chart.yaml` shows `version: 0.1.0` on `master` at research time) will still resolve cleanly via `helm show chart oci://ghcr.io/mlflow/charts/mlflow` at execution time | Standard Stack, Code Examples | Low — chart is actively maintained by the MLflow project; worst case is a `--version` pin needed at install time, easily discovered with `helm show chart` |
| A2 | The exact `minio/minio` community chart version available via `https://charts.min.io/` at execution time still exposes the same `mode`/`persistence`/`resources.requests.memory`/`rootUser`/`rootPassword` value keys shown in this research's Code Examples | Code Examples | Low-Medium — these are long-stable, widely-documented chart keys; if changed, `helm show values minio/minio` at execution time will surface the current key names |
| A3 | k3d v5.9.0 + `kubectl apply -k` (kubectl's bundled kustomize, confirmed present as `v1.35.4`/kustomize `v5.7.1` on this dev machine) is sufficient without installing a standalone `kustomize` binary | Environment Availability | Low — `kubectl`'s built-in `-k` flag has supported the manifests this project needs since well before kustomize v5; a standalone binary is optional |

## Open Questions (RESOLVED)

1. **RESOLVED — Exact resource `requests`/`limits` per component (ingest/validate/features/train/evaluate/register/notify)**
   - What we know: `PITFALLS.md` mandates explicit limits on every component (Pitfall 1/2); LightGBM training on a 12-month window is "small data" per STACK.md.
   - What's unclear: The specific numbers — left to executor per CONTEXT.md's Claude's Discretion, grounded in observed memory usage during Phase 3 execution rather than guessed upfront.
   - Recommendation: Set conservative starting values (e.g. `512Mi`/`1Gi` for ingest/validate/features, `1Gi`/`2Gi` for train), verify actual usage via `kubectl top pod`/`docker stats` during the first ParallelFor test run per Pitfall 1's existing guidance, and adjust.
   - **RESOLVED:** starting values are pinned in `03-02-PLAN.md` Task 3 (`512Mi`/`1536Mi` request/limit for ingest-class components, `1Gi`/`3Gi` for train), with `03-04-PLAN.md` Task 3 verifying the limits actually land on pods (Pitfall 2's SDK/backend mismatch check) before the first real run. No further research needed — this is now an execution-time verification, not an open question.

2. **RESOLVED — Whether the MLflow Helm chart's `podSecurityContext`/`securityContext` defaults (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`) are compatible with the SQLite-on-PVC write path without additional tuning**
   - What we know: The chart sets these security defaults (read directly from `values.yaml` this session) and separately provides a `storage.mountPath: /mlflow` PVC mount for the SQLite file.
   - What's unclear: Whether the default `fsGroup: 1000` is sufficient for the MLflow server process to write `/mlflow/mlflow.db` without a permission error — not verified in this research pass (would require an actual cluster to test).
   - Recommendation: If the MLflow pod CrashLoopBackOffs on startup with a SQLite permission error, check `kubectl logs` for a `sqlite3.OperationalError: unable to open database file` and adjust `podSecurityContext.fsGroup`/`securityContext` overrides accordingly — flag this as a first-hour verification step, not an upfront blocker.
   - **RESOLVED:** this cannot be settled without a live cluster, so it is deliberately deferred to a documented execution-time check rather than left as an unaddressed unknown — `03-04-PLAN.md` Task 2 includes the exact mitigation above (check `kubectl logs`, override `fsGroup` if needed) as part of the MLflow deployment task's acceptance criteria. No further research needed.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | k3d cluster runtime | Yes | 29.1.3 | — |
| `kubectl` (bundles kustomize) | Cluster install, all `kubectl apply -k` steps | Yes | v1.35.4 (kustomize v5.7.1 bundled) | — |
| k3d | Local cluster creation | **No** | — | Install per STACK.md (`curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh \| bash`) before Phase 3 execution begins — no viable fallback, this is REQ-B1's foundation |
| `helm` | MLflow official chart + MinIO community chart install (this research's recommended path) | **No** | — | Install (`curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \| bash` or distro package) before the MLflow/MinIO deployment step; fallback is hand-rolled Deployment/PVC/Service YAML per STACK.md's original (pre-Helm-chart-discovery) suggestion if Helm install itself is blocked |
| RAM | All of Phase 3 (k3d + KFP + MinIO + MLflow + task pods) | Partial | 15Gi total, ~10Gi available at idle (measured via `free -h` this session, before any cluster exists) | None — this is the binding constraint `PITFALLS.md` Pitfall 1 already covers; close other memory-heavy applications before cluster-up per that pitfall's existing guidance |

**Missing dependencies with no fallback:** k3d (must be installed; no alternative satisfies REQ-B1's specific "k3d" requirement from PROJECT.md/ROADMAP.md).

**Missing dependencies with fallback:** `helm` (falls back to hand-rolled manifests if install is blocked in the execution environment — slower/riskier but not blocking).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.x [VERIFIED: pyproject.toml `dev` extra, `pytest~=9.1.0`] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `--cov=lib --cov-fail-under=100`) — already exists, unchanged |
| Quick run command | `scripts/qa.sh test` (already exists, runs `uv run ... pytest`) |
| Full suite command | `scripts/qa.sh test` (same command — this repo's suite is small enough that "quick" and "full" are currently identical; Phase 3 does not need to introduce a split) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| REQ-B2 | Every component signature uses typed artifact params, no raw string paths | static/compile | `scripts/qa.sh test` (new: `tests/pipelines/test_pipeline_compiles.py` inspecting `components/*/component.py` annotations) | ❌ Wave 0 |
| REQ-B3 | No `packages_to_install` anywhere in `components/`/`pipelines/` | static | `grep -rn "packages_to_install" components/ pipelines/` (new: assert-empty pytest test, same pattern as `check_component_boundary.sh`) | ❌ Wave 0 |
| REQ-B4 | Full DAG compiles without error | compile (automated) | `tests/pipelines/test_pipeline_compiles.py::test_train_pipeline_compiles` via `kfp.compiler.Compiler().compile(...)` | ❌ Wave 0 |
| REQ-B4 | A real run reaches `register` or a documented skip-branch | manual-only | N/A — requires k3d + KFP + GHCR images + real TLC data; documented in README with KFP run-UI evidence | N/A |
| REQ-B5 | `parallelism` cap present in compiled IR YAML | static (automated) | `tests/pipelines/test_pipeline_compiles.py::test_parallel_for_capped` parses the compiled YAML for the `parallelism` field | ❌ Wave 0 |
| REQ-B6 | `dsl.Collected` used, not manual artifact stitching | static (automated) | Extend the same compile test: `grep`/source-inspect `pipelines/train_pipeline.py` for `dsl.Collected(` | ❌ Wave 0 |
| REQ-B7 | Deliberately-worse model not registered; better model is | manual-only | N/A — requires two real cluster runs with different model quality; documented in README with MLflow UI/registry evidence | N/A |
| REQ-B8 | Two identical backfill runs produce byte-identical output | manual-only (cluster) + unit (if a deterministic-key function is added to `lib/`) | If Pattern 5's deterministic-key logic lands in `lib/` (e.g. `lib/paths.py::artifact_key(month)`), it gets a `tests/lib/test_paths.py` unit test per this repo's 100%-`lib/`-coverage convention; the actual byte-diff itself is manual/cluster | ❌ Wave 0 (conditional on planner's design choice) |
| REQ-B9 | `ExitHandler` triggers on both success and failure | static (compile) + manual (cluster) | Compile test: assert compiled YAML contains an exit-handler group structure; manual: a deliberately-failed run's log evidence in README | ❌ Wave 0 (static half) |
| REQ-B10 | Cache invalidation demonstrated with a documented input change | manual-only | N/A — requires two real cluster runs; documented in README with the specific input diff and cache-key diff | N/A |
| REQ-B11 | Compiled YAML attached as CI release artifact | CI-verified, not pytest | New CI job in `.github/workflows/ci.yml` (or a release workflow) running `kfp.compiler.Compiler().compile(...)` and uploading the YAML — verified by a green CI run producing a downloadable artifact, not a pytest assertion | N/A (CI config, not test file) |
| REQ-E1/E2/E3 | README sections (architecture diagram, ADRs, Next Steps) present and non-empty | static (automated) | Extend `tests/test_readme.py`'s existing pattern (`_section_body` helper already exists) with new assertions for `## Architecture`, `## ADRs` (or equivalent heading), `## Next Steps` | ❌ Wave 0 (extends existing file) |

### Sampling Rate

- **Per task commit:** `scripts/qa.sh test` (covers all static/compile-time checks above; fast, no cluster needed)
- **Per wave merge:** `scripts/qa.sh lint && scripts/qa.sh typecheck && scripts/qa.sh test && scripts/qa.sh boundary` (existing full local gate)
- **Phase gate:** All of the above green, plus the manual-only cluster checkpoints (REQ-B4's real run, REQ-B7's both-directions promotion, REQ-B8's byte-diff, REQ-B9's failure-path trigger, REQ-B10's cache-invalidation demo) each documented in README with concrete evidence (checksums, run IDs, log excerpts) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/pipelines/__init__.py` + `tests/pipelines/test_pipeline_compiles.py` — covers REQ-B2 (typed-artifact static check), REQ-B4 (compile succeeds), REQ-B5 (parallelism cap present in compiled YAML), REQ-B6 (`dsl.Collected` present), REQ-B9 (exit-handler group present in compiled YAML). This directory does not exist yet; `ARCHITECTURE.md`'s Recommended Project Structure already anticipated it ("`tests/pipelines/` # optional: compile-time DAG shape assertions") but it was never created since Phase 1/2 had no `pipelines/` code to test.
- [ ] A `packages_to_install`-absence static test — either a new pytest test or an extension of `scripts/check_component_boundary.sh` (the latter is more consistent with this repo's existing "mechanical gate, not code review discipline" pattern for REQ-A6/REQ-B3-adjacent rules).
- [ ] Extend `tests/test_readme.py` with assertions for the three new required README sections (REQ-E1/E2/E3) — the file and its `_section_body` helper already exist; this is additive, not new infrastructure.
- [ ] Conditional: if the planner designs a dedicated `lib/` function for the deterministic output-key strategy (Pattern 5), it needs its own `tests/lib/test_<module>.py` file to stay inside the existing 100%-`lib/`-coverage gate (`--cov-fail-under=100` would otherwise fail the moment such a function is added without a test).
- [ ] Framework install: none — pytest/pytest-cov are already installed via the `dev` extra; no new test framework needed for Phase 3.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | Single-user local cluster, no user-facing auth surface; KFP standalone (not multi-user Kubeflow) has no identity layer by design — out of scope per PROJECT.md |
| V3 Session Management | No | Same as above |
| V4 Access Control | No | Single-tenant local cluster; no namespace-as-tenant separation (explicitly out of scope, full multi-user Kubeflow rejected in PROJECT.md's Key Decisions) |
| V5 Input Validation | Yes | `lib/months.py::month_range` already raises `ValueError` on malformed `start_month`/`end_month`; `lib/schemas.py`'s pandera schema already validates ingest-boundary data (REQ-C1, Phase 2). Phase 3 components must let these existing validations surface as loud pipeline failures, not swallow them |
| V6 Cryptography / Secrets | Yes | MinIO root credentials and MLflow's S3 access/secret keys must be K8s Secrets (`kubectl create secret generic`), referenced via `env[].valueFrom.secretKeyRef` in both the MLflow Helm chart values and any component that logs to MLflow — never hardcoded in component code, Dockerfiles, or committed manifests (already flagged as a "never acceptable" shortcut in `PITFALLS.md`'s Technical Debt Patterns table; this research adds no new guidance here beyond confirming the Helm-chart-based deployment path supports Secret references natively) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Hardcoded MinIO/MLflow credentials in component code or Dockerfiles | Information Disclosure | K8s Secrets only, referenced via `secretKeyRef` — never literal values in `components/`/Helm `--set` history/git |
| Floating/mutable image tags (`:latest`, or `env/dev`'s `:master` override — Pitfall 9) | Tampering | Git-SHA image tags (existing CI convention) for `components/*`; explicit `env/platform-agnostic` overlay (not `env/dev`) for the KFP backend itself, verified post-install per Pitfall 9 |
| Public GHCR packages (no `imagePullSecrets`) | Information Disclosure | Accepted risk for this mock/portfolio project, already documented as such in `PITFALLS.md`'s Technical Debt Patterns table — no new mitigation needed, just keep the existing README disclosure |
| Malformed pipeline parameters (`start_month`/`end_month`, `months` list) reaching a component uncaught | Tampering / Denial of Service (a malformed value crashing a pod mid-run in a confusing way) | Rely on `lib/months.py`'s existing `ValueError` surfacing cleanly through the component (let it propagate as a component failure with the original message, don't catch-and-obscure it) |
| Credential leakage via the ExitHandler notify task's structured log line (D-11) | Information Disclosure | The notify pattern in Code Examples above only logs `PipelineTaskFinalStatus` fields and run identifiers — never include `AWS_SECRET_ACCESS_KEY`/MinIO credentials/MLflow tracking-URI-with-embedded-auth in any printed log line |

## Sources

### Primary (HIGH/MEDIUM confidence — read directly this session)

- `github.com/kubeflow/pipelines` — `manifests/kustomize/env/{platform-agnostic,dev}/kustomization.yaml`, `manifests/kustomize/base/pipeline/kustomization.yaml`, at tag `2.17.0`, read via `gh api` — [VERIFIED: this session]
- `github.com/kubeflow/pipelines` — tags list (confirms 2.17.0 is latest) — [VERIFIED: this session]
- `github.com/mlflow/mlflow` — `charts/values.yaml`, `charts/Chart.yaml`, `charts/templates/` listing, read via `gh api` — [VERIFIED: this session]
- `github.com/minio/minio` — `helm/minio/README.md`, read via `gh api` — [VERIFIED: this session]
- kubeflow.org control-flow docs (`dsl.ExitHandler`, `dsl.PipelineTaskFinalStatus`) — fetched via context7 (`/kubeflow/pipelines`, `/websites/kubeflow_components_pipelines`) — [CITED: official docs, MEDIUM per this session's classify-confidence seam]
- `kubeflow/pipelines#10187` (GitHub issue) — exit task cannot depend on outputs of tasks inside its own scope — [CITED: community-confirmed GitHub issue, cross-checked against the official docs' construction-order example]
- Empirical test: `pandas.to_parquet`/`lgb.Booster.model_to_string()` byte-determinism, run against this repo's exact pinned `pandas==2.3.3`/`pyarrow==25.0.1`/`lightgbm==4.7.0` — [VERIFIED: executed this session via `uv run`]
- `pip index versions kfp` / `kfp-kubernetes` / `boto3` — PyPI registry checks — [VERIFIED: this session]
- `gh release list --repo k3d-io/k3d` — [VERIFIED: this session]
- This repo's own `pyproject.toml`, `lib/registry.py`, `lib/train.py`, `lib/evaluate.py`, `lib/ingest.py`, `lib/features.py`, `lib/months.py`, `components/ingest/{main.py,Dockerfile}`, `tests/test_readme.py`, `tests/lib/test_registry.py`, `scripts/qa.sh`, `scripts/check_component_boundary.sh`, `.github/workflows/ci.yml` — [VERIFIED: read directly this session]

### Secondary (MEDIUM confidence)

- WebSearch on MinIO's default Helm chart memory request (16Gi) — corroborated by the chart's own README "toy setup" example showing an explicit override, consistent finding across two independent sources

### Tertiary (LOW confidence)

- None used for load-bearing claims in this document — every finding above was corroborated against a primary source (official repo file or empirical test) before being included.

## Metadata

**Confidence breakdown:**
- KFP install path (Q1): HIGH — direct primary-source file reads at the pinned tag, cross-checked against the live tags list
- MLflow/MinIO deployment (Q2): MEDIUM-HIGH — chart source files read directly; exact published OCI/Helm-repo version numbers not pinned (chart versions move independently of app versions, flagged in Assumptions Log)
- Idempotency/byte-determinism (Q3): HIGH — empirically verified in this repo's own pinned environment, not just documentation-sourced
- ExitHandler/PipelineTaskFinalStatus (Q4): HIGH — official docs example plus a corroborating GitHub issue for the scope-limitation finding
- Validation Architecture (Q5): MEDIUM — derived from this repo's existing, already-established test conventions (`test_readme.py` pattern, `--cov-fail-under=100`, `check_component_boundary.sh`), extended by inference to Phase 3's new surface area rather than independently re-verified against an external source

**Research date:** 2026-08-24
**Valid until:** 7 days for the KFP-overlay/MLflow-chart/MinIO-chart version specifics (fast-moving: chart versions and the kubeflow.org docs page content can change independently of the underlying 2.17.0/3.15.1 pins); 30 days for the ExitHandler/idempotency architectural findings (stable SDK behavior, unlikely to change before Phase 3 execution)
</content>
