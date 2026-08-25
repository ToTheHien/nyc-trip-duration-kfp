---
schema_version: 1
open_count: 3
waived_count: 0
fixed_count: 1
total_count: 4
last_updated: 2026-08-25T06:58:54.205Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 03 | unmet-truth | scripts/submit_pipeline.py |  | Task 3's live per-month-branch proof (REQ-B5/B3) is blocked: no GHCR image has ever been published for any commit on feature/phase-3-kubeflow-pipeline-core-deployment (branch never pushed, CI never ran build-push). See 03-04-SUMMARY.md Deviations. | fixed |  | 2026-08-25T02:35:26.755Z | 2026-08-25T06:58:41.579Z |
| 2 | 03 | unmet-truth | pipelines/train_pipeline.py |  | 03-04's full-real-data run (2020-02 through 2020-04, the exact range 03-05 needs for REQ-B4/B7/B8/B9) is unverified end-to-end: ingest/validate succeeded at real 6.3M-row scale after the memory fix, but the full DAG through register was only proven against a truncated 20,000-row synthetic month due to host memory pressure (two host-wide OOM events during investigation). See 03-04-SUMMARY.md Known Gap. | open |  | 2026-08-25T06:58:54.020Z |  |
| 3 | 03 | deviation | .planning/REQUIREMENTS.md |  | REQ-B5's text ('parallelism capped for 16GB RAM, 2-3 concurrent') needs updating: 03-04 measured a real month peaking at ~5.4GiB RSS through ingest alone and cut PARALLELISM to 1 for physical correctness on this host. REQUIREMENTS.md still states 2-3 concurrent as the target; either update the wording or reduce per-task memory further in a later plan to restore it safely. | open |  | 2026-08-25T06:58:54.110Z |  |
| 4 | 03 | deviation | deploy/01-cluster-up.sh |  | 01-cluster-up.sh's comment and PITFALLS.md Pitfall 1 both claim k3d's --memory flag is advisory, not an enforced cgroup limit. 03-04 measured the opposite empirically via dmesg (Memory cgroup out of memory ... CONSTRAINT_MEMCG events at the pod level, reproducible across multiple OOM kills this session) - the flag does translate to a real Docker container cgroup limit on this Linux host. Documentation correction needed in both files; not made in 03-04 per explicit instruction not to block on it. | open |  | 2026-08-25T06:58:54.205Z |  |

````json
[
  {
    "id": 1,
    "kind": "unmet-truth",
    "phase": "03",
    "file": "scripts/submit_pipeline.py",
    "line": null,
    "description": "Task 3's live per-month-branch proof (REQ-B5/B3) is blocked: no GHCR image has ever been published for any commit on feature/phase-3-kubeflow-pipeline-core-deployment (branch never pushed, CI never ran build-push). See 03-04-SUMMARY.md Deviations.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-25T02:35:26.755Z",
    "resolved_at": "2026-08-25T06:58:41.579Z"
  },
  {
    "id": 2,
    "kind": "unmet-truth",
    "phase": "03",
    "file": "pipelines/train_pipeline.py",
    "line": null,
    "description": "03-04's full-real-data run (2020-02 through 2020-04, the exact range 03-05 needs for REQ-B4/B7/B8/B9) is unverified end-to-end: ingest/validate succeeded at real 6.3M-row scale after the memory fix, but the full DAG through register was only proven against a truncated 20,000-row synthetic month due to host memory pressure (two host-wide OOM events during investigation). See 03-04-SUMMARY.md Known Gap.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-25T06:58:54.020Z",
    "resolved_at": null
  },
  {
    "id": 3,
    "kind": "deviation",
    "phase": "03",
    "file": ".planning/REQUIREMENTS.md",
    "line": null,
    "description": "REQ-B5's text ('parallelism capped for 16GB RAM, 2-3 concurrent') needs updating: 03-04 measured a real month peaking at ~5.4GiB RSS through ingest alone and cut PARALLELISM to 1 for physical correctness on this host. REQUIREMENTS.md still states 2-3 concurrent as the target; either update the wording or reduce per-task memory further in a later plan to restore it safely.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-25T06:58:54.110Z",
    "resolved_at": null
  },
  {
    "id": 4,
    "kind": "deviation",
    "phase": "03",
    "file": "deploy/01-cluster-up.sh",
    "line": null,
    "description": "01-cluster-up.sh's comment and PITFALLS.md Pitfall 1 both claim k3d's --memory flag is advisory, not an enforced cgroup limit. 03-04 measured the opposite empirically via dmesg (Memory cgroup out of memory ... CONSTRAINT_MEMCG events at the pod level, reproducible across multiple OOM kills this session) - the flag does translate to a real Docker container cgroup limit on this Linux host. Documentation correction needed in both files; not made in 03-04 per explicit instruction not to block on it.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-25T06:58:54.205Z",
    "resolved_at": null
  }
]
````
