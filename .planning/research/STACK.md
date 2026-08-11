# Stack Research

**Domain:** Batch ML training pipeline on Kubeflow Pipelines (KFP) v2 standalone, k3d-hosted, MLflow-backed model registry
**Researched:** 2026-08-11
**Confidence:** MEDIUM (version numbers verified against live PyPI/GitHub sources during this research session; no MCP docs provider or package-registry sandbox was available in this environment, so treat exact patch versions as a snapshot to re-verify at `uv add` time, not a hard pin to defend in an ADR)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **KFP SDK** (`kfp`) | 2.17.0 | Author pipelines/components as Python, compile to IR YAML | Current stable v2 SDK line (v1 is EOL/legacy). Supports Python 3.9–3.13, `dsl.container_component`, `dsl.If`/`dsl.OneOf`, `dsl.ParallelFor`, `ExitHandler`, typed artifacts — every DAG feature PROJECT.md requires. Pin exact patch version in `pyproject.toml`; SDK and backend versions must match (see Version Compatibility). |
| **KFP backend (standalone)** | 2.17.0 (match SDK) | Runs the pipeline API server, persistence agent, MLMD metadata store, cache server, Argo Workflows controller | "Standalone" kustomize overlay (`manifests/kustomize`, no Istio/Dex/central dashboard) is the only realistic choice for a 16GB laptop — full multi-user Kubeflow adds an auth/mesh layer that teaches nothing the JD asks for and roughly doubles pod count. |
| **k3d** | v5.9.0 (bundles k3s, image pinnable e.g. `rancher/k3s:v1.32.x-k3s1`) | Runs a real Kubernetes cluster (k3s) inside Docker, single binary, disposable | Lightest way to get a genuine multi-node-capable Kubernetes API on a laptop. Prefer k3d over kind/minikube here specifically because `k3d cluster create --agents-memory`/`--servers-memory` and `--registries-create` give you a local registry mirror for free — useful since you're building custom images in CI and want to `k3d image import` or push to a local pull-through cache without round-tripping through GHCR on every iteration. |
| **MLflow** | 3.15.1 (server + client) | Experiment tracking + model registry (champion/candidate promotion) | MLflow 3.x is current major; the client is backward-compatible enough with a 2.x-speaking server for one-major-version skew, but **run matching major versions on client and server** to avoid the documented edge cases. MLflow 3 made **models first-class entities** (`mlflow.<flavor>.log_model(name=...)` instead of `artifact_path=...`) and **replaced registry stages with aliases** (`@champion`/`@candidate`) — this directly maps to the "register only if RMSE beats champion" requirement, use `set_registered_model_alias`, not the deprecated `transition_model_version_stage`. |
| **MinIO** | latest `RELEASE.2025-xx` server image (`minio/minio:latest` pinned to a dated tag at install time) | S3-compatible object store for MLflow artifacts (and optionally KFP pipeline artifacts) | S3-compatible, single static binary, ~1Gi memory request is enough for single-node local dev — the standard choice for giving MLflow an artifact store without AWS. **Important 2025/2026 correction**: KFP's own standalone manifests stopped bundling MinIO as of KFP 2.15 (see Version Compatibility) — don't assume KFP "comes with" MinIO anymore. |
| **LightGBM** | 4.7.0 (Python package) | Gradient-boosted tree regressor for trip-duration prediction | Matches PROJECT.md's "boring, no tuning theater" model choice; trains fast on CPU (fits a 16GB laptop, no GPU needed), native pandas DataFrame + categorical-column support avoids manual one-hot encoding, which keeps the `lib/` feature code smaller. |
| **pandera** | 0.32.1 | Schema validation at the ingest boundary ("bad month fails loudly") | Purpose-built for exactly this: declarative pandas DataFrame schemas with dtype/range/nullability checks, raises on the first bad batch instead of failing silently three components downstream. `pandera` 0.30.0+ added `pandas>=3` support if you do choose pandas 3 later. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pandas` | **2.3.x** (pin explicitly — see rationale below, not 3.0.x) | DataFrame engine for `lib/` feature logic | Default for all `lib/` pandas work. See "What NOT to Use" for why 3.0 is deliberately deferred here. |
| `numpy` | 2.5.x (numpy 2.x line; whatever `pandas==2.3.x` pins) | Vectorized haversine distance, dtype downcasting | `lib/` feature computations — this is where the vectorization benchmark work lives. |
| `pyarrow` | latest compatible with pinned pandas | Parquet I/O for NYC TLC monthly files, backs pandas' nullable/string dtypes | Read/write Parquet in the ingest component; also lets pandas use Arrow-backed string dtype today (opt-in) instead of waiting for pandas 3's default. |
| `mlflow[extras]` client only in component images | 3.15.1 | Log params/metrics/model from the `train`/`evaluate`/`register` components | Component images that talk to MLflow only need the `mlflow` client package + `boto3` (for the MinIO S3 endpoint), not the full server. |
| `boto3` | latest | S3 client used by MLflow's client SDK to reach MinIO (`MLFLOW_S3_ENDPOINT_URL`) | Any component logging artifacts to MinIO via MLflow. |
| `kfp-kubernetes` | matches `kfp` minor (2.x) | Kubernetes-specific pipeline extensions (PVC mount, secret mount) if a component needs cluster resources beyond typed artifacts | Only pull this in if a component needs a mounted Secret/PVC directly — most of this project's components shouldn't need it since typed artifacts already handle data passing. |
| `pandas-stubs` | matching pandas minor | Type stubs so `mypy --strict` can actually check `lib/` pandas code | Dev dependency; without it `mypy --strict` on pandas-heavy code is mostly `Any` noise. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Fast Python package/venv manager, single lockfile-per-package workflow | Version 0.12.x line. Use a `uv` workspace (`[tool.uv.workspace]` at repo root) so `lib/`, each `components/*` package, and `pipelines/` share one resolved lockfile but can still each declare their own `pyproject.toml` for per-component Docker image builds — this is the standard 2025/2026 monorepo pattern for uv and avoids dependency drift between what CI tests and what the component image ships. |
| `ruff` | Lint + format (replaces flake8/isort/black) | Version 0.16.x. Single tool, single config block in `pyproject.toml` (`[tool.ruff]`), fast enough to run on every save; use `ruff check --fix` + `ruff format` as the two CI/pre-commit steps. |
| `mypy` | Static typing, `--strict` on `lib/` | Version 2.3.x. Only `--strict` on `lib/` per PROJECT.md — component wrapper code and pipeline DSL code can stay looser since KFP's own decorators are only partially typed. |
| `pytest` | Unit tests on `lib/` with synthetic DataFrame fixtures | Version 9.1.x. Use `pandas.testing.assert_frame_equal` for the "assert exact output values" requirement, not looser equality checks. |
| `pre-commit` | Git-hook mirror of CI checks | Config: `ruff check`, `ruff format --check`, `mypy` (on `lib/` only), a fast `pytest -q` subset if feasible pre-commit, else defer full suite to CI. |
| `docker/build-push-action@v7` + `docker/login-action@v4` + `docker/setup-buildx-action@v4` | Build and push component images to GHCR from GitHub Actions | Use `cache-from: type=gha` / `cache-to: type=gha,mode=max` — this is the current standard GHA Docker layer cache and matters a lot here since you're rebuilding several component images per PR. |
| `k3d` local registry (`k3d registry create` / `--registries-create`) | Optional pull-through cache so k3d doesn't re-pull every GHCR image on every pipeline run | Saves laptop bandwidth/time during iterative Phase 2 development; not required, but recommended given the 1-week budget. |

## Installation

```bash
# --- Local toolchain (host machine) ---
curl -LsSf https://astral.sh/uv/install.sh | sh        # uv (package/venv manager)
uv python install 3.12                                  # pin Python 3.12 across the repo

# --- Repo/monorepo Python deps (run from repo root, uv workspace) ---
uv init --workspace                                      # once, at repo root
uv add --package lib pandas==2.3.* numpy pyarrow pandera
uv add --package lib --dev pytest pandas-stubs mypy ruff
uv add --package components-train lightgbm mlflow boto3 kfp==2.17.*

# --- Local Kubernetes cluster ---
brew install k3d   # or curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
k3d cluster create mlops \
  --servers 1 --agents 0 \
  --servers-memory 6Gi \
  --registries-create \
  --wait

# --- KFP standalone (backend) ---
export PIPELINE_VERSION=2.17.0
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/platform-agnostic?ref=$PIPELINE_VERSION"
kubectl wait pods -n kubeflow -l app=ml-pipeline --for condition=ready --timeout=300s

# --- MinIO (dedicated, for MLflow artifact store) ---
# Single-pod, no distributed mode, no Operator — a plain Deployment+PVC+Service manifest
# (or `minio/minio` Helm chart with --set mode=standalone --set resources.requests.memory=512Mi)
kubectl create namespace mlflow
kubectl apply -f minio-standalone.yaml -n mlflow

# --- MLflow (tracking server + registry) ---
# SQLite backend store (file-based, no separate Postgres pod) + MinIO artifact store
mlflow server \
  --backend-store-uri sqlite:////mlflow/mlflow.db \
  --default-artifact-root s3://mlflow-artifacts/ \
  --host 0.0.0.0
# with MLFLOW_S3_ENDPOINT_URL pointed at the in-cluster MinIO service
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| KFP v2 standalone on k3d | Full multi-user Kubeflow (Istio + Dex + Central Dashboard, via `kubeflow/manifests`) | Only if the JD/role actually operates the multi-user platform layer (auth, namespaces-as-tenants) — this JD doesn't; standalone gets you 100% of the DSL/orchestration surface the JD tests for with a fraction of the pods. |
| k3d (k3s in Docker) | kind, minikube | `kind` is a close second and equally light: use it if you hit k3d-specific quirks (there are occasional k3d+Traefik ingress conflicts). `minikube` is heavier (its own VM/driver layer) — skip it for this project. |
| MLflow (self-hosted) | Weights & Biases, Neptune, plain "pickle + S3 path" registry | Only if the JD specifically named a different tracking tool — it doesn't; MLflow's model registry + alias-based promotion is the direct fit for the "register only if RMSE beats champion" requirement and is free/self-hostable, unlike W&B/Neptune's hosted-first model. |
| pandas 2.3.x | pandas 3.0.x | Once you've shipped this project and have slack to debug copy-on-write/string-dtype fallout separately from learning Kubernetes for the first time — see "What NOT to Use." |
| LightGBM | XGBoost, scikit-learn `HistGradientBoostingRegressor` | XGBoost is an equally valid "boring GBM" choice if the JD or team explicitly standardizes on it; scikit-learn's HGBR is fine for smaller data but has weaker native categorical support, meaning more `lib/` encoding code for no benefit here. |
| MinIO (dedicated pod, for MLflow) | Let KFP's bundled SeaweedFS double as MLflow's artifact store too | Only attempt this if you're comfortable digging into KFP's `pipeline-install-config`/artifact-secret wiring under time pressure — SeaweedFS is S3-compatible so it's *possible*, but it's undocumented for this exact use and not worth the risk in a 1-week budget. Running one small dedicated MinIO pod for MLflow is simpler and safer. |
| SQLite backend store for MLflow | Postgres/MySQL backend store for MLflow | Switch to Postgres only if multiple concurrent writers are hitting the tracking server (a real team) — for a single-user local project, SQLite avoids running a whole extra stateful pod on a RAM-constrained cluster. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| Full Kubeflow (Istio/Dex/multi-user) manifests | Adds a service mesh, auth proxy, and per-namespace profile controller — several more pods and a nontrivial amount of setup/debugging surface for zero JD-relevant learning; PROJECT.md already rules this out explicitly. | KFP standalone kustomize overlay only. |
| `packages_to_install=[...]` on `@dsl.component` for anything beyond trivial one-off components | Installs deps at every pipeline run from PyPI inside the default KFP base image — slow, non-reproducible, and explicitly against PROJECT.md's "custom component images built in CI" requirement. | `@dsl.component(base_image="ghcr.io/<org>/<component>:<sha>")` or `@dsl.container_component` pointing at a CI-built, GHCR-hosted image. |
| Assuming KFP standalone still bundles MinIO by default | As of **KFP 2.15**, the default standalone/platform-agnostic kustomize overlay swapped its bundled S3-compatible object store from MinIO to **SeaweedFS** (`third-party/seaweedfs`, no `third-party/minio` base exists in the 2.17.0 manifests tree anymore). If you follow an older tutorial/blog assuming a bundled `minio-service`, you'll be confused when it's SeaweedFS instead. | Deploy your own small dedicated MinIO pod for MLflow's artifact store (see Installation); leave KFP's internal SeaweedFS store alone for pipeline artifacts — both are S3-compatible, so typed artifacts (`Input[Dataset]`, `Output[Model]`) behave identically either way. |
| pandas 3.0.x for this project's timeframe | Released Jan 2026; ships **copy-on-write as the only mode** and a **default string dtype** — both are exactly the class of subtle-breakage risk (silent behavior changes in indexing/assignment, `.apply()`/dtype edge cases) that costs debugging time disproportionate to a 1-week, first-time-Kubernetes budget. Ecosystem compatibility (LightGBM, pandera, pyarrow) is still settling as of this research date. | pandas 2.3.x — mature, well-documented, the version most current tutorials/blog posts (including the KFP+MinIO ones found in this research) still use. Revisit pandas 3 after the JD-relevant skills are proven. |
| MySQL/Postgres pod for MLflow's backend store, on this hardware | An extra stateful pod (plus its PVC) for a single local user provides no benefit and costs real RAM on a 16GB machine already running k3d + KFP's own bundled MySQL + SeaweedFS + Argo. | `sqlite:///` backend store URI for MLflow — file-based, zero extra pods. |
| `minikube` | Heavier VM/driver overhead than k3d for equivalent functionality; no benefit for this use case. | `k3d` (or `kind` as a close second). |
| Hyperparameter tuning frameworks (Optuna, Katib, etc.) | PROJECT.md explicitly defers this — "no tuning theater." | Fixed, documented LightGBM hyperparameters. |

## Stack Patterns by Variant

**If RAM pressure is severe once everything is running (k3d + KFP's ~10-12 pods + MinIO + MLflow):**
- Use `k3d cluster create --agents 0` (single-node, no separate agent VMs) rather than a multi-node k3d topology.
- Cap `dsl.ParallelFor` concurrency explicitly (e.g. `parallelism=2`) — the fan-out over months is the single biggest concurrent-pod-count driver in this pipeline.
- Set explicit low `resources.requests`/`limits` on your custom component containers (LightGBM training on a 12-month window is small data — don't let it request more than ~1-2Gi).
- Because 16GB is reported (community-wide) as right at the *minimum* threshold for standalone KFP alone, close other memory-heavy apps (browser, IDE indexing) while running pipeline executions, and prefer running MLflow's server as a plain `mlflow server` process outside the cluster (on the host, or as a single lightweight pod) rather than adding it as a heavier Helm-chart deployment.

**If you want a tighter, single-object-store setup instead of two S3-compatible stores (SeaweedFS for KFP + MinIO for MLflow):**
- This is a valid "advanced" optimization but not the recommended default here — see "What NOT to Use." Only pursue it if Phase 2 resource pressure genuinely requires shaving one more pod, and budget extra time for the kustomize patch work.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `kfp==2.17.0` (SDK) | KFP backend `2.17.0` (kustomize `?ref=2.17.0`) | SDK-compiled IR YAML must match a backend that understands that `pipelineSpec` schema version; keep SDK and backend pinned to the same release tag to avoid "unsupported pipeline spec" errors — a very common first-timer trap. |
| KFP standalone manifests `2.17.0` | k3s / Kubernetes ≥ 1.14 (kustomize-native `kubectl`) | No hard upper bound found in this research pass; k3d v5.9.0's default k3s line (~1.32+) is well within range — verify with `kubectl version` after cluster create. |
| `pandera>=0.30.0` | `pandas>=3` (and still supports 2.x) | Not a blocker either way; recommendation above to stay on pandas 2.3.x is a risk-management choice, not a pandera compatibility requirement. |
| `mlflow==3.15.1` client | MLflow server up to one major version away (2.x server) | Backward-compatible but "may lead to unexpected behavior" per MLflow's own migration guide — run client and server on matching major version (3.x/3.x) here since you control both ends. |
| `lightgbm==4.7.0` | numpy 2.x, pandas DataFrame input | No confirmed incompatibility found with pandas 2.3.x or numpy 2.x during this research pass; treat as the safe pairing. Explicit pandas-3.0 compatibility for LightGBM was not confirmed as of this research date — another reason to stay on pandas 2.3.x for now. |
| `uv` workspace | Multiple `pyproject.toml` (one per `components/*`, one for `lib/`) | Standard current (2025/2026) uv monorepo pattern — one root lockfile, per-package builds; each component's Dockerfile does `uv sync --package <name>` to get a minimal, reproducible image. |

## Sources

- PyPI package pages (fetched live): `kfp`, `mlflow`, `pandera`, `lightgbm`, `pandas`, `numpy`, `uv`, `ruff`, `mypy`, `pytest` — version numbers, confidence: MEDIUM (single-source live fetch, not cross-checked against a second registry mirror).
- `github.com/kubeflow/pipelines` — releases page, `manifests/kustomize` tree at tag `2.17.0` (`third-party/` directory listing, `env/platform-agnostic/kustomization.yaml`, `seaweedfs/README.md`) — confidence: MEDIUM-HIGH (primary source repo, directly inspected at the pinned tag).
- `kubeflow.org/docs/components/pipelines/*` — Containerized/Lightweight Python Components, Container Components docs — confidence: MEDIUM (official docs, not cross-verified against a second source in this pass).
- `mlflow.org/docs/latest/ml/mlflow-3/breaking-changes`, MLflow model registry workflow docs — confidence: MEDIUM.
- `pandas.pydata.org` — "Pandas 3.0 Released!" blog post, `whatsnew/v3.0.0.html` — confidence: MEDIUM-HIGH (official project blog/docs).
- `blog.min.io` — "Setting up a Development Machine with Kubeflow Pipelines 2.0 and MinIO" — confidence: LOW-MEDIUM (vendor blog, useful for pattern confirmation, not authoritative on current defaults given the SeaweedFS migration it predates).
- General web search (community reports on KFP local-cluster RAM usage, k3d memory flags, GHA Docker build-push patterns) — confidence: LOW-MEDIUM, used only for resource-sizing guidance and CI action version numbers, not for anything safety/correctness-critical.
- No MCP documentation provider (context7/exa/etc.) was available in this execution environment; all findings came from `WebSearch`/`WebFetch` against live public pages. Re-verify exact patch versions with `uv add <pkg>` / `pip index versions <pkg>` at implementation time before locking them into an ADR.

---
*Stack research for: Batch ML training pipeline on Kubeflow Pipelines v2 standalone (k3d, MinIO, MLflow, LightGBM)*
*Researched: 2026-08-11*
