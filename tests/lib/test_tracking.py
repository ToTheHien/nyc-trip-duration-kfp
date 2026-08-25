"""Exact-value, mocked-mlflow-module tests for lib.tracking (100% coverage)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from lib.registry import CANDIDATE_ALIAS, CHAMPION_ALIAS, RMSE_TAG
from lib.tracking import (
    _default_mlflow,
    build_registry,
    evaluate_and_compare,
    register_and_promote,
)


def _mlflow_module_with_champion(rmse_value: str | None) -> MagicMock:
    """Return a MagicMock mlflow module whose MlflowClient().get_model_version_by_alias
    resolves to a champion tagged rmse_value, or raises MlflowException when
    rmse_value is None (no champion yet).
    """
    from mlflow.exceptions import MlflowException

    mlflow_module = MagicMock()
    client = mlflow_module.MlflowClient.return_value
    if rmse_value is None:
        client.get_model_version_by_alias.side_effect = MlflowException("not found")
    else:
        version = MagicMock()
        version.tags = {RMSE_TAG: rmse_value}
        client.get_model_version_by_alias.return_value = version
    return mlflow_module


def test_build_registry_sets_tracking_uri_and_constructs_client() -> None:
    mlflow_module = MagicMock()

    registry = build_registry(mlflow_module, "http://mlflow:5000", "trip-duration")

    mlflow_module.set_tracking_uri.assert_called_once_with("http://mlflow:5000")
    mlflow_module.MlflowClient.assert_called_once_with("http://mlflow:5000")
    assert registry._client is mlflow_module.MlflowClient.return_value
    assert registry._model_name == "trip-duration"


def test_evaluate_and_compare_no_champion_returns_true() -> None:
    mlflow_module = _mlflow_module_with_champion(None)

    with patch("lib.tracking.evaluate_from_parquet", return_value=10.0) as mock_eval:
        candidate_rmse, beats = evaluate_and_compare(
            mlflow_module,
            Path("model.txt"),
            Path("features.parquet"),
            Path("metrics.json"),
            "http://mlflow:5000",
            "trip-duration",
        )

    mock_eval.assert_called_once_with(
        Path("model.txt"), Path("features.parquet"), Path("metrics.json")
    )
    assert candidate_rmse == 10.0
    assert beats is True


def test_evaluate_and_compare_better_candidate_returns_true() -> None:
    mlflow_module = _mlflow_module_with_champion("20.0")

    with patch("lib.tracking.evaluate_from_parquet", return_value=10.0):
        candidate_rmse, beats = evaluate_and_compare(
            mlflow_module,
            Path("model.txt"),
            Path("features.parquet"),
            Path("metrics.json"),
            "http://mlflow:5000",
            "trip-duration",
        )

    assert candidate_rmse == 10.0
    assert beats is True


def test_evaluate_and_compare_exact_tie_resolves_false_and_never_promotes() -> None:
    mlflow_module = _mlflow_module_with_champion("10.0")
    client = mlflow_module.MlflowClient.return_value

    with patch("lib.tracking.evaluate_from_parquet", return_value=10.0):
        candidate_rmse, beats = evaluate_and_compare(
            mlflow_module,
            Path("model.txt"),
            Path("features.parquet"),
            Path("metrics.json"),
            "http://mlflow:5000",
            "trip-duration",
        )

    assert candidate_rmse == 10.0
    assert beats is False
    client.set_registered_model_alias.assert_not_called()


def test_register_and_promote_calls_sequence_in_order() -> None:
    mlflow_module = MagicMock()
    client = mlflow_module.MlflowClient.return_value
    mlflow_module.lightgbm.log_model.return_value.registered_model_version = "7"

    with patch("lib.tracking.load_booster", return_value="booster") as mock_load:
        version = register_and_promote(
            mlflow_module,
            Path("model.txt"),
            12.5,
            "http://mlflow:5000",
            "trip-duration",
        )

    assert version == "7"
    mock_load.assert_called_once_with(Path("model.txt"))
    mlflow_module.set_tracking_uri.assert_called_with("http://mlflow:5000")
    mlflow_module.start_run.assert_called_once_with()
    mlflow_module.lightgbm.log_model.assert_called_once_with(
        "booster", name="trip-duration", registered_model_name="trip-duration"
    )
    assert client.mock_calls == [
        (
            "set_model_version_tag",
            ("trip-duration", "7", RMSE_TAG, "12.5"),
            {},
        ),
        (
            "set_registered_model_alias",
            ("trip-duration", CANDIDATE_ALIAS, "7"),
            {},
        ),
        (
            "set_registered_model_alias",
            ("trip-duration", CHAMPION_ALIAS, "7"),
            {},
        ),
    ]


def test_default_mlflow_returns_the_real_module() -> None:
    import mlflow

    assert _default_mlflow() is mlflow
