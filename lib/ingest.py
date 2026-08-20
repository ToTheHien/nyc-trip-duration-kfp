"""Chunked TLC Parquet ingest, trip-duration derivation, and the D-09a
row-level quality pre-filter (lib.schemas.trip_schema handles tier one:
structural validation of the frame this module hands it)."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd
import pyarrow.parquet as pq

from lib.months import month_range
from lib.schemas import (
    PASSENGER_COUNT_MAX,
    PASSENGER_COUNT_MIN,
    PLACEHOLDER_ZONE_IDS,
    validate_trips,
)

# REQ-D1 / D-07: the 12-month backfill window. Pinned once here so both the
# download script (plan 02-02) and the chronological train/test split
# (plan 02-03) read the same source of truth. Twelve consecutive months
# whose final quarter crosses the March-2020 COVID demand collapse — the
# drift event REQ-D1 exists to demonstrate.
TLC_START_MONTH = "2019-07"
TLC_END_MONTH = "2020-06"
TLC_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "tlc"

DEFAULT_BATCH_SIZE = 200_000

logger = logging.getLogger(__name__)


def month_parquet_path(month: str, data_dir: Path = TLC_DATA_DIR) -> Path:
    """Return the expected local path for a given 'YYYY-MM' month's Parquet file."""
    # Delegate month-string validation to lib.months' existing parser rather
    # than writing a second one.
    month_range(month, month)
    return data_dir / f"yellow_tripdata_{month}.parquet"


def read_month_chunked(path: Path, batch_size: int = DEFAULT_BATCH_SIZE) -> pd.DataFrame:
    """Read a Parquet file in bounded-memory batches via pyarrow's Arrow-batch iterator.

    pandas.read_parquet has no chunksize parameter, so it can only load a whole
    file into memory at once; pyarrow.parquet.ParquetFile.iter_batches bounds
    peak Arrow-batch residency instead (REQ-C4).

    This function only reads: it opens the file, materialises batches, and
    returns a DataFrame. It writes nothing, so an interrupted or
    concurrently-executed call cannot leave partial state behind on the
    filesystem — the property that makes it safe to call from several
    processes at once, which Phase 3's ParallelFor fan-out over months will
    do.
    """
    parquet_file = pq.ParquetFile(path)
    frames = [batch.to_pandas() for batch in parquet_file.iter_batches(batch_size=batch_size)]
    if not frames:
        # A zero-row file yields no batches; pd.concat([]) would raise, so
        # build the empty frame directly from the file's own Arrow schema to
        # preserve the source column set instead.
        return cast(pd.DataFrame, parquet_file.schema_arrow.empty_table().to_pandas())
    return cast(pd.DataFrame, pd.concat(frames, ignore_index=True))


def add_trip_duration(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with a trip_duration_s float column (dropoff - pickup, seconds).

    Derived via Series.dt.total_seconds(), producing float64 seconds with no
    rounding, truncation, or integer coercion at derivation time — fractional
    seconds survive to the feature stage. Only lib.features's later float32
    downcast reduces precision, deliberately and separately.
    """
    df = df.copy()
    delta = df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    df["trip_duration_s"] = delta.dt.total_seconds()
    return df


@dataclass(frozen=True)
class FilterReport:
    """Per-reason row-drop counts from filter_trip_quality, for load_month to log."""

    total_rows: int
    dropped_non_positive_distance: int
    dropped_non_positive_duration: int
    dropped_unmapped_zone: int
    dropped_passenger_count: int
    kept_rows: int


def filter_trip_quality(df: pd.DataFrame) -> tuple[pd.DataFrame, FilterReport]:
    """Pre-filter D-09a's four row-level noise reasons, counting each one.

    RESEARCH.md measured these rates live on real January-2019 data at
    roughly 0.98% for distance, 0.08% for duration, and 1.26% for passenger
    count — this is the normal profile of every TLC month, not corruption,
    which is precisely why it is filtered and counted here rather than
    rejected by lib.schemas.trip_schema. One boolean mask per reason keeps
    each count independently attributable; the combined mask is applied
    without sorting, so surviving rows keep their original relative order.

    A null passenger_count is kept (not dropped): pandera skips Checks on
    nulls in a nullable column, and dropping them would discard rows for a
    non-core field the schema itself tolerates as missing.
    """
    total_rows = len(df)

    non_positive_distance = df["trip_distance"] <= 0
    non_positive_duration = df["trip_duration_s"] <= 0
    unmapped_zone = df["PULocationID"].isin(PLACEHOLDER_ZONE_IDS) | df["DOLocationID"].isin(
        PLACEHOLDER_ZONE_IDS
    )
    passenger_count = df["passenger_count"]
    bad_passenger_count = passenger_count.notna() & (
        (passenger_count < PASSENGER_COUNT_MIN) | (passenger_count > PASSENGER_COUNT_MAX)
    )

    drop_mask = non_positive_distance | non_positive_duration | unmapped_zone | bad_passenger_count
    kept = df.loc[~drop_mask].copy()

    report = FilterReport(
        total_rows=total_rows,
        dropped_non_positive_distance=int(non_positive_distance.sum()),
        dropped_non_positive_duration=int(non_positive_duration.sum()),
        dropped_unmapped_zone=int(unmapped_zone.sum()),
        dropped_passenger_count=int(bad_passenger_count.sum()),
        kept_rows=int(len(kept)),
    )
    return kept, report


def load_month(
    month: str,
    data_dir: Path = TLC_DATA_DIR,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[pd.DataFrame, FilterReport]:
    """Orchestrate the D-09a ingest boundary for one month: read, derive duration,
    pre-filter row-level noise (logged), then structurally validate the survivors.

    Raises FileNotFoundError naming the missing path if month's Parquet file
    is absent. The INFO log record emitted here — naming the month and every
    dropped count — is the whole reason this filtering is not silent, which
    is how REQ-C1's "not silently" is satisfied under D-09a; it must never be
    downgraded to DEBUG or dropped.
    """
    path = month_parquet_path(month, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"no cached Parquet file for month {month!r} at {path}")

    df = read_month_chunked(path, batch_size=batch_size)
    df = add_trip_duration(df)
    filtered, report = filter_trip_quality(df)

    logger.info(
        "load_month %s: kept %d/%d rows (dropped: non_positive_distance=%d "
        "non_positive_duration=%d unmapped_zone=%d passenger_count=%d)",
        month,
        report.kept_rows,
        report.total_rows,
        report.dropped_non_positive_distance,
        report.dropped_non_positive_duration,
        report.dropped_unmapped_zone,
        report.dropped_passenger_count,
    )

    validated = validate_trips(filtered)
    return validated, report
