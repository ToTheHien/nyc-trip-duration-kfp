"""Path-in/path-out adapter layer between typed KFP artifacts and the Phase 2
`lib/` functions.

`components/` bodies are mechanically forbidden (scripts/check_component_boundary.sh)
from importing pandas/numpy or touching Parquet bytes directly, so every KFP
component makes exactly one call into this module: it reads a typed artifact's
`.path`, hands it here, and this module does the actual file I/O plus the one
`lib.<module>` call the component needs. This is the seam design decision 3 in
03-01-PLAN.md describes ("lib/ owns all file I/O, not just all pandas").
"""

import json
import logging
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import boto3
import pandas as pd

from lib.evaluate import rmse
from lib.features import FEATURE_COLUMNS, TARGET_COLUMN, ZONE_CATEGORY_DTYPE, build_features
from lib.features import load_zone_centroids as _load_zone_centroids
from lib.ingest import (
    add_trip_duration,
    filter_trip_quality,
    month_parquet_path,
    read_month_chunked,
)
from lib.months import month_range
from lib.schemas import validate_trips as _validate_trips
from lib.train import (
    CATEGORICAL_FEATURES,
    chronological_split,
    load_booster,
    save_model,
    train_trip_duration_model,
)

logger = logging.getLogger(__name__)

ARTIFACT_VERSION_DEFAULT: str = "v1"
RAW_BUCKET: str = "tlc-raw"
BACKFILL_BUCKET: str = "backfill"


def artifact_key(month: str, stage: str, version: str = ARTIFACT_VERSION_DEFAULT) -> str:
    """Return the deterministic backfill key `{version}/{stage}/{month}.parquet`.

    Delegates month validation to lib.months.month_range - the same
    delegation lib.ingest.month_parquet_path already uses - rather than
    writing a second month parser. Raises ValueError naming the offending
    value when stage or version is empty or contains a path separator, so a
    malformed pipeline parameter cannot escape its key prefix or traverse
    into another stage's namespace.
    """
    month_range(month, month)
    if not stage or "/" in stage:
        raise ValueError(f"stage must be non-empty and contain no path separator, got {stage!r}")
    if not version or "/" in version:
        raise ValueError(
            f"version must be non-empty and contain no path separator, got {version!r}"
        )
    return f"{version}/{stage}/{month}.parquet"


def default_s3_client(endpoint_url: str) -> Any:
    """Return a boto3 S3 client for endpoint_url, taking credentials only from
    the standard AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY environment
    variables boto3 already consults. Never accepts or logs a credential.
    """
    return boto3.client("s3", endpoint_url=endpoint_url)


def download_object(client: Any, bucket: str, key: str, dest: Path) -> Path:
    """Download bucket/key to dest, creating dest's parent directory first.

    Lets botocore errors propagate uncaught - a missing key must never
    become a silent empty file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, key, str(dest))
    return dest


def upload_object(client: Any, path: Path, bucket: str, key: str) -> None:
    """Upload path to bucket/key."""
    client.upload_file(str(path), bucket, key)


def publish_deterministic(
    client: Any,
    path: Path,
    month: str,
    stage: str,
    version: str = ARTIFACT_VERSION_DEFAULT,
) -> str:
    """Upload path into BACKFILL_BUCKET at artifact_key(month, stage, version),
    with full-overwrite semantics (a plain upload_file call always replaces
    whatever object previously existed at that key). Returns the key.
    """
    key = artifact_key(month, stage, version)
    upload_object(client, path, BACKFILL_BUCKET, key)
    return key


def ingest_month_to_parquet(
    client: Any, month: str, out_path: Path, bucket: str = RAW_BUCKET
) -> int:
    """Download yellow_tripdata_{month}.parquet from bucket into a temporary
    directory using the exact filename shape lib.ingest.month_parquet_path
    expects (so that temp directory is a drop-in data_dir), then compose the
    read + duration-derivation + row-quality-filter primitives directly -
    see design decision 4 in 03-01-PLAN.md: lib.ingest's orchestrator
    function also structurally validates, and this stage must stay a
    distinct DAG node from validate - write the survivors to out_path, and
    return the kept row count.

    Emits the same INFO record lib.ingest's orchestrator function emits
    (month plus every dropped count), so REQ-C1's "not silently" survives
    the ingest/validate split.
    """
    with tempfile.TemporaryDirectory() as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        raw_path = month_parquet_path(month, tmp_dir)
        download_object(client, bucket, raw_path.name, raw_path)

        df = read_month_chunked(raw_path)

    df = add_trip_duration(df)
    kept, report = filter_trip_quality(df)

    logger.info(
        "ingest_month_to_parquet %s: kept %d/%d rows (dropped: non_positive_distance=%d "
        "non_positive_duration=%d unmapped_zone=%d passenger_count=%d)",
        month,
        report.kept_rows,
        report.total_rows,
        report.dropped_non_positive_distance,
        report.dropped_non_positive_duration,
        report.dropped_unmapped_zone,
        report.dropped_passenger_count,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept.to_parquet(out_path, index=False)
    return report.kept_rows


def validate_parquet(in_path: Path, out_path: Path) -> int:
    """Read in_path, validate via lib.schemas.validate_trips, write out_path,
    return the row count. Structural drift raises out of here loudly.
    """
    df = pd.read_parquet(in_path)
    validated = _validate_trips(df)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    validated.to_parquet(out_path, index=False)
    return len(validated)


def build_features_parquet(in_path: Path, out_path: Path) -> int:
    """Read in_path, join zone centroids, build the feature frame, write
    out_path, return the row count.

    Note: Parquet has no native categorical logical type. pyarrow restores
    pandas' embedded "categorical" metadata automatically for string-keyed
    categoricals, but not for the int-keyed ones this project uses
    (PULocationID/DOLocationID/VendorID) - verified empirically against this
    repo's pinned pandas==2.3.3/pyarrow==25.0.1: a bare pd.read_parquet on
    this function's own output returns those three columns as plain int64,
    not category. Every real reader of a features-shaped Parquet file in this
    codebase already re-establishes the dtype explicitly at the point of use
    (lib.train.train_trip_duration_model casts before fit;
    evaluate_from_parquet below casts before predict) rather than relying on
    the round trip alone, which is why this function does not need to
    compensate for it here.

    Also carries tpep_pickup_datetime through as a passthrough column beyond
    lib.features.FEATURE_COLUMNS/TARGET_COLUMN's locked (Phase 2) contract:
    lib.train.chronological_split needs it to split the merged features
    artifact in train_from_parquet/evaluate_from_parquet below, and
    build_features itself must not be widened to carry it (that would change
    a Phase-2-locked public signature out of this plan's scope).
    """
    df = pd.read_parquet(in_path)
    centroids = _load_zone_centroids()
    features = build_features(df, centroids)
    features = features.assign(tpep_pickup_datetime=df["tpep_pickup_datetime"].to_numpy())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(out_path, index=False)
    return len(features)


def build_and_publish_features(
    client: Any,
    in_path: Path,
    out_path: Path,
    month: str,
    version: str = ARTIFACT_VERSION_DEFAULT,
) -> tuple[int, str]:
    """Build the feature frame and publish it to the deterministic backfill
    key in one call, so the features component makes exactly one lib call.
    """
    n_rows = build_features_parquet(in_path, out_path)
    key = publish_deterministic(client, out_path, month, "features", version)
    return n_rows, key


def merge_feature_parquets(in_paths: Sequence[Path], out_path: Path) -> int:
    """Concatenate in_paths (sorted by str(path) first, so the merged row
    order is independent of the order dsl.Collected hands them back - KFP
    does not specify that order), write out_path, return the row count.

    Raises ValueError on an empty in_paths.
    """
    if not in_paths:
        raise ValueError("merge_feature_parquets requires at least one input path")
    sorted_paths = sorted(in_paths, key=str)
    frames = [pd.read_parquet(p) for p in sorted_paths]
    merged = pd.concat(frames, ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(out_path, index=False)
    return len(merged)


def train_from_parquet(features_path: Path, model_path: Path) -> None:
    """Read features_path, chronologically split, train on the train side,
    and save the resulting model to model_path.
    """
    df = pd.read_parquet(features_path)
    train, _test = chronological_split(df)
    x = train[list(FEATURE_COLUMNS)]
    y = train[TARGET_COLUMN]
    model = train_trip_duration_model(x, y)
    save_model(model, model_path)


def evaluate_from_parquet(model_path: Path, features_path: Path, metrics_path: Path) -> float:
    """Read features_path, chronologically split, cast the test side's
    categorical columns to mirror train_trip_duration_model's in-place
    casts, load the Booster, score with lib.evaluate.rmse (not
    evaluate_model, which is annotated for LGBMRegressor and would fail
    mypy --strict against a Booster), write a JSON metrics document, and
    return the rmse.
    """
    df = pd.read_parquet(features_path)
    _train, test = chronological_split(df)

    x_test = test[list(FEATURE_COLUMNS)].copy()
    y_test = test[TARGET_COLUMN]
    x_test["PULocationID"] = x_test["PULocationID"].astype(ZONE_CATEGORY_DTYPE)
    x_test["DOLocationID"] = x_test["DOLocationID"].astype(ZONE_CATEGORY_DTYPE)
    for col in CATEGORICAL_FEATURES:
        if col not in ("PULocationID", "DOLocationID"):
            x_test[col] = x_test[col].astype("category")

    booster = load_booster(model_path)
    predictions = booster.predict(x_test)
    rmse_value = rmse(y_test, cast(Any, predictions))

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps({"rmse": rmse_value, "n_rows": len(x_test)}), encoding="utf-8"
    )
    return rmse_value
