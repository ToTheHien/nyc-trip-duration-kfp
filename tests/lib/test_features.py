"""Exact-value tests for lib.features's vectorized haversine, zone-centroid join, and
dtype-downcasting contract (REQ-C2 / REQ-C3)."""

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lib.features import (
    EARTH_RADIUS_KM,
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    ZONE_CATEGORY_DTYPE,
    ZONE_CENTROID_PATH,
    build_features,
    downcast_features,
    haversine_km,
    haversine_km_rowwise,
    join_zone_centroids,
    load_zone_centroids,
)


def _synthetic_centroids() -> pd.DataFrame:
    """A 4-zone synthetic centroid table."""
    return pd.DataFrame(
        {
            "zone_id": [1, 2, 3, 4],
            "centroid_lat": [40.7128, 40.7614, 40.6892, 40.7484],
            "centroid_lon": [-74.0060, -73.9776, -74.0445, -73.9857],
        }
    )


def _synthetic_trip_frame(n: int) -> pd.DataFrame:
    """A tiny, in-memory synthetic Yellow-schema-shaped frame with zones 1-4 only."""
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
            "trip_duration_s": [600.0 + (i % 5) * 60 for i in range(n)],
        }
    )


# --- haversine_km ------------------------------------------------------------


def test_haversine_km_matches_known_equatorial_one_degree_distance() -> None:
    # Two points on the equator, one degree of longitude apart: the great-circle
    # distance reduces exactly to EARTH_RADIUS_KM * radians(1) - an independent
    # closed-form check, not a re-derivation of the haversine formula itself.
    lat = pd.Series([0.0])
    lon1 = pd.Series([0.0])
    lon2 = pd.Series([1.0])
    expected = EARTH_RADIUS_KM * math.radians(1.0)

    result = haversine_km(lat, lon1, lat, lon2)

    assert result.iloc[0] == pytest.approx(expected, rel=0.005)


def test_haversine_km_identical_coordinates_returns_exact_zero() -> None:
    lat = pd.Series([40.7128, -33.8688])
    lon = pd.Series([-74.0060, 151.2093])

    result = haversine_km(lat, lon, lat, lon)

    assert (result == 0.0).all()


def test_haversine_km_and_rowwise_agree_within_1e9() -> None:
    rng = np.random.default_rng(0)
    n = 50
    df = pd.DataFrame(
        {
            "pu_lat": rng.uniform(40.5, 40.9, size=n),
            "pu_lon": rng.uniform(-74.2, -73.7, size=n),
            "do_lat": rng.uniform(40.5, 40.9, size=n),
            "do_lon": rng.uniform(-74.2, -73.7, size=n),
        }
    )

    vectorized = haversine_km(df["pu_lat"], df["pu_lon"], df["do_lat"], df["do_lon"])
    rowwise = haversine_km_rowwise(df)

    np.testing.assert_allclose(vectorized.to_numpy(), rowwise.to_numpy(), atol=1e-9)


# --- load_zone_centroids -------------------------------------------------------


def test_load_zone_centroids_reads_real_committed_csv() -> None:
    result = load_zone_centroids(ZONE_CENTROID_PATH)

    assert list(result.columns) == ["zone_id", "centroid_lat", "centroid_lon"]
    assert len(result) == 263


def test_load_zone_centroids_raises_file_not_found_naming_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError, match=re.escape(str(missing_path))):
        load_zone_centroids(missing_path)


# --- join_zone_centroids --------------------------------------------------------


def test_join_zone_centroids_attaches_coordinates_and_preserves_row_count() -> None:
    df = _synthetic_trip_frame(6)
    centroids = _synthetic_centroids()

    result = join_zone_centroids(df, centroids)

    assert len(result) == 6
    assert {"pu_lat", "pu_lon", "do_lat", "do_lon"}.issubset(result.columns)
    assert result["pu_lat"].notna().all()
    assert result["do_lat"].notna().all()


# --- build_features --------------------------------------------------------------


def test_build_features_returns_exact_feature_columns_in_order() -> None:
    df = _synthetic_trip_frame(5)
    centroids = _synthetic_centroids()

    result = build_features(df, centroids)

    assert list(result.columns) == [*FEATURE_COLUMNS, TARGET_COLUMN]


def test_build_features_haversine_zero_for_identical_pickup_dropoff_zone() -> None:
    df = _synthetic_trip_frame(4)
    df["PULocationID"] = 2
    df["DOLocationID"] = 2
    centroids = _synthetic_centroids()

    result = build_features(df, centroids)

    assert (result["trip_distance_km"] == 0.0).all()


def test_build_features_never_calls_dataframe_or_series_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("build_features must never call .apply on the production path")

    monkeypatch.setattr(pd.DataFrame, "apply", _raise)
    monkeypatch.setattr(pd.Series, "apply", _raise)

    df = _synthetic_trip_frame(5)
    centroids = _synthetic_centroids()

    result = build_features(df, centroids)

    assert len(result) == 5


def test_build_features_is_idempotent() -> None:
    df = _synthetic_trip_frame(6)
    centroids = _synthetic_centroids()

    first = build_features(df, centroids)
    second = build_features(df, centroids)

    pd.testing.assert_frame_equal(first, second)


def test_build_features_does_not_mutate_input_frame() -> None:
    df = _synthetic_trip_frame(6)
    before = df.copy(deep=True)
    centroids = _synthetic_centroids()

    build_features(df, centroids)

    pd.testing.assert_frame_equal(df, before)


def test_build_features_raises_valueerror_naming_unmapped_zone_ids() -> None:
    df = _synthetic_trip_frame(3)
    df.loc[df.index[0], "PULocationID"] = 999
    centroids = _synthetic_centroids()

    with pytest.raises(ValueError, match="999"):
        build_features(df, centroids)


# --- downcast_features (REQ-C3) -----------------------------------------------


def _synthetic_merged_frame(n: int) -> pd.DataFrame:
    """A frame shaped like build_features' pre-downcast merged frame."""
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        {
            "PULocationID": rng.integers(1, 264, size=n),
            "DOLocationID": rng.integers(1, 264, size=n),
            "VendorID": rng.integers(1, 3, size=n),
            "passenger_count": rng.uniform(1.0, 6.0, size=n),
            "trip_distance": rng.uniform(0.1, 50000.0, size=n),
            "trip_distance_km": rng.uniform(0.1, 50000.0, size=n),
            "trip_duration_s": rng.uniform(0.1, 50000.0, size=n),
            "pickup_hour": rng.integers(0, 24, size=n),
            "pickup_dayofweek": rng.integers(0, 7, size=n),
        }
    )


def test_downcast_features_produces_float32_for_numeric_feature_columns() -> None:
    df = _synthetic_merged_frame(20)

    result = downcast_features(df)

    for col in ("trip_distance", "trip_distance_km", "trip_duration_s", "passenger_count"):
        assert result[col].dtype == np.float32


def test_downcast_features_produces_263_category_zone_dtype_and_vendor_category() -> None:
    df = _synthetic_merged_frame(20)

    result = downcast_features(df)

    assert isinstance(result["PULocationID"].dtype, pd.CategoricalDtype)
    assert isinstance(result["DOLocationID"].dtype, pd.CategoricalDtype)
    assert len(result["PULocationID"].dtype.categories) == 263
    assert len(result["DOLocationID"].dtype.categories) == 263
    assert isinstance(result["VendorID"].dtype, pd.CategoricalDtype)


def test_downcast_features_preserves_nan_in_passenger_count() -> None:
    df = _synthetic_merged_frame(10)
    df.loc[df.index[0], "passenger_count"] = np.nan

    result = downcast_features(df)

    assert pd.isna(result["passenger_count"].iloc[0])
    assert result["passenger_count"].dtype == np.float32


def test_downcast_features_preserves_values_within_relative_tolerance() -> None:
    df = _synthetic_merged_frame(200)

    result = downcast_features(df)

    for col in ("trip_distance", "trip_distance_km", "trip_duration_s"):
        np.testing.assert_allclose(
            result[col].to_numpy(dtype=np.float64), df[col].to_numpy(dtype=np.float64), rtol=1e-4
        )


def test_downcast_features_pickup_hour_and_dayofweek_are_int8_within_range() -> None:
    df = _synthetic_merged_frame(20)

    result = downcast_features(df)

    assert result["pickup_hour"].dtype == np.int8
    assert result["pickup_dayofweek"].dtype == np.int8
    assert result["pickup_hour"].between(0, 23).all()
    assert result["pickup_dayofweek"].between(0, 6).all()


def test_downcast_features_reduces_memory_usage() -> None:
    df = _synthetic_merged_frame(2000)
    before_bytes = df.memory_usage(deep=True).sum()

    result = downcast_features(df)

    after_bytes = result.memory_usage(deep=True).sum()
    assert after_bytes < before_bytes


def test_downcast_features_returns_new_frame_leaves_input_dtypes_unchanged() -> None:
    df = _synthetic_merged_frame(20)
    before_dtypes = df.dtypes.copy()

    downcast_features(df)

    pd.testing.assert_series_equal(df.dtypes, before_dtypes)


def test_zone_category_dtype_is_immutable_categorical_dtype_object() -> None:
    assert isinstance(ZONE_CATEGORY_DTYPE, pd.CategoricalDtype)
    assert len(ZONE_CATEGORY_DTYPE.categories) == 263
