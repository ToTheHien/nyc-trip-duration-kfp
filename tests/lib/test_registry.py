"""Exact-value, mocked-client tests for lib.registry.ModelRegistry."""

from unittest.mock import MagicMock

from mlflow.exceptions import MlflowException

from lib.registry import CANDIDATE_ALIAS, CHAMPION_ALIAS, RMSE_TAG, ModelRegistry


def test_get_champion_rmse_returns_none_when_client_raises() -> None:
    client = MagicMock()
    client.get_model_version_by_alias.side_effect = MlflowException("not found")
    registry = ModelRegistry(client, "trip-duration")

    assert registry.get_champion_rmse() is None


def test_get_champion_rmse_returns_float_of_tagged_version() -> None:
    client = MagicMock()
    version = MagicMock()
    version.tags = {RMSE_TAG: "123.45"}
    client.get_model_version_by_alias.return_value = version
    registry = ModelRegistry(client, "trip-duration")

    assert registry.get_champion_rmse() == 123.45


def test_promote_to_champion_calls_alias_setter_once() -> None:
    client = MagicMock()
    registry = ModelRegistry(client, "trip-duration")

    registry.promote_to_champion("3")

    client.set_registered_model_alias.assert_called_once_with("trip-duration", CHAMPION_ALIAS, "3")
    assert CHAMPION_ALIAS == "champion"


def test_set_candidate_calls_alias_setter_once() -> None:
    client = MagicMock()
    registry = ModelRegistry(client, "trip-duration")

    registry.set_candidate("4")

    client.set_registered_model_alias.assert_called_once_with("trip-duration", CANDIDATE_ALIAS, "4")
    assert CANDIDATE_ALIAS == "candidate"


def test_tag_version_rmse_calls_version_tag_setter() -> None:
    client = MagicMock()
    registry = ModelRegistry(client, "trip-duration")

    registry.tag_version_rmse("4", 12.5)

    client.set_model_version_tag.assert_called_once_with("trip-duration", "4", RMSE_TAG, "12.5")
