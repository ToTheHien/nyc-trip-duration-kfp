"""Exact-value tests for lib.schemas.trip_schema / validate_trips (D-09a tier one:
structural checks only, validated against an already-filtered frame)."""

import numpy as np
import pandas as pd
import pandera.errors as perr
import pytest

from lib.schemas import (
    PASSENGER_COUNT_MAX,
    PASSENGER_COUNT_MIN,
    VALID_ZONE_MAX,
    VALID_ZONE_MIN,
    trip_schema,
    validate_trips,
)


def _clean_frame(n: int = 5) -> pd.DataFrame:
    """A tiny, already-filtered synthetic frame: every column and value legal."""
    pickup = pd.date_range("2019-07-01", periods=n, freq="h")
    dropoff = pickup + pd.to_timedelta(600, unit="s")
    return pd.DataFrame(
        {
            "tpep_pickup_datetime": pickup,
            "tpep_dropoff_datetime": dropoff,
            "PULocationID": [1 + (i % 4) for i in range(n)],
            "DOLocationID": [1 + ((i + 1) % 4) for i in range(n)],
            "trip_distance": [1.0 + i * 0.5 for i in range(n)],
            "trip_duration_s": [600.0] * n,
            "passenger_count": [1.0 + (i % 3) for i in range(n)],
        }
    )


def test_validate_trips_returns_clean_frame_unchanged() -> None:
    df = _clean_frame()

    result = validate_trips(df)

    pd.testing.assert_frame_equal(result.reset_index(drop=True), df.reset_index(drop=True))


def test_validate_trips_raises_on_missing_required_column() -> None:
    df = _clean_frame().drop(columns=["tpep_pickup_datetime"])

    with pytest.raises(perr.SchemaErrors) as exc_info:
        validate_trips(df)
    assert "tpep_pickup_datetime" in str(exc_info.value)


def test_validate_trips_raises_on_wrong_dtype() -> None:
    df = _clean_frame()
    df["PULocationID"] = df["PULocationID"].astype(str)

    with pytest.raises(perr.SchemaErrors) as exc_info:
        validate_trips(df)
    assert "PULocationID" in str(exc_info.value)


def test_validate_trips_raises_on_zone_id_outside_valid_range() -> None:
    df = _clean_frame()
    df.loc[0, "PULocationID"] = 300

    with pytest.raises(perr.SchemaErrors) as exc_info:
        validate_trips(df)
    assert "PULocationID" in str(exc_info.value)


def test_validate_trips_raises_on_null_in_key_column() -> None:
    df = _clean_frame()
    df.loc[0, "trip_distance"] = None

    with pytest.raises(perr.SchemaErrors) as exc_info:
        validate_trips(df)
    assert "trip_distance" in str(exc_info.value)


def test_validate_trips_raises_on_dropoff_before_pickup() -> None:
    df = _clean_frame()
    dropoff = df["tpep_dropoff_datetime"].to_numpy().copy()
    dropoff[0] = df["tpep_pickup_datetime"].to_numpy()[0] - np.timedelta64(10, "s")
    df["tpep_dropoff_datetime"] = dropoff

    with pytest.raises(perr.SchemaErrors):
        validate_trips(df)


def test_validate_trips_passes_with_extra_unlisted_column() -> None:
    df = _clean_frame()
    df["some_new_tlc_column"] = "unvalidated"

    result = validate_trips(df)

    assert "some_new_tlc_column" in result.columns


def test_validate_trips_passes_with_all_null_fee_columns() -> None:
    df = _clean_frame()
    df["congestion_surcharge"] = pd.array([None] * len(df), dtype="float64")
    df["airport_fee"] = pd.array([None] * len(df), dtype="float64")

    result = validate_trips(df)

    assert result["congestion_surcharge"].isna().all()
    assert result["airport_fee"].isna().all()


def test_trip_schema_is_not_strict() -> None:
    assert trip_schema.strict is False


def test_trip_schema_fee_columns_absent_or_nullable() -> None:
    for col in ("congestion_surcharge", "airport_fee"):
        if col in trip_schema.columns:
            assert trip_schema.columns[col].nullable is True


def test_trip_schema_carries_real_checks_per_column() -> None:
    for col in ("PULocationID", "DOLocationID", "trip_distance", "passenger_count"):
        assert len(trip_schema.columns[col].checks) >= 1
    assert len(trip_schema.checks) >= 1


def test_trip_schema_zone_range_constants_match_check_bounds() -> None:
    assert VALID_ZONE_MIN == 1
    assert VALID_ZONE_MAX == 263
    assert PASSENGER_COUNT_MIN == 1
    assert PASSENGER_COUNT_MAX == 6
