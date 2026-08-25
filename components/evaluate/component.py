"""The evaluate KFP component: candidate Model + merged Dataset -> RMSE and
the champion-comparison outcome, via a real MLflow tracking server."""

from typing import NamedTuple

from kfp import dsl
from kfp.dsl import Dataset, Input, Metrics, Model, Output

from components import image_for


class EvaluateOutputs(NamedTuple):
    rmse: float
    beats_champion: bool


@dsl.component(base_image=image_for("evaluate"))
def evaluate(
    model: Input[Model],
    merged: Input[Dataset],
    mlflow_tracking_uri: str,
    model_name: str,
    metrics: Output[Metrics],
) -> EvaluateOutputs:
    from pathlib import Path

    from lib.tracking import _default_mlflow, evaluate_and_compare

    candidate_rmse, beats = evaluate_and_compare(
        _default_mlflow(),
        Path(model.path),
        Path(merged.path),
        Path(metrics.path),
        mlflow_tracking_uri,
        model_name,
    )
    metrics.log_metric("rmse", candidate_rmse)
    return EvaluateOutputs(rmse=candidate_rmse, beats_champion=beats)
