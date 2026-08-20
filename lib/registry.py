"""Thin, mockable MLflow model-registry wrapper using alias-based promotion (REQ-D3)."""

from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

CHAMPION_ALIAS = "champion"
RMSE_TAG = "rmse"


class ModelRegistry:
    """Wraps an injected MLflow client so tests never construct a real one.

    No MLflow tracking server exists until Phase 3; every use of this class
    in Phase 2 passes a mocked client.
    """

    def __init__(self, client: MlflowClient, model_name: str) -> None:
        self._client = client
        self._model_name = model_name

    def get_champion_rmse(self) -> float | None:
        """Return the champion model version's tagged RMSE, or None if no champion exists."""
        try:
            version = self._client.get_model_version_by_alias(self._model_name, CHAMPION_ALIAS)
        except MlflowException:
            return None
        return float(version.tags[RMSE_TAG])
