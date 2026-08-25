"""The notify KFP component: the ExitHandler exit task (D-11).

A single structured log line - no artifact file, no webhook, no MLflow
query. The score computed by the evaluate stage is deliberately absent:
that stage runs inside the ExitHandler's own scope, so its output provably
cannot be threaded into this exit task (03-RESEARCH.md Pitfall 11 /
kubeflow/pipelines#10187) - do not "fix" this by wiring an evaluate output
in.
"""

from kfp import dsl
from kfp.dsl import PipelineTaskFinalStatus

from components import image_for


@dsl.component(base_image=image_for("notify"))
def notify(status: PipelineTaskFinalStatus) -> None:
    print(
        f"run_status={status.state} "
        f"run_id={status.pipeline_job_resource_name} "
        f"failed_task={status.pipeline_task_name or ''} "
        f"error_code={status.error_code or ''} "
        f"error_message={status.error_message or ''}"
    )
