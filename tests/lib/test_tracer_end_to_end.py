"""End-to-end tracer: one synthetic month through ingest -> schemas -> features ->
train -> evaluate -> registry, proving a real finite positive RMSE (Phase 2, Task 3)."""

import math
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pandera.errors as perr
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from mlflow.exceptions import MlflowException

from lib.evaluate import rmse
from lib.features import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_features,
    haversine_km,
    load_zone_centroids,
)
from lib.ingest import TLC_DATA_DIR, add_trip_duration, month_parquet_path, read_month_chunked
from lib.registry import RMSE_TAG, ModelRegistry
from lib.schemas import validate_trips
from lib.train import train_trip_duration_model

_N_SYNTHETIC_ROWS = 40


def _synthetic_trip_frame(n: int) -> pd.DataFrame:
    """A tiny, in-memory synthetic Yellow-schema-shaped DataFrame (D-07: never real data)."""
    pickup = pd.date_range("2019-07-01", periods=n, freq="h")
    dropoff = pickup + pd.to_timedelta([600 + (i % 5) * 60 for i in range(n)], unit="s")
    return pd.DataFrame(
        {
            "VendorID": [1 + (i % 2) for i in range(n)],
            "tpep_pickup_datetime": pickup,
            "tpep_dropoff_datetime": dropoff,
            "PULocationID": [1 + (i % 4) for i in range(n)],
            "DOLocationID": [1 + ((i + 1) % 4) for i in range(n)],
            "trip_distance": [1.0 + (i % 7) * 0.3 for i in range(n)],
            "passenger_count": [1.0 + (i % 3) for i in range(n)],
        }
    )


def _synthetic_centroids() -> pd.DataFrame:
    """A 4-zone synthetic centroid table matching _synthetic_trip_frame's zone IDs."""
    return pd.DataFrame(
        {
            "zone_id": [1, 2, 3, 4],
            "centroid_lat": [40.7128, 40.7614, 40.6892, 40.7484],
            "centroid_lon": [-74.0060, -73.9776, -74.0445, -73.9857],
        }
    )


def test_read_month_chunked_returns_all_rows_in_order(tmp_path: Path) -> None:
    df = _synthetic_trip_frame(_N_SYNTHETIC_ROWS)
    path = tmp_path / "synthetic_month.parquet"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)

    result = read_month_chunked(path, batch_size=8)

    assert len(result) == _N_SYNTHETIC_ROWS
    assert list(result.columns) == list(df.columns)
    pd.testing.assert_frame_equal(
        result.reset_index(drop=True), df.reset_index(drop=True), check_like=False
    )


def test_month_parquet_path_builds_expected_filename() -> None:
    result = month_parquet_path("2019-07")

    assert result == TLC_DATA_DIR / "yellow_tripdata_2019-07.parquet"


def test_load_zone_centroids_reads_csv_columns(tmp_path: Path) -> None:
    path = tmp_path / "zone_centroids.csv"
    _synthetic_centroids().to_csv(path, index=False)

    result = load_zone_centroids(path)

    assert list(result.columns) == ["zone_id", "centroid_lat", "centroid_lon"]
    assert len(result) == 4


def test_add_trip_duration_computes_seconds_between_timestamps() -> None:
    df = pd.DataFrame(
        {
            "tpep_pickup_datetime": pd.to_datetime(["2019-07-01 08:00:00"]),
            "tpep_dropoff_datetime": pd.to_datetime(["2019-07-01 08:12:30"]),
        }
    )

    result = add_trip_duration(df)

    assert result["trip_duration_s"].iloc[0] == 750.0


def test_validate_trips_returns_clean_frame_unchanged() -> None:
    # trip_duration_s is required by lib.schemas.trip_schema as of plan
    # 02-04 (D-09a tier one); validate_trips expects a frame that has
    # already been through add_trip_duration, per its own docstring.
    df = add_trip_duration(_synthetic_trip_frame(5))

    result = validate_trips(df)

    assert len(result) == 5


def test_validate_trips_raises_on_missing_required_column() -> None:
    df = add_trip_duration(_synthetic_trip_frame(5)).drop(columns=["PULocationID"])

    with pytest.raises(perr.SchemaErrors):
        validate_trips(df)


def test_build_features_produces_exact_column_set() -> None:
    df = _synthetic_trip_frame(3)
    df = add_trip_duration(df)
    centroids = _synthetic_centroids()

    result = build_features(df, centroids)

    assert list(result.columns) == [*FEATURE_COLUMNS, TARGET_COLUMN]


def test_build_features_haversine_is_zero_for_identical_zones() -> None:
    df = pd.DataFrame(
        {
            "VendorID": [1],
            "tpep_pickup_datetime": pd.to_datetime(["2019-07-02 15:30:00"]),
            "tpep_dropoff_datetime": pd.to_datetime(["2019-07-02 15:45:00"]),
            "PULocationID": [3],
            "DOLocationID": [3],
            "trip_distance": [0.5],
            "passenger_count": [2.0],
            "trip_duration_s": [900.0],
        }
    )
    centroids = _synthetic_centroids()

    result = build_features(df, centroids)

    assert result["trip_distance_km"].iloc[0] == 0.0


def test_haversine_km_zero_for_identical_coordinates() -> None:
    lat = pd.Series([40.7128])
    lon = pd.Series([-74.0060])

    result = haversine_km(lat, lon, lat, lon)

    assert result.iloc[0] == 0.0


def test_train_trip_duration_model_predicts_finite_values() -> None:
    df = _synthetic_trip_frame(_N_SYNTHETIC_ROWS)
    df = add_trip_duration(df)
    centroids = _synthetic_centroids()
    features = build_features(df, centroids)
    # FEATURE_COLUMNS is a tuple (immutable module constant) - list(...) is
    # required here because pandas treats a bare tuple key as a single
    # (MultiIndex-style) lookup rather than a sequence of column names.
    x = features[list(FEATURE_COLUMNS)].copy()
    y = features[TARGET_COLUMN]

    model = train_trip_duration_model(x, y)
    predictions = model.predict(x)

    assert len(predictions) == len(x)
    assert all(math.isfinite(p) for p in predictions)


def test_rmse_hand_computed_pair() -> None:
    y_true = pd.Series([3.0, -0.5, 2.0, 7.0])
    y_pred = [2.5, 0.0, 2.0, 8.0]

    result = rmse(y_true, y_pred)

    assert result == pytest.approx(0.6123724356957945)


def test_get_champion_rmse_returns_none_when_no_champion() -> None:
    client = MagicMock()
    client.get_model_version_by_alias.side_effect = MlflowException("not found")
    registry = ModelRegistry(client, "trip-duration")

    assert registry.get_champion_rmse() is None


def test_get_champion_rmse_returns_float_when_champion_tagged() -> None:
    client = MagicMock()
    version = MagicMock()
    version.tags = {RMSE_TAG: "123.45"}
    client.get_model_version_by_alias.return_value = version
    registry = ModelRegistry(client, "trip-duration")

    assert registry.get_champion_rmse() == 123.45


def test_full_chain_produces_finite_positive_rmse(tmp_path: Path) -> None:
    """The tracer: read -> duration -> validate -> features -> fit -> rmse -> champion lookup."""
    df = _synthetic_trip_frame(_N_SYNTHETIC_ROWS)
    path = tmp_path / "synthetic_month.parquet"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)

    read_back = read_month_chunked(path, batch_size=8)
    with_duration = add_trip_duration(read_back)
    validated = validate_trips(with_duration)
    features = build_features(validated, _synthetic_centroids())

    # FEATURE_COLUMNS is a tuple (immutable module constant) - list(...) is
    # required here because pandas treats a bare tuple key as a single
    # (MultiIndex-style) lookup rather than a sequence of column names.
    x = features[list(FEATURE_COLUMNS)].copy()
    y = features[TARGET_COLUMN]
    model = train_trip_duration_model(x, y)
    predictions = model.predict(x)
    result_rmse = rmse(y, predictions)

    client = MagicMock()
    client.get_model_version_by_alias.side_effect = MlflowException("no champion yet")
    registry = ModelRegistry(client, "trip-duration")
    champion_rmse = registry.get_champion_rmse()

    assert math.isfinite(result_rmse)
    assert result_rmse > 0
    assert champion_rmse is None
