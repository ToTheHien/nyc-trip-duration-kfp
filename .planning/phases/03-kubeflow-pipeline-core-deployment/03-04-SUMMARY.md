---
phase: 03-kubeflow-pipeline-core-deployment
plan: 04
subsystem: infra
tags: [k3d, kubeflow-pipelines, minio, mlflow, helm, kfp-client, boto3, github-actions, memory-tuning]

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
  - "The branch pushed to origin, PR #10 open against development, CI publishing real GHCR images at every pushed SHA"
  - "A memory-hygiene fix in lib/artifacts.py's adapter functions and re-tuned per-task resource limits in pipelines/train_pipeline.py, both empirically measured against real cluster data"
  - "PARALLELISM cut from 2 to 1 (documented deviation from REQ-B5's literal '2-3 concurrent' text)"
  - "The full per-month branch (ingest->validate->features->merge) proven end-to-end on the live cluster with GHCR-pulled images, against a truncated/synthetic month - see Known Gap below for what this does and does not establish"
affects: ["03-05"]

# Actuals (#2632)
actuals:
  tokens: 16700
  tasks: 3
  commits: 7

tech-stack:
  added: ["k3d v5.9.0", "helm v3.21.4", "MinIO Helm chart 5.4.0", "MLflow OCI Helm chart 0.1.0 (mlflow v3.14.0-full image)"]
  patterns:
    - "Credentials generated/read from env, passed to Helm only via existingSecret reference, never --set or stdout"
    - "fullnameOverride pinning a chart's release-composite resource name to match code-side DNS assumptions"
    - "Empirical /proc/*/status VmRSS sampling in a throwaway debug pod to size a container memory limit instead of guessing"
    - "gc.collect() + ctypes malloc_trim(0) between adapter-function pipeline stages to actually return freed pandas/pyarrow memory to the OS"
    - "A row-truncated real-data parquet (not hand-authored fixture data) as a synthetic month, to prove a live-cluster mechanism without the memory footprint of a full real month"

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
    - lib/artifacts.py
    - pipelines/train_pipeline.py
    - components/features/Dockerfile

key-decisions:
  - "Reused the previously-generated MinIO root credentials (read from the existing Secret) rather than regenerating, so the already-Running MinIO pod's live credentials stayed in sync with the Secret."
  - "Set deploy/mlflow-values.yaml's fullnameOverride to \"mlflow\" so the chart's Service name matches pipelines/train_pipeline.py's mlflow_tracking_uri default (http://mlflow.mlflow.svc.cluster.local:5000), instead of the chart's default \"mlflow-mlflow\" composite name."
  - "Sized MLflow's memory limit to 3Gi (request 1536Mi) from an empirically measured ~2.31GiB steady-state RSS, not from guessing worker counts down."
  - "Pushed the feature branch to origin and opened PR #10 against development (explicit user instruction, overriding this session's original 'do not push' constraint), specifically to trigger CI's build-push job and unblock the GHCR-image precondition - not a merge, not a force-push."
  - "Added lib/artifacts.py's _release_memory() (gc.collect() + malloc_trim) after every del of a superseded DataFrame in ingest_month_to_parquet/validate_parquet/build_features_parquet - measured to cut a real month's peak ingest RSS from an unbounded/still-climbing >6.3GiB to a stable, completing ~5.4GiB."
  - "Cut PARALLELISM from 2 to 1 in pipelines/train_pipeline.py - a documented deviation from REQ-B5's literal '2-3 concurrent' text, made after measuring that 2 concurrent branches risk the k3d node's real, enforced 10Gi cgroup budget (confirmed via dmesg CONSTRAINT_MEMCG events, not merely advisory as 01-cluster-up.sh's comment assumed)."
  - "Bumped ingest/validate to 1Gi/6Gi and features specifically to 1Gi/7Gi (features does strictly more work on the same row count and measurably needed more)."
  - "Fixed components/features/Dockerfile to COPY data/zone_centroids.csv into the image - a 100%-reproducible bug (not data-dependent) that had never been exercised before this session's first real in-cluster submission."
  - "When the real-scale run (2020-02, 6.3M rows) still risked host-wide OOM even after the above fixes (host desktop memory pressure, not just cgroup limits), switched to a row-truncated (20,000-row) real-data parquet as a synthetic month to prove the mechanism without the memory risk - documented as a narrower proof than the plan's original full-real-data acceptance criterion, not silently treated as equivalent."

requirements-completed: [REQ-B1]  # REQ-B3's cluster-pull proof for a full real-scale run, and REQ-B5's literal "2-3 concurrent" wording, remain open - see Known Gap and the PARALLELISM deviation above.

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
        ref: "deploy/03-storage-tracking.sh full run: pods Ready, in-cluster curl to mlflow.mlflow.svc.cluster.local:5000/health returns 2xx, both Secret copies present"
        status: pass
      - kind: other
        ref: "boto3 list_buckets() -> ['backfill', 'mlflow-artifacts', 'tlc-raw']; credential-pattern grep across all deploy/ files (tracked and untracked) -> 0 matches"
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
        ref: "submit_pipeline.py --image-tag dev exits 1 naming the placeholder; backfill_checksums.py against an empty bucket and again after deleting a previously-uploaded test key both exit 1 naming the missing key(s); multiple real submissions compiled and created live KFP runs"
        status: pass
    human_judgment: false
  - id: D5
    description: "GHCR images are published for real commits on this branch, and a live-cluster submission successfully pulls them (not merely a docker push, an actual in-cluster pull)"
    requirement: "REQ-B3"
    verification:
      - kind: other
        ref: "Branch pushed, PR #10 opened (github.com/ToTheHien/nyc-trip-duration-kfp/pull/10), CI runs 32805757046/32807948119/32809421695 all green with build-push publishing every component image; docker pull and live in-cluster ImagePullBackOff/Pulled events confirmed at three successive SHAs (44dbb21, 15d8bca->721ea78->2d6af29)"
        status: pass
    human_judgment: false
  - id: D6
    description: "The full per-month branch (ingest->validate->features->merge) succeeds end-to-end on the live cluster with GHCR-pulled images, live resource limits, and an observed ParallelFor concurrency cap of 1"
    requirement: "REQ-B5"
    verification:
      - kind: other
        ref: "Run 8bc27a6d against a truncated (20,000-row) synthetic month '2021-01': months/ingest/validate/features/merge all Completed; features pod's live resources block showed limits.memory=7Gi; at most one container-impl pod Running/PodInitializing at any polled instant across ~4 minutes of monitoring; train failed on a correctly-raised chronological_split ValueError (data-scope limitation of the truncated month, not a bug) and the ExitHandler notify task correctly logged run_status=FAILED"
        status: pass
    human_judgment: true
    rationale: "Passes for the per-month branch MECHANISM (task wiring, image pull, resource limits, parallelism cap, Secret injection) on synthetic/truncated data. Does NOT establish the same mechanism succeeds at real full-month scale (6.3M rows) - see Known Gap below. A human should confirm this distinction is an acceptable basis to unblock 03-05's own real-data run, or require the real-scale attempt first."

duration: ~4.5h (across three response cycles, including two host-memory investigations)
completed: 2026-08-25
status: halted
---

# Phase 3 Plan 4: Cluster Storage, Tracking, and Submit Tooling Summary

**Dedicated MinIO + in-cluster MLflow (D-12) stood up; the GHCR-image-publish blocker resolved by pushing the branch and opening PR #10; three real bugs found and fixed via live-cluster testing (MLflow memory/naming, adapter-function memory hygiene, a missing Dockerfile COPY); and the full per-month branch mechanism proven end-to-end with GHCR-pulled images against a truncated synthetic month — but the plan's original acceptance criterion of a full real-data run (2020-02 through 2020-04) remains unverified, blocked by host memory pressure outside the cluster's control.**

## Performance

- **Duration:** ~4.5h total across this session (Task 1 completed in a prior session)
- **Tasks:** 3 (Task 1 done at session start; Task 2 complete; Task 3's tooling complete and its per-month-branch mechanism proven, but its literal full-real-data acceptance criterion remains open)
- **Files modified:** 11 (4 new deploy/ files, 2 new scripts/ files, pyproject.toml, lib/artifacts.py, pipelines/train_pipeline.py, components/features/Dockerfile)
- **Commits:** 7 (see Task Commits below)

## Accomplishments

- Verified the k3d cluster (`mlops`) and KFP standalone 2.17.0 install from the prior session were still healthy at session start.
- Diagnosed and fixed an in-progress MLflow deployment crash-looping on OOM, by measuring real steady-state RSS in a throwaway debug pod (~2.31GiB) rather than guessing further; fixed a Service-naming mismatch (`fullnameOverride`) that broke in-cluster reachability; fixed the acceptance criterion's own overly-literal negative grep.
- Fully deployed and verified the D-12 storage/tracking topology; uploaded all 12 locally-cached TLC months into `tlc-raw`.
- Wrote and verified `scripts/submit_pipeline.py` and `scripts/backfill_checksums.py` against the live cluster, including their guarded-refusal behaviors.
- **Resolved the GHCR-image-publish blocker**: at the user's explicit instruction (overriding this session's original "do not push" constraint), pushed the feature branch to `origin` and opened PR #10 (`github.com/ToTheHien/nyc-trip-duration-kfp/pull/10`) against `development`. CI's `pull_request` trigger published real GHCR images for the first time on this branch.
- **Found and fixed a real, severe memory bug** discovered only by running the actual pipeline against real data on the live cluster (never previously exercised, since no prior plan had run the compiled DAG in-cluster): `ingest`/`validate`/`features` all OOM-killed at their original 1536Mi limit against a real 6.3M-row TLC month. Root-caused via `/proc/*/status` VmRSS sampling and `dmesg` cgroup-OOM events (not host pressure - confirmed `CONSTRAINT_MEMCG`) to genuinely large, non-leaking pandas/pyarrow memory use, not a fixable-by-guessing config error. Fixed with an eager memory-release pattern in `lib/artifacts.py` and re-tuned resource limits.
- **Found and fixed a second real bug**: `components/features/Dockerfile` never copied `data/zone_centroids.csv` into the image, so the `features` component's `FileNotFoundError` was 100% reproducible in-cluster and had simply never been exercised by any prior compile-only or unit-test check.
- **Made and documented a real architectural deviation**: cut `PARALLELISM` from 2 to 1, because 2 concurrent branches risk the k3d node's own real, enforced memory cgroup (confirmed via `dmesg`, contradicting `01-cluster-up.sh`'s "advisory, not enforced" assumption) - a measured crash risk, not theoretical. This is a documented deviation from REQ-B5's literal "2-3 concurrent" wording; not silently reinterpreted (see Deviations below and the WINDOWS.md/STATE.md entries).
- **Proved the full per-month branch mechanism end-to-end** (`ingest`→`validate`→`features`→`merge`) on the live cluster with GHCR-pulled images, live 7Gi resource limits confirmed on the running pod, `PARALLELISM=1` concurrency observed throughout, Secret injection working, and the `ExitHandler`'s failure path correctly triggered and logged - against a **truncated/synthetic** 20,000-row month, after real host-memory constraints made repeated full-real-scale attempts unsafe (two host-wide, not just per-pod, OOM events already occurred during investigation).
- **Also retained as supporting evidence**: earlier in the session, `ingest` and `validate` (not `features`, which came later in the fix sequence) succeeded end-to-end against the REAL, full-scale 2020-02 month (6.3M rows) after the memory fix, before the run was intentionally stopped once `features`'s (then-unfixed) Dockerfile bug surfaced. This is real signal that the memory fix works at real scale for at least two of the three per-month stages - not merely synthetic-data-only success.

## Task Commits

1. **Task 1: k3d cluster and KFP standalone 2.17.0** — `201b308` (feat) — completed in a prior session, verified healthy at the start of this one.
2. **Task 2: Dedicated MinIO, in-cluster MLflow, credentials, and the raw-data upload** — `7fc333e` (feat)
3. **Task 3: Submit tooling** — `1c412f0` (feat)
4. **Plan-completion docs (pre-push state)** — `44dbb21` (docs) — superseded by this rewrite; kept in history as an honest record of the mid-session halt.
5. **Memory-release fix + PARALLELISM cut** — `15d8bca` (fix)
6. **zone_centroids.csv Dockerfile fix** — `721ea78` (fix)
7. **features memory limit bump to 7Gi** — `2d6af29` (fix)

This SUMMARY plus STATE.md/ROADMAP.md updates are committed together as the final plan-completion commit.

## Files Created/Modified

- `deploy/03-storage-tracking.sh` — Installs Helm, generates/reuses MinIO root credentials, creates both Secrets in both namespaces, installs MinIO and MLflow via Helm, verifies pods/reachability/Secrets.
- `deploy/minio-values.yaml` — Standalone MinIO, explicit 512Mi memory request, persistence, the three required buckets.
- `deploy/mlflow-values.yaml` — SQLite backend on a PVC, MinIO artifact root over in-cluster DNS, 1 worker, 1536Mi/3Gi resources, `fullnameOverride: "mlflow"`.
- `deploy/04-upload-raw-data.sh` — Uploads every locally cached `yellow_tripdata_*.parquet` into `tlc-raw` under its exact expected filename.
- `scripts/submit_pipeline.py` — Compiles `train_pipeline` (same `Compiler().compile(...)` call `pipelines/compile.py` makes) with `COMPONENT_IMAGE_TAG` set before any pipeline/component import, refuses the unpublished `dev` placeholder tag, submits via `kfp.Client` with `--no-cache` wired to `enable_caching=False`.
- `scripts/backfill_checksums.py` — Verifies every expected backfill key exists before downloading anything, then prints month/key/byte-size/sha256 rows and an optional markdown table.
- `pyproject.toml` — Added a `scripts/backfill_checksums.py` ANN401 per-file-ignore, matching `lib/artifacts.py`'s existing untyped-boto3-client rationale.
- `lib/artifacts.py` — Added `_release_memory()` (gc.collect + malloc_trim), called after every `del` of a superseded DataFrame in `ingest_month_to_parquet`, `validate_parquet`, `build_features_parquet`.
- `pipelines/train_pipeline.py` — `PARALLELISM` 2→1; `ingest`/`validate` memory 512Mi/1536Mi→1Gi/6Gi; `features` memory →1Gi/7Gi.
- `components/features/Dockerfile` — Added `COPY data/zone_centroids.csv /app/data/zone_centroids.csv`.

## Decisions Made

See `key-decisions` in the frontmatter above for the full list with rationale; the two most consequential:

- **Pushed the branch and opened a PR** at the user's explicit, direct instruction mid-session, which is treated as overriding the orchestrator's original "do not push" constraint per this executor's own protocol (a message from the user, not from a launching agent, is valid consent for actions the launching agent had restricted). This was the only way to satisfy Task 3's GHCR-image precondition without a registry credential this session never had.
- **Cut PARALLELISM from 2 to 1** rather than raise memory limits further and keep 2 concurrent branches. Given the coordinator's explicit direction and the measured evidence (a real month peaks at ~5.4GiB RSS through ingest alone; the k3d node's memory cap is really enforced), staying within the physical constraint was judged to take priority over REQ-B5's literal "2-3 concurrent" wording. This is flagged as needing a REQUIREMENTS.md wording update, not silently absorbed.

## Deviations from Plan

### Auto-fixed Issues (Rule 1 - bugs)

**1. MLflow OOM-killed repeatedly; root cause was the `-full` image + S3 artifact-root config, not worker count**
- **Found during:** Task 2 (re-running the interrupted `deploy/03-storage-tracking.sh`)
- **Fix:** Measured real steady-state RSS (~2.31GiB) in a debug pod; set `resources.requests.memory: 1536Mi` / `resources.limits.memory: 3Gi`.
- **Files:** `deploy/mlflow-values.yaml` — **Committed in:** `7fc333e`

**2. MLflow's Service name did not match the pipeline code's DNS assumption**
- **Found during:** Task 2's in-cluster reachability check
- **Fix:** `fullnameOverride: "mlflow"` in `deploy/mlflow-values.yaml`, pinning the Service name to what `pipelines/train_pipeline.py` already assumed. No pipeline code changed.
- **Files:** `deploy/mlflow-values.yaml` — **Committed in:** `7fc333e`

**3. The acceptance criterion's negative grep for a loopback address matched the plan's own rule-explaining comment**
- **Found during:** Post-Task-2 acceptance-criteria sweep
- **Fix:** Reworded the comment to avoid the literal matched substrings.
- **Files:** `deploy/mlflow-values.yaml` — **Committed in:** `7fc333e`

**4. `ingest`/`validate`/`features` OOM-killed against real cluster data at their original 1536Mi limit**
- **Found during:** Task 3's first real submission (after the GHCR blocker was resolved)
- **Issue:** Real 2020-02 data (6.3M rows) drove genuine, non-leaking pandas/pyarrow memory use far past the original limit - confirmed via `dmesg` `Memory cgroup out of memory ... CONSTRAINT_MEMCG` events at every limit tried up to 6Gi for `features`, and via `/proc/*/status` VmRSS sampling in isolated debug pods showing real (not fragmentation-driven) growth.
- **Fix:** Added `lib/artifacts.py`'s `_release_memory()` pattern (cut ingest's peak from unbounded/still-climbing >6.3GiB to a stable, completing ~5.4GiB); bumped `ingest`/`validate` to 1Gi/6Gi and `features` to 1Gi/7Gi; cut `PARALLELISM` to 1 (see Decisions above).
- **Files:** `lib/artifacts.py`, `pipelines/train_pipeline.py` — **Committed in:** `15d8bca`, `2d6af29`

**5. `components/features/Dockerfile` never copied `data/zone_centroids.csv` into the image**
- **Found during:** Task 3's first submission to reach the `features` stage
- **Issue:** `lib.features.ZONE_CENTROID_PATH` resolves relative to the repo layout; every earlier check (compile, unit tests, local `qa.sh`) ran against the host checkout where the file is simply present, so this 100%-reproducible bug had never been exercised before a real in-cluster run.
- **Fix:** Added `COPY data/zone_centroids.csv /app/data/zone_centroids.csv`. Verified only `features` needs it (grepped every other component for the relevant lib calls) and confirmed with a local `docker build` + `docker run ... load_zone_centroids()` (263 rows).
- **Files:** `components/features/Dockerfile` — **Committed in:** `721ea78`

### Explicit deviation requiring a follow-up (not a bug - a resource-budget tradeoff)

**6. PARALLELISM cut from 2 to 1, deviating from REQ-B5's literal "2-3 concurrent" wording**
- REQ-B5 as written: "`dsl.ParallelFor` fan-out over months, parallelism capped for 16GB RAM (2-3 concurrent)." That figure was never validated against real per-month memory cost before this session.
- Empirical measurement (this session): a single real TLC month peaks at ~5.4GiB RSS through `ingest` alone after the memory-release fix. Running 2 concurrent branches (2020-02 paired with 2020-03, the two largest months in the 3-month proof range) risks ~8GiB of task-pod memory on top of ~3GiB of baseline cluster infra, against the k3d node's real, enforced 10Gi cgroup budget.
- **Action taken:** `PARALLELISM = 1`, at the coordinator's explicit direction, prioritizing physical correctness over the literal requirement text.
- **Follow-up needed:** `REQUIREMENTS.md`'s REQ-B5 row text should be updated to reflect the validated cap (or the memory footprint reduced further in a later plan to restore 2-3x concurrency safely). Not silently reinterpreted here - flagged in `WINDOWS.md` and `STATE.md`.

### Known Gap: full-scale real-data run remains unverified

**What was proven:** the full per-month branch mechanism (`ingest`→`validate`→`features`→`merge`) succeeds end-to-end on the live cluster - real GHCR-pulled images, live 7Gi resource limits confirmed on a running pod, `PARALLELISM=1` concurrency observed throughout (never more than one `container-impl` pod Running/PodInitializing across ~4 minutes of continuous polling), Secret injection into task pods working, and the `ExitHandler`'s failure path correctly triggered when `train` raised a clean, expected `chronological_split` `ValueError` (the truncated month's timestamps don't straddle the `SPLIT_TIMESTAMP` boundary - a data-scope artifact of the truncation, not a pipeline bug).

**What this does NOT prove:** that the same mechanism succeeds at real full-month scale (the largest real month, 2020-02, has 6.3M rows vs. the truncated proof's 20,000). Two real full-scale attempts were made and both surfaced real, fixed bugs (Deviations 4 and 5 above); a third full-scale attempt (after both fixes) was not completed because:

1. The host itself (not just the k3d node's cgroup) was under genuine memory pressure from concurrent desktop applications (Chrome, VSCodium, Obsidian, and locally-running MinIO/MLflow/MySQL processes outside the cluster) outside this session's control.
2. Two debug-pod memory-measurement attempts at that point triggered **host-wide** (not per-pod-cgroup) OOM kills - confirmed via `dmesg` showing plain `Out of memory: Killed process` events without the `Memory cgroup`/`CONSTRAINT_MEMCG` prefix that scoped every other OOM event in this session to a single pod. A host-wide OOM kills processes indiscriminately across the whole machine, which could have affected the user's unrelated work.
3. Rather than risk a third such event, the coordinator directed a switch to a row-truncated (20,000-row) real-data parquet as a synthetic month, explicitly to prove the mechanism without the real month's memory footprint - and explicitly NOT to be silently treated as equivalent to the full-scale proof.

**Evidence in favor of the fix generalizing to full scale:** earlier in the session, `ingest` and `validate` (before `features`'s Dockerfile bug was found and fixed) both succeeded end-to-end against the REAL, full-scale 2020-02 month after the memory-release fix and the 6Gi limit bump - not merely at truncated scale. This is real, if partial, signal.

**Recorded as an open item** in `.planning/WINDOWS.md` (kind: `unmet-truth`) and in `STATE.md`'s Blockers/Concerns, so it stays visible rather than disappearing once this SUMMARY scrolls out of context. **03-05 depends on this plan** and its own Run A/B/C/D sequence (README's `## Pipeline Run Evidence`, REQ-B4/B7/B8/B9) explicitly requires a full real-data run over 2020-02 through 2020-04 reaching `register` - the truncated proof in this plan does not substitute for that. The recommended next step is to re-attempt the full real-data run in a session with more host headroom (e.g., desktop apps closed, or on a machine with more free RAM), reusing the exact same fixes and commands recorded here (`scripts/submit_pipeline.py --start-month 2020-02 --end-month 2020-04 --image-tag <SHA>`).

---

**Total deviations:** 6 (5 auto-fixed bugs under Rule 1; 1 explicit resource-budget tradeoff requiring a REQUIREMENTS.md follow-up) plus 1 documented scope gap (full-scale real-data run deferred).
**Impact on plan:** All auto-fixed issues were real, reproducible bugs found only by actually running the pipeline in-cluster for the first time this milestone - each is now fixed and verified. The PARALLELISM cut is a deliberate, disclosed tradeoff, not a silent one. The full-scale-run gap is a genuine open item, not a failure to execute the plan competently - it reflects a physical constraint (host memory shared with the user's desktop session) that code changes alone cannot resolve.

## Issues Encountered

Covered in Deviations above. In addition: GHCR image pulls were intermittently slow/flaky during the truncated-data proof run (`dial tcp: lookup ghcr.io: Try again`, `connection timed out`), consistent with transient DNS/network conditions rather than a registry or credential problem - every pull eventually succeeded on kubelet's automatic retry (`BackOff`/`Pulling` cycle), so no code change was needed.

## User Setup Required

None - no external service configuration required. The full-scale-run gap (above) needs more host memory headroom, not a one-time setup step; closing it is a follow-up execution task, not a configuration change.

## Next Phase Readiness

- **Ready:** The cluster, storage/tracking topology, both host-side scripts, the memory-hygiene fix, the corrected `features` Dockerfile, and the re-tuned resource limits are all in place, committed, pushed, and CI-green. The per-month branch mechanism is proven end-to-end on the live cluster with real GHCR images.
- **Blocked:** 03-05 (`depends_on: ["03-03", "03-04"]`) needs a full real-data run (2020-02 through 2020-04) reaching `register` for its own REQ-B4/B7/B8/B9 proofs - that run has not yet been completed at full scale (Known Gap above). This plan is marked `status: halted` rather than `complete` for exactly this reason.
- **Follow-up required in REQUIREMENTS.md:** REQ-B5's "2-3 concurrent" wording needs updating to reflect the validated `PARALLELISM=1` cap (or a later plan needs to reduce the per-task memory footprint further to safely restore 2-3x concurrency).
- **Documentation correction flagged, not yet made:** `deploy/01-cluster-up.sh`'s comment and `.planning/research/PITFALLS.md`'s Pitfall 1 both describe k3d's `--memory` flag as "advisory... not an enforced cgroup limit." This session's `dmesg` evidence (`Memory cgroup out of memory ... CONSTRAINT_MEMCG` events at the pod level, consistently reproducible) shows the flag DOES translate into a real, enforced Docker container cgroup limit on this Linux host - the pods that get killed are just not always the ones a user expects. Recorded in `WINDOWS.md`; not fixed in this plan per the coordinator's explicit "don't block on it" instruction.
- **Resource note:** the k3d node's own cgroup budget (10Gi) has more headroom than the HOST's real physical memory once desktop applications are running concurrently - the binding constraint for a full-scale run on this particular machine, in this particular session, was host RAM shared with an active desktop session, not the cluster's own configuration.

---
*Phase: 03-kubeflow-pipeline-core-deployment*
*Completed: 2026-08-25*

## Self-Check: PASSED

All 9 referenced files verified present on disk (`deploy/03-storage-tracking.sh`, `deploy/04-upload-raw-data.sh`, `deploy/minio-values.yaml`, `deploy/mlflow-values.yaml`, `scripts/submit_pipeline.py`, `scripts/backfill_checksums.py`, `lib/artifacts.py`, `pipelines/train_pipeline.py`, `components/features/Dockerfile`). All 7 referenced commits (`201b308`, `7fc333e`, `1c412f0`, `44dbb21`, `15d8bca`, `721ea78`, `2d6af29`) verified present in git log. PR #10 (`github.com/ToTheHien/nyc-trip-duration-kfp/pull/10`) confirmed open with 3 successful CI runs (32805757046, 32807948119, 32809421695).
