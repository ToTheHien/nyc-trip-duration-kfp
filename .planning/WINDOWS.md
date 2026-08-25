---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-08-25T02:35:26.755Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 03 | unmet-truth | scripts/submit_pipeline.py |  | Task 3's live per-month-branch proof (REQ-B5/B3) is blocked: no GHCR image has ever been published for any commit on feature/phase-3-kubeflow-pipeline-core-deployment (branch never pushed, CI never ran build-push). See 03-04-SUMMARY.md Deviations. | open |  | 2026-08-25T02:35:26.755Z |  |

````json
[
  {
    "id": 1,
    "kind": "unmet-truth",
    "phase": "03",
    "file": "scripts/submit_pipeline.py",
    "line": null,
    "description": "Task 3's live per-month-branch proof (REQ-B5/B3) is blocked: no GHCR image has ever been published for any commit on feature/phase-3-kubeflow-pipeline-core-deployment (branch never pushed, CI never ran build-push). See 03-04-SUMMARY.md Deviations.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-25T02:35:26.755Z",
    "resolved_at": null
  }
]
````
