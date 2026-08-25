---
phase: 03-kubeflow-pipeline-core-deployment
plan: 04
subsystem: infra
tags: [k3d, kubeflow-pipelines, minio, mlflow, helm, kfp-client, boto3]

# Dependency graph
requires:
  - phase: 03-kubeflow-pipeline-core-deployment
    provides: "03-01/03-02/03-03's compiled DAG, components/ image build, and Docker images (train_pipeline.py, components/*, GHCR image-tag wiring)"
provides:
  - "A running k3d cluster (`mlops`) with KFP standalone 2.17.0 verified at the pinned tag, no Istio namespace"
  - "A dedicated MinIO pod + in-cluster MLflow server (D-12 topology) in the `mlflow` namespace, both Ready and reachable in-cluster"
  - "The `mlflow-minio-creds` Secret in both `mlflow` and `kubeflow` namespaces, no credential in git"
  - "The three MinIO buckets (tlc-raw, mlflow-artifacts, backfill), with tlc-raw pre-loaded from the local TLC cache"
  - "scripts/submit_pipeline.py and scripts/backfill_checksums.py, both verified against the live cluster"
affects: ["03-05"]

# Actuals (#2632)
actuals:
  tokens: 7200
  tasks: 3
  commits: 2

tech-stack:
  added: ["k3d v5.9.0", "helm v3.21.4", "MinIO Helm chart 5.4.0", "MLflow OCI Helm chart 0.1.0 (mlflow v3.14.0-full image)"]
  patterns:
    - "Credentials generated/read from env, passed to Helm only via existingSecret reference, never --set or stdout"
    - "fullnameOverride pinning a chart's release-composite resource name to match code-side DNS assumptions"
    - "Empirical /proc/*/status VmRSS sampling in a throwaway debug pod to size a container memory limit instead of guessing"

key-files:
  created:
    - deploy/03-storage-tracking.sh
    - deploy/04-upload-raw-data.sh
    - deploy/minio-values.yaml
    - deploy/mlflow-values.yaml
    - scripts/submit_pipeline.py
    - scripts/backfill_checksums.py
  modified:
    - pyproject.toml

key-decisions:
  - "Reused the previously-generated MinIO root credentials (read from the existing Secret) rather than regenerating, so the already-Running MinIO pod's live credentials stayed in sync with the Secret."
  - "Set deploy/mlflow-values.yaml's fullnameOverride to \"mlflow\" so the chart's Service name matches pipelines/train_pipeline.py's mlflow_tracking_uri default (http://mlflow.mlflow.svc.cluster.local:5000), instead of the chart's default \"mlflow-mlflow\" composite name."
  - "Sized MLflow's memory limit to 3Gi (request 1536Mi) from an empirically measured ~2.31GiB steady-state RSS, not from guessing worker counts down."
  - "Wrote and verified scripts/submit_pipeline.py and scripts/backfill_checksums.py fully, including a real submission against the live KFP API, despite the missing-GHCR-images blocker described below."

requirements-completed: []  # REQ-B1 and the storage/tracking half of REQ-B3 are met; REQ-B3's cluster-pull proof is NOT met - see Deviations.

coverage:
  - id: D1
    description: "k3d cluster `mlops` runs KFP standalone 2.17.0 via the platform-agnostic overlay; every KFP image at 2.17.0; no istio-system namespace"
    requirement: "REQ-B1"
    verification:
      - kind: other
        ref: "kubectl get pods -n kubeflow (14 Running), kubectl get namespace istio-system (NotFound) - re-verified live at session start"
        status: pass
    human_judgment: false
  - id: D2
    description: "Dedicated MinIO pod + in-cluster MLflow (SQLite backend, MinIO artifact root) Ready in the mlflow namespace, reachable via in-cluster DNS, three buckets present, credentials Secret in both namespaces, no credential in git"
    requirement: "REQ-B3"
    verification:
      - kind: other
        ref: "deploy/03-storage-tracking.sh full run (task2-run4.log): pods Ready, in-cluster curl to mlflow.mlflow.svc.cluster.local:5000/health returns 2xx, both Secret copies present"
        status: pass
      - kind: other
        ref: "boto3 list_buckets() -> ['backfill', 'mlflow-artifacts', 'tlc-raw']; git ls-files + untracked-file grep for credential patterns across deploy/ -> 0 matches"
        status: pass
    human_judgment: false
  - id: D3
    description: "tlc-raw bucket pre-loaded with every locally cached TLC month under the exact filename component pods expect"
    verification:
      - kind: other
        ref: "deploy/04-upload-raw-data.sh run: 12/12 months uploaded, confirmed via boto3 list_objects_v2 count"
        status: pass
    human_judgment: false
  - id: D4
    description: "scripts/submit_pipeline.py and scripts/backfill_checksums.py exist, both refuse loudly on their guarded failure modes (placeholder image tag; missing backfill key), and the submit path is mechanically proven end to end against the live KFP API"
    verification:
      - kind: other
        ref: "submit_pipeline.py --image-tag dev exits 1 naming the placeholder; backfill_checksums.py against an empty bucket and again after deleting one previously-uploaded test key both exit 1 naming the missing key(s); a real submission (image tag = HEAD SHA) compiled and created a KFP run"
        status: pass
    human_judgment: false
  - id: D5
    description: "A submitted run's per-month branch (ingest/validate/features) succeeds for 2020-02 through 2020-04 with GHCR-pulled images, live resource limits, and an observed ParallelFor concurrency cap"
    requirement: "REQ-B5"
    verification: []
    human_judgment: true
    rationale: "BLOCKED, not merely unverified: no GHCR image has ever been published for any commit on this feature branch (CI only builds/pushes on push to master/development or a pull_request event, and this branch has never been pushed). The one real submission made during this session reached the cluster and failed with ImagePullBackOff/ErrImagePull on ghcr.io/tothehien/nyc-trip-duration-kfp/months:<HEAD-SHA>, confirming the diagnosis empirically. A human must choose how to unblock this (push the branch, publish images by another route, or accept a documented cut-line substitute) before this deliverable can be attempted again - see Deviations below."

duration: 45min
completed: 2026-08-25
status: halted
---

# Phase 3 Plan 4: Cluster Storage, Tracking, and Submit Tooling Summary

**Dedicated MinIO + in-cluster MLflow (D-12) stood up and verified on the existing k3d/KFP-standalone cluster, plus fully-tested host-side submit and checksum tooling — but the live per-month-branch proof is blocked because no GHCR image has ever been published for this feature branch.**

## Performance

- **Duration:** ~45 min (this session; Task 1 was completed and committed in a prior session)
- **Started:** 2026-08-25T01:51:00Z
- **Completed:** 2026-08-25T02:33:00Z
- **Tasks:** 3 (Task 1 already done at session start; Task 2 completed; Task 3 partially completed — tooling done, live-run proof blocked)
- **Files modified:** 7 (4 new deploy/ files, 2 new scripts/ files, 1 pyproject.toml edit)

## Accomplishments

- Verified the k3d cluster (`mlops`) and KFP standalone 2.17.0 install from the prior session are still healthy: 14 pods Running in `kubeflow`, no `istio-system` namespace.
- Diagnosed and fixed an in-progress MLflow deployment that was crash-looping on OOM at three successively larger memory limits (512Mi → 768Mi → 1536Mi), by measuring the real steady-state RSS (~2.31GiB) directly in a throwaway debug pod rather than guessing further, then sizing the limit to 3Gi with 1 worker.
- Discovered and fixed a service-name mismatch: the MLflow Helm chart's default `<release>-<chart>` naming produces a Service named `mlflow-mlflow`, which does not match `pipelines/train_pipeline.py`'s `mlflow_tracking_uri` default of `http://mlflow.mlflow.svc.cluster.local:5000`. Fixed via `fullnameOverride: "mlflow"` rather than touching pipeline code.
- Fully deployed and verified the D-12 storage/tracking topology: MinIO + MLflow pods Ready, MLflow reachable over in-cluster DNS, three buckets present, `mlflow-minio-creds` present in both `mlflow` and `kubeflow` namespaces, zero credential values in any tracked or untracked file under `deploy/`.
- Uploaded all 12 locally-cached TLC months into `tlc-raw`.
- Wrote and verified `scripts/submit_pipeline.py` and `scripts/backfill_checksums.py`, both refusing loudly on their guarded failure modes, and both mechanically proven against the live cluster (a real submission compiled and created a KFP run; the run reached the cluster and failed only at image pull, for the reason documented below).

## Task Commits

1. **Task 1: k3d cluster and KFP standalone 2.17.0** — `201b308` (feat) — completed in a prior session, verified healthy at the start of this one.
2. **Task 2: Dedicated MinIO, in-cluster MLflow, credentials, and the raw-data upload** — `7fc333e` (feat)
3. **Task 3: Submit tooling (partial — see Deviations)** — `1c412f0` (feat)

No separate plan-metadata commit; this SUMMARY plus STATE.md/ROADMAP.md/REQUIREMENTS.md updates are committed together as the plan-completion commit.

## Files Created/Modified

- `deploy/03-storage-tracking.sh` — Installs Helm, generates/reuses MinIO root credentials, creates both Secrets in both namespaces, installs MinIO and MLflow via Helm, verifies pods/reachability/Secrets.
- `deploy/minio-values.yaml` — Standalone MinIO, explicit 512Mi memory request, persistence, the three required buckets.
- `deploy/mlflow-values.yaml` — SQLite backend on a PVC, MinIO artifact root over in-cluster DNS, 1 worker, 1536Mi/3Gi resources, `fullnameOverride: "mlflow"`.
- `deploy/04-upload-raw-data.sh` — Uploads every locally cached `yellow_tripdata_*.parquet` into `tlc-raw` under its exact expected filename.
- `scripts/submit_pipeline.py` — Compiles `train_pipeline` (same `Compiler().compile(...)` call `pipelines/compile.py` makes) with `COMPONENT_IMAGE_TAG` set before any pipeline/component import, refuses the unpublished `dev` placeholder tag, submits via `kfp.Client` with `--no-cache` wired to `enable_caching=False`.
- `scripts/backfill_checksums.py` — Verifies every expected backfill key exists before downloading anything (so a missing key produces a full refusal, never a partial table), then prints month/key/byte-size/sha256 rows and an optional markdown table.
- `pyproject.toml` — Added a `scripts/backfill_checksums.py` ANN401 per-file-ignore, matching `lib/artifacts.py`'s existing untyped-boto3-client rationale.

## Decisions Made

- Reused the pre-existing MinIO root credentials (read from the live Secret) instead of letting the script regenerate new ones, so the already-Running MinIO pod's actual credentials never fell out of sync with the Secret it was re-applied from.
- Pinned MLflow's Helm release name via `fullnameOverride: "mlflow"` instead of changing `pipelines/train_pipeline.py`'s tracking-URI default — keeps the fix in deploy/ (this plan's own file scope) and matches the naming convention the MinIO release already uses.
- Sized MLflow's memory limit empirically (measured RSS + margin) rather than by trial-and-error guessing a fourth time — a debug pod running the exact same image, workers=1, and S3-artifact-root configuration showed RSS stabilize at ~2.31GiB within seconds of startup completing, which is the "-full" image's steady-state footprint under this configuration, not a leak.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MLflow OOM-killed repeatedly; root cause was the `-full` image + S3 artifact-root config, not worker count**
- **Found during:** Task 2 (re-running the interrupted `deploy/03-storage-tracking.sh`)
- **Issue:** The MLflow pod OOM-killed at 512Mi (chart default 4 workers), then again at 768Mi (2 workers), then again at 1536Mi (1 worker) — the values file already on disk from the prior interrupted session had progressively reduced workers, but the actual driver was never worker count.
- **Fix:** Measured total `/proc/*/status` VmRSS across every process in a throwaway debug pod running the exact production image, `--workers=1`, and the exact `MLFLOW_S3_ENDPOINT_URL`/AWS-credential/`default-artifact-root=s3://mlflow-artifacts/` configuration. RSS stabilized at ~2.31GiB seconds after startup completed and stayed flat for 60s of polling — a steady-state footprint of the `-full` image's preloaded extras plus the S3-artifact-root code path, not a leak. Set `resources.requests.memory: 1536Mi` / `resources.limits.memory: 3Gi`, comfortably above the measured steady state, and confirmed the host had headroom (`kubectl top pods` showed <3GiB used cluster-wide against the k3d server's 10Gi advisory budget).
- **Files modified:** `deploy/mlflow-values.yaml`
- **Verification:** `deploy/03-storage-tracking.sh` ran to completion with 0 pod restarts on the new revision; `kubectl get pod -o jsonpath` confirmed no further `OOMKilled` events.
- **Committed in:** `7fc333e`

**2. [Rule 1 - Bug] MLflow's Service name did not match the pipeline code's DNS assumption**
- **Found during:** Task 2's in-cluster reachability check (`http://mlflow.mlflow.svc.cluster.local:5000/health` connection refused/timed out)
- **Issue:** The MLflow Helm chart's default naming template composes `<release>-<chart>` = `mlflow-mlflow` for every resource, including the Service. `pipelines/train_pipeline.py`'s `mlflow_tracking_uri` parameter defaults to `http://mlflow.mlflow.svc.cluster.local:5000` (the plan's own verification block hard-codes the same address), so the deployed Service was unreachable at the address every consumer already assumed.
- **Fix:** Added `fullnameOverride: "mlflow"` to `deploy/mlflow-values.yaml`, pinning every chart-managed resource name (Service included) to `mlflow`, matching both the pipeline code's default and the MinIO release's own unprefixed naming. No pipeline code changed.
- **Files modified:** `deploy/mlflow-values.yaml`
- **Verification:** A throwaway in-cluster curl pod against `http://mlflow.mlflow.svc.cluster.local:5000/health` returned `200`; `deploy/03-storage-tracking.sh`'s own verification block passed on the next run.
- **Committed in:** `7fc333e`

**3. [Rule 1 - Bug] The acceptance criterion's negative grep for a loopback address matched the plan's own rule-explaining comment**
- **Found during:** Post-Task-2 acceptance-criteria sweep
- **Issue:** `grep -Ec 'localhost|127\.0\.0\.1' deploy/mlflow-values.yaml` returned 1, matching a comment explaining the rule ("never localhost/127.0.0.1 — Pitfall 7"), not an actual pod-resolved address.
- **Fix:** Reworded the comment to describe the rule without using the literal matched substrings ("never a loopback host address").
- **Files modified:** `deploy/mlflow-values.yaml`
- **Verification:** `grep -Ec 'localhost|127\.0\.0\.1' deploy/mlflow-values.yaml` now returns 0.
- **Committed in:** `7fc333e`

### Blocked (not auto-fixable — Task 3's live-run proof)

**No GHCR image has ever been published for any commit on `feature/phase-3-kubeflow-pipeline-core-deployment`.**

- **Root cause:** `.github/workflows/ci.yml`'s `build-push` job (and `compile-pipeline`) only trigger on `push` to `master`/`development` or on a `pull_request` event. This feature branch — which contains every plan-03-01-through-03-04 commit, including the `components/*/Dockerfile`s and the `train_pipeline.py` DAG itself — has never been pushed to `origin` (`git branch -r` shows no `feature/phase-3-...` remote branch). CI has therefore never run `build-push` for any commit that contains the pipeline code, and no image (`ghcr.io/tothehien/nyc-trip-duration-kfp/*`) exists at any tag.
- **Confirmed empirically, not assumed:**
  - `docker pull ghcr.io/tothehien/nyc-trip-duration-kfp/ingest:<HEAD-SHA>` fails with "not found" for the exact SHA under test.
  - `gh api /user/packages/container/...` and `docker pull ...:latest` / `...:dev` all confirm no package exists in the namespace at all — this is not a stale-tag problem, the package has never been created.
  - A real submission was made anyway (`scripts/submit_pipeline.py --start-month 2020-02 --end-month 2020-04 --image-tag $(git rev-parse HEAD)`): it compiled successfully and created a real KFP run (`run_id=bab41166-dca8-4a27-a177-90e711f7f870`). The run reached the cluster; its first task pod (`expand_months`, image `ghcr.io/tothehien/nyc-trip-duration-kfp/months:<HEAD-SHA>`) went to `ImagePullBackOff` then `ErrImagePull`, confirmed via `kubectl describe pod` and `kubectl get events -n kubeflow`. The run was then terminated via `kfp.Client.terminate_run` to free cluster resources.
- **Why this was not auto-fixed:** Two possible fixes exist, and neither was mine to choose unilaterally:
  1. **Push the branch to `origin`**, which would trigger CI's `build-push`/`compile-pipeline` jobs and publish real images at the current HEAD SHA. This is explicitly prohibited by this session's instructions ("do NOT push... The orchestrator owns merge/push after the full phase is verified").
  2. **Push images to GHCR directly** (bypassing git/CI), which would require a `write:packages`-scoped credential. The `gh` CLI token available in this environment has scopes `admin:public_key, gist, read:org, repo, workflow` — no `packages` scope at all (confirmed via `gh api /user/packages/...` returning 403, and no `ghcr.io` entry in `~/.docker/config.json`). I do not have a credential capable of this, and acquiring one would require an OAuth scope change I should not make unilaterally.
- **What this means for the plan:** Task 3's `scripts/submit_pipeline.py` and `scripts/backfill_checksums.py` deliverables are complete and verified (D4 above). Task 3's core proof — "a submitted run's per-month branch completes for every month in the range... with GHCR-pulled images" (REQ-B5's cap observed on live pods, and the must-have "a successful docker push is not proof a pod can pull") — is **not met** and cannot be met without one of the two actions above. This plan is marked `status: halted` rather than `complete` so `03-05` (which `depends_on: ["03-03", "03-04"]`) is correctly reported as blocked until this is resolved.
- **Recommended next step:** the orchestrator/user should either (a) push this branch (or open a PR from it) once the full phase is verified, so CI publishes real images and Task 3's live-run proof can be re-attempted, or (b) explicitly authorize a `write:packages` credential for a direct GHCR push, or (c) explicitly accept a documented cut-line substitute (e.g., `k3d image import` of a locally-built image) with the understanding that it does **not** prove GHCR-pull and the corresponding must-have stays unmet until a real CI-published image is later pulled.

---

**Total deviations:** 4 (3 auto-fixed under Rule 1; 1 blocked pending a human decision, documented above rather than worked around)
**Impact on plan:** The 3 auto-fixed issues were all correctness bugs in the in-progress Task 2 work and are fully resolved and verified live. The blocked item is structural (no image has ever been published for this branch) and outside what an executor can resolve without either violating the "do not push" instruction or acquiring a registry credential it doesn't have.

## Issues Encountered

Covered in Deviations above — the MLflow OOM/service-name issues were resolved during Task 2; the GHCR-image-publish gap surfaced during Task 3 and remains open.

## User Setup Required

None — no external service configuration required for the work done in this session. The GHCR-publish blocker (above) requires a workflow/permissions decision from the user or orchestrator, not a one-time setup step.

## Next Phase Readiness

- **Ready:** The cluster, storage/tracking topology, and both host-side scripts are in place and verified. Once GHCR images exist for a commit on this branch, `scripts/submit_pipeline.py --start-month 2020-02 --end-month 2020-04 --image-tag <that-SHA>` is the exact command to re-attempt Task 3's live-run proof, and `scripts/backfill_checksums.py` is ready to verify the resulting `backfill` bucket contents.
- **Blocked:** 03-05 depends on this plan; its own real-run-based proofs (REQ-B8's byte-identity comparison, REQ-B5's concurrency-cap observation on a full run, etc.) inherit this same GHCR-image blocker and cannot proceed until it is resolved.
- **Resource note:** current cluster memory usage across all pods is under 3GiB against the k3d server's 10Gi advisory budget; the MLflow limit change (3Gi) leaves comfortable headroom on this 16GB host as long as no other large workload runs concurrently with a real pipeline submission.

---
*Phase: 03-kubeflow-pipeline-core-deployment*
*Completed: 2026-08-25*

## Self-Check: PASSED

All 6 created files verified present on disk; all 3 referenced commits (`201b308`, `7fc333e`, `1c412f0`) verified present in git log.
