"""The KFP DAG definition and the compile-time parallelism cap."""

from kfp import dsl
from kfp.dsl import PipelineTask

from components.ingest.component import ingest

# dsl.ParallelFor's `parallelism` argument resolves at compile time and
# therefore cannot be a pipeline parameter - ARCHITECTURE.md Pattern 3's
# snippet shows it as one, but that part of the snippet does not compile as
# written. PARALLELISM stays a literal module constant; plan 03-02 wires it
# into the real ParallelFor fan-out this single-task pipeline stands in for.
PARALLELISM = 2


def _harden(task: PipelineTask, memory_request: str, memory_limit: str) -> PipelineTask:
    """Apply the shared caching + resource-limit hardening every task needs.

    Factored out because plan 03-02 applies this to eight more tasks.
    """
    task.set_caching_options(enable_caching=True)
    task.set_memory_request(memory_request)
    task.set_memory_limit(memory_limit)
    task.set_cpu_request("250m")
    task.set_cpu_limit("1")
    return task


@dsl.pipeline(name="nyc-trip-duration-training")
def train_pipeline(
    month: str = "2019-07",
    s3_endpoint_url: str = "http://minio.mlflow.svc.cluster.local:9000",
) -> None:
    """The training DAG - a single hardened ingest task for this plan.

    plan 03-02 replaces this single-task body with the full
    ingest -> validate -> features -> ParallelFor -> Collected -> merge ->
    train -> evaluate -> If -> register DAG wrapped in an ExitHandler; the
    s3_endpoint_url parameter name and _harden survive that replacement.
    """
    ingest_task = ingest(month=month, s3_endpoint_url=s3_endpoint_url)
    _harden(ingest_task, "512Mi", "1536Mi")
