"""Chunked TLC Parquet ingest and trip-duration derivation."""

from pathlib import Path
from typing import cast

import pandas as pd
import pyarrow.parquet as pq

from lib.months import month_range

# REQ-D1 / D-07: the 12-month backfill window. Pinned once here so both the
# download script (plan 02-02) and the chronological train/test split
# (plan 02-03) read the same source of truth. Twelve consecutive months
# whose final quarter crosses the March-2020 COVID demand collapse — the
# drift event REQ-D1 exists to demonstrate.
TLC_START_MONTH = "2019-07"
TLC_END_MONTH = "2020-06"
TLC_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "tlc"

DEFAULT_BATCH_SIZE = 200_000


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
    """
    parquet_file = pq.ParquetFile(path)
    frames = [batch.to_pandas() for batch in parquet_file.iter_batches(batch_size=batch_size)]
    return cast(pd.DataFrame, pd.concat(frames, ignore_index=True))


def add_trip_duration(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with a trip_duration_s float column (dropoff - pickup, seconds)."""
    df = df.copy()
    delta = df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    df["trip_duration_s"] = delta.dt.total_seconds()
    return df
