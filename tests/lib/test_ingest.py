"""Exact-value tests for lib.ingest's chunked read, duration derivation, and D-09a
row-level quality pre-filter (filter_trip_quality, load_month)."""

import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from lib.ingest import (
    FilterReport,
    add_trip_duration,
    filter_trip_quality,
    load_month,
    read_month_chunked,
)

_N_SYNTHETIC_ROWS = 25


def _synthetic_trip_frame(n: int) -> pd.DataFrame:
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


def _write_parquet(df: pd.DataFrame, tmp_path: Path, name: str = "month.parquet") -> Path:
    path = tmp_path / name
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def _quality_frame(n: int) -> pd.DataFrame:
    """A frame with trip_duration_s already present, for filter_trip_quality tests."""
    return add_trip_duration(_synthetic_trip_frame(n))


# --- read_month_chunked ---------------------------------------------------


def test_read_month_chunked_returns_all_rows_in_source_order(tmp_path: Path) -> None:
    df = _synthetic_trip_frame(_N_SYNTHETIC_ROWS)
    path = _write_parquet(df, tmp_path)

    result = read_month_chunked(path, batch_size=4)

    assert list(result.columns) == list(df.columns)
    pd.testing.assert_frame_equal(
        result.reset_index(drop=True), df.reset_index(drop=True), check_like=False
    )


def test_read_month_chunked_zero_row_file_returns_empty_frame_with_columns(
    tmp_path: Path,
) -> None:
    df = _synthetic_trip_frame(0)
    path = _write_parquet(df, tmp_path)

    result = read_month_chunked(path, batch_size=4)

    assert len(result) == 0
    assert list(result.columns) == list(df.columns)


def test_read_month_chunked_single_row_file_returns_that_row(tmp_path: Path) -> None:
    df = _synthetic_trip_frame(1)
    path = _write_parquet(df, tmp_path)

    result = read_month_chunked(path, batch_size=4)

    assert len(result) == 1
    pd.testing.assert_frame_equal(
        result.reset_index(drop=True), df.reset_index(drop=True), check_like=False
    )


# --- add_trip_duration -----------------------------------------------------


def test_add_trip_duration_computes_exact_seconds() -> None:
    df = pd.DataFrame(
        {
            "tpep_pickup_datetime": pd.to_datetime(["2019-07-01 08:00:00"]),
            "tpep_dropoff_datetime": pd.to_datetime(["2019-07-01 08:12:30"]),
        }
    )

    result = add_trip_duration(df)

    assert result["trip_duration_s"].iloc[0] == 750.0


def test_add_trip_duration_preserves_fractional_seconds_without_rounding() -> None:
    df = pd.DataFrame(
        {
            "tpep_pickup_datetime": pd.to_datetime(["2019-07-01 08:00:00.000"]),
            "tpep_dropoff_datetime": pd.to_datetime(["2019-07-01 08:01:30.500"]),
        }
    )

    result = add_trip_duration(df)

    assert result["trip_duration_s"].iloc[0] == 90.5


# --- filter_trip_quality: distance ------------------------------------------


def test_filter_trip_quality_drops_non_positive_trip_distance() -> None:
    df = _quality_frame(4)
    df.loc[0, "trip_distance"] = 0.0
    df.loc[1, "trip_distance"] = -1.0

    kept, report = filter_trip_quality(df)

    assert report.dropped_non_positive_distance == 2
    assert 0 not in kept.index and 1 not in kept.index


# --- filter_trip_quality: duration ------------------------------------------


def test_filter_trip_quality_drops_zero_and_negative_duration() -> None:
    df = _quality_frame(4)
    df.loc[0, "trip_duration_s"] = 0.0
    df.loc[1, "trip_duration_s"] = -5.0  # dropoff before pickup

    kept, report = filter_trip_quality(df)

    assert report.dropped_non_positive_duration == 2
    assert 0 not in kept.index and 1 not in kept.index


# --- filter_trip_quality: zone ----------------------------------------------


def test_filter_trip_quality_drops_placeholder_zone_ids_keeps_boundary_zones() -> None:
    df = _quality_frame(4)
    df.loc[0, "PULocationID"] = 264
    df.loc[1, "DOLocationID"] = 265
    df.loc[2, "PULocationID"] = 1
    df.loc[2, "DOLocationID"] = 263

    kept, report = filter_trip_quality(df)

    assert report.dropped_unmapped_zone == 2
    assert 0 not in kept.index and 1 not in kept.index
    assert 2 in kept.index


# --- filter_trip_quality: passenger_count -----------------------------------


def test_filter_trip_quality_drops_passenger_count_0_and_7_keeps_1_and_6_and_null() -> None:
    df = _quality_frame(5)
    df.loc[0, "passenger_count"] = 0
    df.loc[1, "passenger_count"] = 7
    df.loc[2, "passenger_count"] = 1
    df.loc[3, "passenger_count"] = 6
    df.loc[4, "passenger_count"] = None

    kept, report = filter_trip_quality(df)

    assert report.dropped_passenger_count == 2
    assert 0 not in kept.index and 1 not in kept.index
    assert {2, 3, 4}.issubset(set(kept.index))


# --- filter_trip_quality: ordering / totals / edge frames -------------------


def test_filter_trip_quality_preserves_relative_order_of_unsorted_input() -> None:
    df = _quality_frame(6)
    shuffled = df.iloc[[5, 0, 4, 1, 3, 2]].reset_index(drop=True)

    kept, report = filter_trip_quality(shuffled)

    assert report.kept_rows == 6
    pd.testing.assert_frame_equal(kept.reset_index(drop=True), shuffled)


def test_filter_trip_quality_empty_frame_returns_empty_frame_and_all_zero_report() -> None:
    df = _quality_frame(0)

    kept, report = filter_trip_quality(df)

    assert len(kept) == 0
    assert report.total_rows == 0
    assert report.kept_rows == 0
    assert report.dropped_non_positive_distance == 0
    assert report.dropped_non_positive_duration == 0
    assert report.dropped_unmapped_zone == 0
    assert report.dropped_passenger_count == 0


def test_filter_trip_quality_report_accounts_for_every_row_single_violation_each() -> None:
    df = _quality_frame(5)
    df.loc[0, "trip_distance"] = 0.0
    df.loc[1, "trip_duration_s"] = 0.0
    df.loc[2, "PULocationID"] = 264
    df.loc[3, "passenger_count"] = 0
    # row 4 stays clean

    kept, report = filter_trip_quality(df)

    assert report.total_rows == 5
    assert (
        report.kept_rows
        + report.dropped_non_positive_distance
        + report.dropped_non_positive_duration
        + report.dropped_unmapped_zone
        + report.dropped_passenger_count
        == report.total_rows
    )
    assert report.kept_rows == 1


def test_filter_trip_quality_returns_frozen_filterreport_type() -> None:
    df = _quality_frame(1)

    _, report = filter_trip_quality(df)

    assert isinstance(report, FilterReport)


# --- load_month --------------------------------------------------------------


def test_load_month_emits_info_log_with_month_and_counts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    df = _synthetic_trip_frame(6)
    df.loc[0, "trip_distance"] = 0.0
    data_dir = tmp_path
    path = data_dir / "yellow_tripdata_2019-07.parquet"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)

    with caplog.at_level(logging.INFO):
        _, report = load_month("2019-07", data_dir=data_dir)

    assert report.dropped_non_positive_distance == 1
    [record] = [r for r in caplog.records if r.levelno == logging.INFO]
    message = record.getMessage()
    assert "2019-07" in message
    for count in (
        report.total_rows,
        report.kept_rows,
        report.dropped_non_positive_distance,
        report.dropped_non_positive_duration,
        report.dropped_unmapped_zone,
        report.dropped_passenger_count,
    ):
        assert str(count) in message


def test_load_month_raises_file_not_found_for_absent_month(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="2099-01"):
        load_month("2099-01", data_dir=tmp_path)
