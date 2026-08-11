# Pitfalls Research

**Domain:** Batch ML pipeline orchestration — Kubeflow Pipelines v2 standalone on k3d, 16GB laptop, first-time K8s user, 10-15h/1-week budget
**Researched:** 2026-08-11
**Confidence:** MEDIUM-HIGH (KFP/k8s mechanics are HIGH confidence from official docs and GitHub issues; exact behavior on this project's specific k3d/KFP version combo is unverified until Phase 1 install — treat version-pinning advice as mandatory, not optional)

## Critical Pitfalls

### Pitfall 1: k3d does not actually enforce the memory cap you think you gave it

**What goes wrong:**
On Linux, k3d nodes are plain Docker containers sharing the host kernel — there is no VM boundary like Minikube/Docker Desktop. `k3d cluster create --servers-memory 8G` only fakes `/proc/meminfo` for cAdvisor/kubelet's own accounting; it does **not** create a cgroup memory limit unless you separately constrain the Docker container. Result: the kubelet *thinks* it has a fixed budget for eviction decisions, but the host's actual OOM killer can still nuke k3d's own containerd/server process (killing the whole cluster) when total host memory pressure spikes — not just the offending pod. On Docker Desktop (macOS/Windows) the effective cap is whatever memory you gave Docker Desktop's VM, which is a *harder* boundary but shrinks the budget for MinIO+MLflow+KFP+component pods all sharing it.

**Why it happens:**
People assume k3d works like Minikube (real VM, hard cgroup limit) and set `--servers-memory`/`--agents-memory` expecting Kubernetes-level eviction to protect the host. It doesn't fully — it's advisory for the scheduler, not a hard container cgroup limit on native Linux.

**How to avoid:**
- Budget conservatively: on a 16GB laptop, assume ~10-11GB usable for k3d + all workloads after OS/browser/IDE overhead — do not plan to use the full 16GB.
- Set explicit `resources.requests`/`.set_memory_limit()` on every component (not just ParallelFor branches) so the k8s scheduler itself refuses to overcommit, rather than relying on `--servers-memory` alone.
- Keep KFP, MinIO, and MLflow as the only always-on services; don't also run a local Jupyter/IDE-in-container or a second cluster.
- Watch `docker stats` (not just `kubectl top`) during first ParallelFor test run — this shows real host memory, which is the number that actually kills things.

**Warning signs (first hour):**
`k3d cluster create` succeeds but pods sit in `Pending` with `Insufficient memory`, or — worse — the whole cluster becomes unreachable and `kubectl get nodes` hangs (host OOM killed containerd, not a graceful k8s eviction).

**Phase to address:** Phase 2 (k3d + KFP standalone install) — set the memory ceiling and per-component resource requests before building the DAG, not after hitting the wall.

---

### Pitfall 2: KFP SDK version vs. backend version mismatch silently drops your resource limits

**What goes wrong:**
A real, confirmed KFP bug (GitHub #11390): pipelines compiled with SDK 2.10 render resource fields as `resourceCpuLimit`/`resourceMemoryLimit`, while older KFP backends (2.9.x-line standalone deployments) expect `cpuLimit`/`memoryLimit`. If SDK and backend versions don't line up, `.set_memory_limit()`/`.set_cpu_limit()` calls compile without error but are **silently ignored at runtime** — every component runs unbounded, which is exactly the failure mode this project depends on `set_memory_limit` to prevent on ParallelFor fan-out.

**Why it happens:**
`pip install kfp` grabs latest SDK by default; the standalone manifest YAML pinned in the install guide is often a version behind. Nothing errors — the pipeline compiles and runs, just without the limits applied, so it's invisible until a component actually OOMs.

**How to avoid:**
- Pin the KFP Python SDK version to match the exact standalone manifest version you install (check the manifest's release tag, `pip install kfp==<that version>`).
- After first compile, `grep -i "cpuLimit\|resourceCpuLimit" pipeline.yaml` to confirm the field name your SDK emitted, and cross-check it appears as a real k8s `resources:` block on the running pod (`kubectl get pod <name> -o yaml | grep -A4 resources`) — do this once, early, not after ParallelFor breaks.
- Don't chase the newest SDK release for this project; older/stable paired with a matching backend is safer than "latest" on both sides independently.

**Warning signs (first hour):**
`kubectl get pod -o yaml` on a running component shows no `resources.limits` block despite `.set_memory_limit()` in the pipeline code.

**Phase to address:** Phase 2 (immediately after first successful pipeline compile+run, before wiring ParallelFor).

---

### Pitfall 3: Custom component images fail with ImagePullBackOff from GHCR

**What goes wrong:**
`@dsl.container_component`/`@dsl.component(base_image=...)` pointing at `ghcr.io/<org>/<image>:<tag>` compiles fine, but the pod fails with `ImagePullBackOff`/`ErrImagePull` because the k3d cluster has no credentials for GHCR, even if the image is public-but-org-scoped or private. Kubernetes needs its own `imagePullSecrets`, independent of whether `docker login` works on the host machine.

**Why it happens:**
Local `docker pull` works (developer's Docker CLI is authenticated) but k3d's containerd inside the cluster nodes has separate, empty credential state. This is the single most common first-K8s-project gotcha with any private/org registry.

**How to avoid:**
- Make GHCR packages **public** for this mock project (simplest — no secret needed) unless there's a reason not to.
- If private: `kubectl create secret docker-registry ghcr-creds --docker-server=ghcr.io --docker-username=<user> --docker-password=<PAT with read:packages> -n <namespace>`, then reference via `imagePullSecrets` on the KFP pipeline's default service account or per-task, or `k3d image import` for truly local-only testing before pushing.
- Verify image pull works with a bare `kubectl run test --image=ghcr.io/... --rm -it -- sh` before wiring it into the full pipeline — isolates registry auth from pipeline-compile issues.

**Warning signs (first hour):**
`kubectl get pods` shows `ImagePullBackOff`; `kubectl describe pod` error mentions `unauthorized` or `denied` for the ghcr.io image, not a "not found."

**Phase to address:** Phase 1 (CI image build/push) — verify pull-ability from a real k8s pod as an exit criterion of the CI phase, not just that `docker push` succeeded.

---

### Pitfall 4: `dsl.ParallelFor` has no default concurrency cap — 12 months = 12 simultaneous pods

**What goes wrong:**
Without an explicit `parallelism=` argument, `dsl.ParallelFor(items)` lets Argo Workflows (KFP v2's underlying engine) schedule as many iterations concurrently as the DAG allows. Fanning out ingest+validate across a 12-month backfill list with no cap means up to 12 pods (each loading a month of Parquet + pandas) can spin up at once — trivially exceeding 16GB.

**Why it happens:**
The natural-looking code `with dsl.ParallelFor(months) as month:` is exactly the same whether you cap it or not, so the OOM only appears at actual scale (full 12-month backfill), not the 1-2 item smoke test used during development — it "works" in every quick test and then falls over on the real run.

**How to avoid:**
- Always pass `dsl.ParallelFor(months, parallelism=2)` (or 3 at most) — cap explicitly from the first version, don't add it "later."
- Combine with per-task `.set_memory_limit('1G')`/`.set_cpu_limit('1')` on the ingest/validate components (contingent on Pitfall 2 being resolved first — verify the limit actually lands).
- Test the OOM boundary deliberately with `parallelism=4` on a throwaway 2-3 month subset before committing to the real 12-month run, so the failure is cheap and fast rather than a 45-minute backfill dying at minute 40.

**Warning signs (first hour of running full ParallelFor):**
`kubectl get pods` shows several `ingest-*`/`validate-*` pods `Running` simultaneously with no stagger; `kubectl top pods` (if metrics-server present) or `docker stats` climbs steadily toward host limit as more iterations start rather than plateauing.

**Phase to address:** Phase 2 (ParallelFor implementation) — set `parallelism` in the same commit that introduces the loop, verified against Pitfall 1's memory budget.

---

### Pitfall 5: Backfill "idempotency" is broken by default because KFP writes outputs to a run-ID-scoped path

**What goes wrong:**
KFP v2's default `pipeline_root` layout writes component outputs to a path that includes the unique run ID / execution ID (e.g., `s3://bucket/pipeline-root/<run-id>/<task>/<artifact>`). Running the *same* backfill parameters (`start_month`/`end_month`) twice produces **two different runs with two different output paths** — not a true idempotency proof, because nothing was ever overwritten or compared. "Byte-identical output" requires the pipeline to deliberately write to a deterministic, parameter-derived key (e.g., `s3://bucket/features/{month}.parquet`), not rely on KFP's auto-generated run-scoped artifact URI.

**Why it happens:**
Typed artifacts (`Output[Dataset]`) make it easy to assume "the artifact system handles versioning/storage correctly," but KFP's artifact URIs are about *lineage tracking*, not about idempotent target-location semantics — those are two different concerns the SDK doesn't unify for you.

**How to avoid:**
- Inside the component, explicitly construct the output object key/path from the pipeline parameter (month), not from the KFP-assigned artifact URI — write to a deterministic S3 key, and have the artifact metadata point at that same deterministic key.
- Idempotency test = run backfill with the same `start_month`/`end_month` twice, then diff the **deterministic S3 keys** (checksum/etag comparison), not the two KFP run records.
- Decide the overwrite semantics up front (full overwrite of the target key is simplest and matches the "batch pipeline idempotency" industry pattern) rather than append/merge, which is much harder to make byte-identical.

**Warning signs (first hour of designing this):**
Realizing the "idempotent backfill" README claim can't be verified because there's no single stable path to diff between two runs — this should surface at design time, not after both runs execute.

**Phase to address:** Phase 2 (backfill implementation) — decide the deterministic-key strategy before writing the first ingest component, since it affects every component's output-writing code, not just backfill.

---

### Pitfall 6: KFP execution caching hashes the component + inputs, not the artifact's actual bytes or your data source

**What goes wrong:**
KFP v2's cache key is computed from the component definition (image digest/tag, command, code) plus its **input values/artifact references** — not from a hash of the artifact's actual content, and not from anything about the upstream data source (e.g., NYC TLC's file changing at the same URL). Two common surprises: (1) using a mutable image tag (`:latest`) means the cache key doesn't change when you rebuild the image with new code, so a cached (stale) result gets reused even though the "logic changed"; (2) re-running the same pipeline with the same month parameter after the underlying source Parquet file was silently updated will hit cache and use old data.

**Why it happens:**
"Cache key = component + inputs" sounds like it would catch code changes, but only does so reliably if the image reference itself changes (i.e., a new tag/digest) — teams that don't retag per-build get invisible staleness.

**How to avoid:**
- Tag every CI-built component image with the git SHA (not `:latest`) so any code change produces a new image reference and therefore a new cache key automatically.
- For the deliberate "invalidate cache" demonstration this project wants: change a component's declared input value (e.g., bump a threshold parameter) — that's the cleanest, most explainable invalidation to document in the README, rather than relying on subtler image-tag mechanics.
- Explicitly call out in the README that KFP caching does not detect upstream data drift at a fixed URL/path — document this as a known limitation, since it's a legitimate and common point of confusion, not a project bug.

**Warning signs (first hour of testing caching):**
A pipeline run marked "cached" (green, near-instant) when you expected fresh execution after a code change — check the component's image tag before assuming a KFP bug.

**Phase to address:** Phase 2 (caching phase) — decide the git-SHA image tagging convention in Phase 1's CI setup, since it's what makes caching behave predictably later.

---

### Pitfall 7: MinIO and MLflow end up with two different, colliding storage configurations

**What goes wrong:**
KFP standalone ships its own MinIO instance (for pipeline artifacts) with its own bucket/credentials (commonly `minio`/`minio123`, bucket `mlpipeline`). If MLflow is added as a separate service pointing at either the *same* MinIO instance (different bucket, needs its own bucket created + `MLFLOW_S3_ENDPOINT_URL` set correctly) or a *second* MinIO instance, it's easy to get endpoint URL, credentials, or bucket-existence wrong — commonly surfacing as `EndpointConnectionError`, S3 signature/region errors, or artifacts silently landing in the wrong bucket. A frequent specific trap: setting `MLFLOW_S3_ENDPOINT_URL` to a `localhost`-forwarded address that only resolves from the host machine, not from inside a pod (pods must use the in-cluster service DNS name, e.g. `http://minio-service.kubeflow:9000`, not `localhost:9000` or a host `port-forward` address).

**Why it happens:**
Tutorials mix "how I access MinIO from my laptop browser" (port-forward, localhost) with "how a pod inside the cluster reaches MinIO" (cluster-internal DNS) — these are different addresses and the wrong one only fails once code actually runs inside a pod, not during interactive testing from the host.

**How to avoid:**
- Reuse KFP's existing MinIO instance for MLflow artifacts too (one less service, one less RAM budget line) — create a dedicated `mlflow` bucket in it rather than standing up a second MinIO.
- Set `MLFLOW_S3_ENDPOINT_URL` to the **in-cluster** service DNS (`http://<minio-svc>.<namespace>.svc.cluster.local:9000`) for anything running as a pod, and use `kubectl port-forward` only for host-side debugging/MLflow UI access — never mix the two.
- Set `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (boto3 reads these even for MinIO) as k8s Secrets mounted into both the MLflow server and any component that logs to MLflow, rather than hardcoding in component code.

**Warning signs (first hour of MLflow logging):**
`boto3`/MLflow errors like `EndpointConnectionError`, `SignatureDoesNotMatch`, or artifacts appearing to log successfully from a local test script but failing only when run as a pipeline component.

**Phase to address:** Phase 2 (MLflow integration, after KFP+MinIO is stable) — reuse-not-duplicate MinIO decision should be made before installing MLflow at all.

---

### Pitfall 8: Typed artifacts make `lib/` logic untestable if business logic leaks into the component wrapper

**What goes wrong:**
`Input[Dataset]`/`Output[Model]` typed artifacts only exist inside a compiled-and-run KFP pipeline (they're resolved to local file paths by the KFP executor at runtime). If any real pandas/feature logic lives inside the `@dsl.component`-decorated function itself (rather than being a thin call into `lib/`), that logic becomes untestable without spinning up a full pipeline run — directly contradicting this project's own stated architecture ("lib/ contains 100% of pandas logic; components are thin wrappers"). This is easy to violate incrementally: "just one small transform inline for convenience" inside the component, three times, and testability is gone.

**Why it happens:**
It's fastest to write directly inside the `@dsl.component` function during initial exploration (no import wiring needed), and that code works fine in a pipeline run, so the violation is invisible until someone tries to unit-test it with a plain pytest fixture and can't.

**How to avoid:**
- Enforce mechanically, not just by discipline: a component function body should be import + read artifact `.path` + call one `lib.<module>.<function>()` + write result — nothing else. Code review (even self-review) checklist: "does this component function have any pandas operation that isn't a single `lib` call?"
- Write the `lib/` function and its pytest test *before* wrapping it in a component — this naturally forces the separation since the component literally can't exist yet.
- Artifact reading/writing (the KFP-specific plumbing: `.path`, `.metadata`) is the only thing allowed to live in the component; everything else is a `lib/` import.

**Warning signs (first hour of writing a component):**
Difficulty writing a pytest test for a piece of logic because it requires an `Input[Dataset]` object rather than a plain DataFrame — that's the signal the logic is in the wrong layer.

**Phase to address:** Phase 1 (repo skeleton + lib/ testing discipline) — the architectural rule should be set before the first component is written in Phase 2, not retrofitted.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| `packages_to_install=[...]` on `@dsl.component` instead of custom GHCR image | Skip CI build/push wiring, faster first pipeline run | Violates project's explicit requirement (custom images via CI); pip install runs on every pod start, slow + no reproducibility proof | Never for this project — it's an explicit portfolio requirement, not a nice-to-have |
| Using `:latest` tag for component images | One less versioning decision | Breaks cache-key semantics (Pitfall 6); can't prove which code version a run used | Never — always tag with git SHA |
| Skipping `imagePullSecrets`/making GHCR packages public | Saves 10 minutes of secret setup | None really, for a portfolio mock project with no sensitive code | Acceptable — make packages public, document the tradeoff in README (wouldn't do this for a real employer repo) |
| Hardcoding MinIO/MLflow credentials in component code instead of k8s Secrets | Faster to wire up | Looks unprofessional in a portfolio repo meant to demonstrate production discipline | Never — this project's entire value proposition is "production-grade," so credentials-as-code undermines the point |
| Running full 12-month backfill without first testing `parallelism=2` on 2-3 months | Feels closer to "done" faster | Wastes 30-45 minutes on an OOM crash discovered late in a 10-15h budget | Never — always dry-run at small scale first |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| GHCR (custom images) | Assume local `docker login` auth covers cluster pulls | Public packages, or explicit `imagePullSecrets` k8s Secret |
| MinIO (from pipeline pods) | Use `localhost:9000` (host port-forward address) inside component code | Use in-cluster service DNS name |
| MLflow tracking + MinIO artifact store | Point `MLFLOW_S3_ENDPOINT_URL` at a second, separately-provisioned MinIO with different creds | Reuse KFP's MinIO instance, new bucket, shared Secret |
| KFP SDK ↔ backend version | `pip install kfp` (latest) against an older pinned standalone manifest | Pin SDK version to match installed manifest release tag exactly |
| GitHub Actions → GHCR | Build/push all component images on every PR regardless of what changed | Path-filter the build matrix so only changed component dirs rebuild (saves CI minutes and avoids unnecessary cache invalidation from unrelated changes) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Unbounded `dsl.ParallelFor` | Works fine on 2-item smoke test | Set `parallelism=2` from the start | Full 12-month backfill on 16GB laptop |
| `.apply()` row-wise haversine distance inside a ParallelFor branch | Fine on a 1-month sample | Vectorize (already an explicit project requirement) before wiring into ParallelFor | Multiplied across N concurrent months, CPU-bound stalls compound the RAM pressure window |
| No dtype downcasting before ParallelFor fan-out | Each branch loads full float64 DataFrame | Downcast dtypes in the ingest `lib/` function, verified by a before/after benchmark (already planned) | Memory pressure compounds linearly with `parallelism` value |
| Heavy component base image (full conda/pandas/lightgbm stack) rebuilt on every CI push | CI minutes balloon, local `docker build` disk/RAM spikes on the same 16GB laptop used for k3d | Multi-stage build, layer caching, path-filtered rebuild triggers | Becomes a real time-budget problem once >3-4 components exist |

## "Looks Done But Isn't" Checklist

- [ ] **ParallelFor caps concurrency:** Verify `parallelism=` is actually set — a pipeline that "runs fine" on a 2-month smoke test can still be unbounded and OOM at full 12-month scale.
- [ ] **Resource limits are real, not silently dropped:** Confirm via `kubectl get pod -o yaml` that `.set_memory_limit()`/`.set_cpu_limit()` produced an actual `resources:` block on the pod — don't trust that the pipeline compiled without error (Pitfall 2).
- [ ] **Backfill idempotency is provable:** Confirm there's a single deterministic output key per month that both runs write to and that can be diffed — not two separate KFP-run-scoped artifact paths that were never compared.
- [ ] **Cache invalidation demo is real:** Confirm the README's cache-invalidation example actually shows a fresh (non-cached) execution in the KFP UI after the described input change — not accidentally still hitting cache due to an unrelated `:latest`-tag image.
- [ ] **Custom images are pull-able from inside the cluster:** `docker push` succeeding is not sufficient proof — confirm a pod running inside k3d can actually pull the image (Pitfall 3).
- [ ] **`lib/` logic has no pipeline dependency:** Every function under test with pytest should run with a plain pandas DataFrame fixture, no `Input[Dataset]`/KFP context required.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|-----------------|
| Whole k3d cluster OOM-killed mid-backfill | MEDIUM | `k3d cluster delete && k3d cluster create` with lower `parallelism`/added memory limits; re-run backfill (idempotency design, Pitfall 5, should make this cheap if deterministic keys were used from the start) |
| Discover resource limits were silently ignored (Pitfall 2) after ParallelFor OOM | LOW | Re-pin SDK version, recompile pipeline.yaml, verify via `kubectl get pod -o yaml`, re-run — no data loss if idempotent |
| Cache-invalidation demo doesn't actually invalidate | LOW | Retag image with new git SHA, or change a declared component input value instead of relying on code-only changes |
| MinIO/MLflow credential mismatch discovered late | LOW-MEDIUM | Centralize into one k8s Secret referenced by both services; restart MLflow deployment; re-run one training component to confirm |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| k3d memory not a real hard cap | Phase 2 (install) | `docker stats` monitored during first ParallelFor test; explicit per-component resource requests set |
| KFP SDK/backend version mismatch drops limits | Phase 2 (install, immediately post-compile) | `kubectl get pod -o yaml` shows real `resources:` block matching `.set_memory_limit()` value |
| GHCR ImagePullBackOff | Phase 1 (CI image build) | `kubectl run --image=ghcr.io/...` pull test passes before component is wired into pipeline |
| Unbounded ParallelFor | Phase 2 (ParallelFor implementation) | `parallelism=` set in same commit as the loop; dry run on 2-3 months before full 12-month backfill |
| Non-idempotent backfill via run-scoped paths | Phase 2 (backfill implementation) | Two backfill runs diffed against the same deterministic S3 key, not two KFP run IDs |
| Cache key surprises (`:latest` tag) | Phase 1 (CI tagging convention) + Phase 2 (caching demo) | Every component image tagged with git SHA; README cache-invalidation example verified in KFP UI as non-cached |
| MinIO/MLflow storage collision | Phase 2 (MLflow integration) | MLflow artifact log succeeds from inside a pod (not just host test script) using in-cluster MinIO DNS |
| Business logic leaking into component wrappers | Phase 1 (repo skeleton discipline, enforced through Phase 2) | Every `lib/` function has a pytest test using a plain DataFrame fixture, no KFP context |

## Sources

- [How to install Kubeflow Pipelines v2 on Apple Silicon (Fmind, Medium)](https://fmind.medium.com/how-to-install-kubeflow-on-apple-silicon-3565db8773f3)
- [kubeflow/pipelines#11136 — shared memory attach limitation in KFP SDK v2](https://github.com/kubeflow/pipelines/issues/11136)
- [kubeflow/pipelines#4275 — node low on resource memory](https://github.com/kubeflow/pipelines/issues/4275)
- [k3d-io/k3d#894 — install issues in k3d cluster](https://github.com/k3d-io/k3d/issues/894)
- [k3d-io/k3d discussion #627 — specifying system resource allocation](https://github.com/k3d-io/k3d/discussions/627)
- [Kubeflow Pipelines Standalone Deployment docs](https://www.kubeflow.org/docs/components/pipelines/legacy-v1/installation/standalone-deployment/)
- [Kubeflow Pipelines Installation (operator guide)](https://www.kubeflow.org/docs/components/pipelines/operator-guides/installation/)
- [Kubeflow — Containerized Python Components docs](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/containerized-python-components/)
- [Resolve ImagePullBackOff — private registry auth failures](https://oneuptime.com/blog/post/2026-02-09-imagepullbackoff-registry-auth/view)
- [Kubernetes docs — Pull an Image from a Private Registry](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)
- [Kubeflow — Use Caching docs](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/caching/)
- [How we fixed a Kubeflow pipeline caching issue (Ansu, Medium)](https://medium.com/@ansu513/how-we-fixed-a-kubeflow-pipeline-caching-issue-in-our-componen-d0dc503a467c)
- [kubeflow/pipelines#7201 — cache key input specification feature request](https://github.com/kubeflow/pipelines/issues/7201)
- [kubeflow/pipelines#11390 — kfp 2.10 pipelines ignore cpu/memory requests/limits (resourceCpuLimit key mismatch)](https://github.com/kubeflow/pipelines/issues/11390)
- [kubeflow/pipelines#9087 — resource limits/requests not working in KFP v2](https://github.com/kubeflow/pipelines/issues/9087)
- [kubeflow/pipelines#4089 — parallelism feature request for dsl.ParallelFor](https://github.com/kubeflow/pipelines/issues/4089)
- [kubeflow/pipelines#7454 — per-Op parallelism access request](https://github.com/kubeflow/pipelines/issues/7454)
- [MLflow — Artifact Stores docs](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/)
- [mlflow/mlflow#2599 — cannot log artifact to MinIO with custom region name](https://github.com/mlflow/mlflow/issues/2599)
- [mlflow/mlflow#2630 — S3 artifact doesn't support MLFLOW_S3_ENDPOINT_URL properly](https://github.com/mlflow/mlflow/issues/2630)
- [mlflow/mlflow#9523 — MLFLOW_S3_ENDPOINT_URL causes loading artifacts failure](https://github.com/mlflow/mlflow/issues/9523)
- [Idempotent Pipelines: Build Once, Run Safely Forever (DEV Community)](https://dev.to/alexmercedcoder/idempotent-pipelines-build-once-run-safely-forever-2o2o)
- [Backfilling Historical Data With Idempotent Data Pipelines (ml4devs)](https://www.ml4devs.com/what-is/backfilling-data/)
- [Kubeflow — Execute KFP pipelines locally docs](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/execute-kfp-pipelines-locally/)
- [Kubeflow — Create, use, pass, and track ML artifacts docs](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/)

---
*Pitfalls research for: KFP v2 on k3d, batch ML pipeline, first-time hands-on, 16GB laptop, 10-15h/1-week budget*
*Researched: 2026-08-11*
