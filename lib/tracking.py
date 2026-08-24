"""MLflow-facing adapters: champion lookup, candidate comparison,
registration and alias promotion.

This is the only module in the repository that constructs a real
MlflowClient or opens a real MLflow run. It stays unit-testable by taking
the mlflow module itself as an injected argument - the same seam
lib/registry.py established for the client - rather than importing mlflow
at module level. Promotion is driven purely through ModelRegistry's alias
methods; MLflow's deprecated numeric-stage transition surface is never used
(REQ-D3).
"""

from pathlib import Path
from typing import Any

from lib.artifacts import evaluate_from_parquet
from lib.evaluate import beats_champion
from lib.registry import ModelRegistry
from lib.train import load_booster


def _default_mlflow() -> Any:
    """Return the real mlflow module, for callers that do not inject one."""
    import mlflow

    return mlflow


def build_registry(mlflow_module: Any, tracking_uri: str, model_name: str) -> ModelRegistry:
    """Point mlflow_module at tracking_uri, construct a real MlflowClient
    against it, and wrap it in a ModelRegistry for model_name.

    tracking_uri arrives as a plain string parameter because it is a service
    endpoint, not a data artifact (ARCHITECTURE.md's Integration Points
    table).
    """
    mlflow_module.set_tracking_uri(tracking_uri)
    client = mlflow_module.MlflowClient(tracking_uri)
    return ModelRegistry(client, model_name)


def evaluate_and_compare(
    mlflow_module: Any,
    model_path: Path,
    features_path: Path,
    metrics_path: Path,
    tracking_uri: str,
    model_name: str,
) -> tuple[float, bool]:
    """Score the candidate model and compare it against the incumbent champion.

    Returns (candidate_rmse, beats_champion). A first-ever run with no
    champion returns True; an exact RMSE tie returns False, leaving the
    incumbent @champion alias in place (lib.evaluate.beats_champion's
    documented tie semantics).
    """
    candidate_rmse = evaluate_from_parquet(model_path, features_path, metrics_path)
    registry = build_registry(mlflow_module, tracking_uri, model_name)
    champion_rmse = registry.get_champion_rmse()
    return candidate_rmse, beats_champion(candidate_rmse, champion_rmse)


def register_and_promote(
    mlflow_module: Any,
    model_path: Path,
    rmse_value: float,
    tracking_uri: str,
    model_name: str,
) -> str:
    """Register model_path under model_name, tag the new version with
    rmse_value, point @candidate at it, then promote it to @champion.

    Returns the registered version string. This is the first place in the
    project a real MlflowClient/run is constructed rather than a mock.
    """
    mlflow_module.set_tracking_uri(tracking_uri)
    booster = load_booster(model_path)
    with mlflow_module.start_run():
        model_info = mlflow_module.lightgbm.log_model(
            booster, name=model_name, registered_model_name=model_name
        )
    version = str(model_info.registered_model_version)

    registry = build_registry(mlflow_module, tracking_uri, model_name)
    registry.tag_version_rmse(version, rmse_value)
    registry.set_candidate(version)
    registry.promote_to_champion(version)
    return version
