"""Thin, mockable MLflow model-registry wrapper using alias-based promotion (REQ-D3)."""

from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

CHAMPION_ALIAS = "champion"
CANDIDATE_ALIAS = "candidate"
RMSE_TAG = "rmse"


class ModelRegistry:
    """Wraps an injected MLflow client so tests never construct a real one.

    No MLflow tracking server exists until Phase 3; every use of this class
    in Phase 2 passes a mocked client. Drives MLflow purely through the 3.x
    alias API (set_registered_model_alias/get_model_version_by_alias) - never
    MLflow's deprecated numeric-stage transition surface (REQ-D3).
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

    def tag_version_rmse(self, version: str, value: float) -> None:
        """Record value as the RMSE tag on model version.

        A later reviewer can reconstruct why a version was (or wasn't)
        promoted from this tag alone, rather than trusting the alias alone.
        """
        self._client.set_model_version_tag(self._model_name, version, RMSE_TAG, str(value))

    def set_candidate(self, version: str) -> None:
        """Point the @candidate alias at version."""
        self._client.set_registered_model_alias(self._model_name, CANDIDATE_ALIAS, version)

    def promote_to_champion(self, version: str) -> None:
        """Point the @champion alias at version."""
        self._client.set_registered_model_alias(self._model_name, CHAMPION_ALIAS, version)
