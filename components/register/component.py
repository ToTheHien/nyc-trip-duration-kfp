"""The register KFP component: promote a candidate model to @champion via
MLflow's alias API. Reachable only from inside the pipeline's
`beats-champion` dsl.If condition group (REQ-B7 static half) - this is the
first place in the project a real MlflowClient/run is constructed rather
than a mock.
"""

from kfp import dsl
from kfp.dsl import Input, Model

from components import image_for


@dsl.component(base_image=image_for("register"))
def register(model: Input[Model], rmse: float, mlflow_tracking_uri: str, model_name: str) -> str:
    from pathlib import Path

    from lib.tracking import _default_mlflow, register_and_promote

    return register_and_promote(
        _default_mlflow(), Path(model.path), rmse, mlflow_tracking_uri, model_name
    )
