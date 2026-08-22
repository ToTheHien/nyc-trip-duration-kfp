"""Measure REQ-C2/REQ-C3's performance claims for real: row-wise vs vectorized haversine
distance, and float64/object vs downcast feature-frame memory, over a real cached TLC month.

Renders a markdown table (variant, rows, elapsed seconds, peak allocation MB, resulting
frame MB) that README's "Feature Engineering Benchmark" section pastes verbatim - this
script's own output is the only thing allowed to produce that table's numbers.
"""

import argparse
import platform
import re
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from lib.features import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    downcast_features,
    haversine_km,
    haversine_km_rowwise,
    join_zone_centroids,
    load_zone_centroids,
)
from lib.ingest import TLC_START_MONTH, load_month, month_parquet_path

DEFAULT_ROWS = 200_000
REPEATS = 3
_FILENAME_MONTH_PATTERN = re.compile(r"yellow_tripdata_(\d{4}-\d{2})\.parquet$")


def _month_and_data_dir(parquet_path: Path) -> tuple[str, Path]:
    """Parse the 'YYYY-MM' month out of a yellow_tripdata_YYYY-MM.parquet filename.

    load_month's real signature takes (month, data_dir), not a raw file path -
    this recovers both from --parquet so the benchmark still measures the
    real lib.ingest.load_month pipeline path (not a reimplementation) while
    keeping a single --parquet flag as the one thing a caller points at a
    different month's cached file.
    """
    match = _FILENAME_MONTH_PATTERN.search(parquet_path.name)
    if match is None:
        raise ValueError(
            f"could not parse a 'YYYY-MM' month from parquet filename: {parquet_path.name!r} "
            f"(expected the yellow_tripdata_YYYY-MM.parquet pattern)"
        )
    return match.group(1), parquet_path.parent


def _size_mb(obj: pd.DataFrame | pd.Series) -> float:
    """Deep memory footprint in MB, for either a DataFrame or a Series."""
    usage = obj.memory_usage(deep=True)
    total_bytes = float(usage.sum()) if isinstance(usage, pd.Series) else float(usage)
    return total_bytes / (1024 * 1024)


def _measure[T: (pd.DataFrame, pd.Series)](
    fn: Callable[[], T], repeats: int = REPEATS
) -> tuple[float, float, T]:
    """Run fn() `repeats` times; return (best elapsed seconds, peak MB of that run, result).

    Each repeat gets its own tracemalloc session so peak allocation is
    attributable to that specific run; the run with the lowest elapsed time
    (not necessarily the first) is reported, so a one-off scheduling hiccup
    never becomes the committed number.
    """
    best: tuple[float, float, T] | None = None
    for _ in range(repeats):
        tracemalloc.start()
        start = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak_bytes / (1024 * 1024)
        if best is None or elapsed < best[0]:
            best = (elapsed, peak_mb, result)
    assert best is not None  # repeats >= 1 is enforced by argparse
    return best


def _natural_feature_frame(joined: pd.DataFrame) -> pd.DataFrame:
    """The joined feature frame left at its natural float64/object dtypes (pre-downcast).

    Mirrors lib.features.build_features' pipeline up to (not including) its
    final downcast_features call, using only that module's public functions -
    this is variant 3's "before" state that variant 4 (downcast_features)
    measures the memory reduction against.
    """
    frame = joined.copy()
    frame["trip_distance_km"] = haversine_km(
        frame["pu_lat"], frame["pu_lon"], frame["do_lat"], frame["do_lon"]
    )
    frame["pickup_hour"] = frame["tpep_pickup_datetime"].dt.hour
    frame["pickup_dayofweek"] = frame["tpep_pickup_datetime"].dt.dayofweek
    return frame[[*FEATURE_COLUMNS, TARGET_COLUMN]]


def _machine_description() -> str:
    return f"Python {platform.python_version()}, {_cpu_count()} CPUs, {_total_ram_gb():.1f} GB RAM"


def _cpu_count() -> int:
    import os

    return os.cpu_count() or 0


def _total_ram_gb() -> float:
    import os

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        n_pages = os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return float("nan")
    return (page_size * n_pages) / (1024**3)


def _render_table(rows: list[tuple[str, int, float, float, float]]) -> str:
    header = "| Variant | Rows | Elapsed (s) | Peak Alloc (MB) | Frame Size (MB) |"
    separator = "|---|---|---|---|---|"
    body = [
        f"| {name} | {n:,} | {elapsed:.3f} | {peak_mb:.2f} | {frame_mb:.2f} |"
        for name, n, elapsed, peak_mb, frame_mb in rows
    ]
    return "\n".join([header, separator, *body])


def run_benchmark(parquet_path: Path, max_rows: int) -> str:
    """Run all four measured variants and return the rendered markdown report."""
    month, data_dir = _month_and_data_dir(parquet_path)
    df, _filter_report = load_month(month, data_dir=data_dir)
    if len(df) > max_rows:
        df = df.iloc[:max_rows].reset_index(drop=True)
    n_rows = len(df)

    centroids = load_zone_centroids()
    joined = join_zone_centroids(df, centroids)

    rowwise_elapsed, rowwise_peak, rowwise_dist = _measure(lambda: haversine_km_rowwise(joined))
    vectorized_elapsed, vectorized_peak, vectorized_dist = _measure(
        lambda: haversine_km(joined["pu_lat"], joined["pu_lon"], joined["do_lat"], joined["do_lon"])
    )
    natural_elapsed, natural_peak, natural_frame = _measure(lambda: _natural_feature_frame(joined))
    downcast_elapsed, downcast_peak, downcast_frame = _measure(
        lambda: downcast_features(natural_frame)
    )

    rows = [
        (
            "1. Row-wise haversine (`haversine_km_rowwise`, baseline)",
            n_rows,
            rowwise_elapsed,
            rowwise_peak,
            _size_mb(rowwise_dist),
        ),
        (
            "2. Vectorized haversine (`haversine_km`, production)",
            n_rows,
            vectorized_elapsed,
            vectorized_peak,
            _size_mb(vectorized_dist),
        ),
        (
            "3. Joined feature frame (float64/object, pre-downcast)",
            n_rows,
            natural_elapsed,
            natural_peak,
            _size_mb(natural_frame),
        ),
        (
            "4. Downcast feature frame (`downcast_features`, float32/category)",
            n_rows,
            downcast_elapsed,
            downcast_peak,
            _size_mb(downcast_frame),
        ),
    ]

    natural_mb = _size_mb(natural_frame)
    downcast_mb = _size_mb(downcast_frame)
    speedup = rowwise_elapsed / vectorized_elapsed if vectorized_elapsed > 0 else float("inf")
    memory_ratio = natural_mb / downcast_mb if downcast_mb > 0 else float("inf")

    lines = [
        f"Measured {n_rows:,} rows from `{month}` ({_machine_description()}).",
        "",
        _render_table(rows),
        "",
        f"Speedup (row-wise / vectorized): {speedup:.2f}x",
        f"Memory ratio (pre-downcast / downcast): {memory_ratio:.2f}x",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark lib.features' vectorized-vs-row-wise haversine distance "
        "and float64-vs-downcast feature-frame memory over a real cached TLC month."
    )
    parser.add_argument(
        "--parquet",
        type=Path,
        default=month_parquet_path(TLC_START_MONTH),
        help="Path to a cached TLC month Parquet file (default: the pinned first month).",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help=f"Cap on rows measured, so the run stays under a minute (default: {DEFAULT_ROWS}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the rendered markdown report to this file instead of stdout.",
    )
    args = parser.parse_args(argv)

    try:
        report = run_benchmark(args.parquet, args.rows)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.out is not None:
        args.out.write_text(report + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
