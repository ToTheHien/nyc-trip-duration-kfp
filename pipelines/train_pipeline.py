"""The KFP DAG definition and the compile-time parallelism cap."""

from kfp import dsl, kubernetes
from kfp.dsl import PipelineTask

from components.evaluate.component import evaluate
from components.features.component import build_features_component
from components.ingest.component import ingest
from components.merge.component import merge_features
from components.months.component import expand_months
from components.notify.component import notify
from components.register.component import register
from components.train.component import train
from components.validate.component import validate

# dsl.ParallelFor's `parallelism` argument resolves at compile time and
# therefore cannot be a pipeline parameter - ARCHITECTURE.md Pattern 3's
# snippet shows it as one, but that part of the snippet does not compile as
# written (confirmed in plan 03-01). PARALLELISM stays a literal module
# constant.
#
# REQ-B5 as originally written calls for "2-3 concurrent" as the cap for a
# 16GB laptop, but that figure was never validated against real per-month
# memory cost. Plan 03-04 Task 3 measured it directly in-cluster: a single
# real TLC month (2020-02, 6.3M rows) peaks at ~5.4GiB RSS through the
# ingest stage alone (after the lib/artifacts.py memory-release fix below -
# without it, RSS was still climbing past 6.3GiB and unfinished). The k3d
# node's own `--memory` flag is a REAL enforced cgroup limit (confirmed via
# `dmesg`'s CONSTRAINT_MEMCG OOM events during this measurement, contradicting
# 01-cluster-up.sh's "advisory, not enforced" comment - see 03-04-SUMMARY.md).
# Running 2 concurrent branches (2020-02 paired with 2020-03, the two
# largest months in the 3-month proof range) risks ~8GiB of task-pod memory
# alone on top of ~3GiB of baseline cluster infra, on a 10GiB node budget -
# a real crash risk, not theoretical. PARALLELISM is set to 1 for physical
# correctness on this constrained host; REQ-B5's "2-3 concurrent" wording
# needs a follow-up requirements-doc update, tracked in
# 03-04-SUMMARY.md rather than silently reinterpreted here.
PARALLELISM = 1

# The MinIO/MLflow credentials Secret every task touching object storage or
# the tracking server must mount - never a literal credential in this file.
_SECRET_NAME = "mlflow-minio-creds"
_SECRET_KEY_TO_ENV = {
    "AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY",
}


def _harden(task: PipelineTask, memory_request: str, memory_limit: str) -> PipelineTask:
    """Apply the shared caching + resource-limit hardening every task needs."""
    task.set_caching_options(enable_caching=True)
    task.set_memory_request(memory_request)
    task.set_memory_limit(memory_limit)
    task.set_cpu_request("250m")
    task.set_cpu_limit("1")
    return task


def _secret(task: PipelineTask) -> PipelineTask:
    """Mount the MinIO/MLflow credentials Secret as AWS_* env vars on task.

    Applied only to tasks that touch MinIO or MLflow (ingest, features,
    evaluate, register) - never to a task with no need for the credential.
    """
    return kubernetes.use_secret_as_env(
        task, secret_name=_SECRET_NAME, secret_key_to_env=_SECRET_KEY_TO_ENV
    )


@dsl.pipeline(name="nyc-trip-duration-training")
def train_pipeline(
    # lib.train.chronological_split partitions on SPLIT_TIMESTAMP
    # (2020-03-01) and raises a ValueError naming the empty side if either
    # partition would be empty. Every runnable start_month/end_month range
    # must therefore straddle that boundary; 2020-02 through 2020-04 is the
    # smallest range that does, and it doubles as D-13's 2-3 month backfill
    # subset - do not "simplify" this default to a single month.
    start_month: str = "2020-02",
    end_month: str = "2020-04",
    features_version: str = "v1",
    mlflow_tracking_uri: str = "http://mlflow.mlflow.svc.cluster.local:5000",
    s3_endpoint_url: str = "http://minio.mlflow.svc.cluster.local:9000",
    model_name: str = "nyc-trip-duration",
) -> None:
    """The full REQ-B4 training DAG.

    expand_months -> ParallelFor(ingest -> validate -> features) ->
    Collected -> merge -> train -> evaluate -> If(beats champion) ->
    register, with notify as the ExitHandler exit task covering both the
    success and failure paths (REQ-B9).
    """
    notify_task = notify()  # constructed before the with-block (SDK requirement)
    _harden(notify_task, "128Mi", "256Mi")

    with dsl.ExitHandler(exit_task=notify_task, name="exit-handler"):
        months_task = expand_months(start_month=start_month, end_month=end_month)
        _harden(months_task, "256Mi", "512Mi")

        # ingest/validate/features memory: bumped from an original 512Mi/1536Mi
        # to 1Gi/6Gi. 1536Mi was sized before any real month had run in-cluster;
        # plan 03-04 Task 3 measured 2020-02 (6.3M rows, the largest month in
        # this pipeline's 12-month window) peaking at ~5.4GiB RSS through
        # ingest alone even after the lib/artifacts.py memory-release fix. 6Gi
        # adds headroom above that measured peak. validate/features process
        # comparably-sized per-month data (validate reads ingest's full output;
        # features re-reads the validated frame and joins zone centroids), so
        # the same limit applies to all three rather than guessing a smaller
        # number for each - see PARALLELISM's comment above for why this and
        # the parallelism cut both stem from the same measurement.
        with dsl.ParallelFor(items=months_task.output, parallelism=PARALLELISM) as month:
            ingest_task = ingest(month=month, s3_endpoint_url=s3_endpoint_url)
            _harden(ingest_task, "1Gi", "6Gi")
            _secret(ingest_task)

            validate_task = validate(raw=ingest_task.outputs["raw"])
            _harden(validate_task, "1Gi", "6Gi")

            features_task = build_features_component(
                validated=validate_task.outputs["validated"],
                month=month,
                features_version=features_version,
                s3_endpoint_url=s3_endpoint_url,
            )
            _harden(features_task, "1Gi", "6Gi")
            _secret(features_task)

        merge_task = merge_features(parts=dsl.Collected(features_task.outputs["features"]))
        _harden(merge_task, "1Gi", "2Gi")

        train_task = train(merged=merge_task.outputs["merged"])
        _harden(train_task, "1Gi", "3Gi")

        evaluate_task = evaluate(
            model=train_task.outputs["model"],
            merged=merge_task.outputs["merged"],
            mlflow_tracking_uri=mlflow_tracking_uri,
            model_name=model_name,
        )
        _harden(evaluate_task, "1Gi", "2Gi")
        _secret(evaluate_task)

        # Ruff's E712 flags `== True`, but dsl.If's condition is built by
        # this exact operator overload on the pipeline channel - rewriting
        # it as a truthiness test would evaluate the placeholder channel
        # object itself, not construct a compile-time condition.
        with dsl.If(evaluate_task.outputs["beats_champion"] == True, name="beats-champion"):  # noqa: E712
            register_task = register(
                model=train_task.outputs["model"],
                rmse=evaluate_task.outputs["rmse"],
                mlflow_tracking_uri=mlflow_tracking_uri,
                model_name=model_name,
            )
            _harden(register_task, "512Mi", "1536Mi")
            _secret(register_task)
