"""Exact-value, mocked-S3-client tests for lib.artifacts's path-in/path-out
adapter layer (REQ-B2/B8 prerequisite)."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from lib.artifacts import (
    ARTIFACT_VERSION_DEFAULT,
    BACKFILL_BUCKET,
    RAW_BUCKET,
    artifact_key,
    build_and_publish_features,
    build_features_parquet,
    default_s3_client,
    download_object,
    evaluate_from_parquet,
    ingest_month_to_parquet,
    merge_feature_parquets,
    publish_deterministic,
    train_from_parquet,
    upload_object,
    validate_parquet,
)
from lib.features import FEATURE_COLUMNS, build_features, downcast_features
from lib.ingest import add_trip_duration


def _synthetic_ingest_frame(n: int) -> pd.DataFrame:
    """A tiny in-memory frame shaped like a raw yellow_tripdata month, using
    zone ids 1-4 (present in the real committed data/zone_centroids.csv)."""
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


def _write_parquet(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def _validated_frame(n: int) -> pd.DataFrame:
    """A frame shaped like validate_parquet's output: raw + trip_duration_s."""
    return add_trip_duration(_synthetic_ingest_frame(n))


# --- artifact_key ------------------------------------------------------------


def test_artifact_key_normal_month_returns_expected_key() -> None:
    assert artifact_key("2019-07", "features") == "v1/features/2019-07.parquet"


def test_artifact_key_uses_default_version() -> None:
    expected = f"{ARTIFACT_VERSION_DEFAULT}/features/2019-07.parquet"
    assert artifact_key("2019-07", "features") == expected


def test_artifact_key_custom_version() -> None:
    assert artifact_key("2019-07", "features", version="v2") == "v2/features/2019-07.parquet"


def test_artifact_key_raises_valueerror_naming_malformed_month() -> None:
    with pytest.raises(ValueError, match="2019-7"):
        artifact_key("2019-7", "features")


def test_artifact_key_raises_valueerror_on_empty_stage() -> None:
    with pytest.raises(ValueError, match="stage"):
        artifact_key("2019-07", "")


def test_artifact_key_raises_valueerror_on_stage_containing_separator() -> None:
    with pytest.raises(ValueError, match="stage"):
        artifact_key("2019-07", "features/evil")


def test_artifact_key_raises_valueerror_on_empty_version() -> None:
    with pytest.raises(ValueError, match="version"):
        artifact_key("2019-07", "features", version="")


def test_artifact_key_raises_valueerror_on_version_containing_separator() -> None:
    with pytest.raises(ValueError, match="version"):
        artifact_key("2019-07", "features", version="v1/evil")


# --- default_s3_client ---------------------------------------------------------


def test_default_s3_client_constructs_boto3_client_with_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_boto3 = MagicMock()
    monkeypatch.setattr("lib.artifacts.boto3", mock_boto3)

    default_s3_client("http://minio.mlflow.svc.cluster.local:9000")

    mock_boto3.client.assert_called_once_with(
        "s3", endpoint_url="http://minio.mlflow.svc.cluster.local:9000"
    )


# --- download_object / upload_object -------------------------------------------


def test_download_object_writes_dest_and_creates_parent(tmp_path: Path) -> None:
    client = MagicMock()

    def _fake_download(bucket: str, key: str, dest: str) -> None:
        Path(dest).write_bytes(b"hello")

    client.download_file.side_effect = _fake_download
    dest = tmp_path / "nested" / "out.bin"

    result = download_object(client, "some-bucket", "some-key", dest)

    assert result == dest
    assert dest.read_bytes() == b"hello"
    client.download_file.assert_called_once_with("some-bucket", "some-key", str(dest))


def test_download_object_propagates_client_error(tmp_path: Path) -> None:
    client = MagicMock()
    client.download_file.side_effect = RuntimeError("object not found")
    dest = tmp_path / "out.bin"

    with pytest.raises(RuntimeError, match="object not found"):
        download_object(client, "some-bucket", "missing-key", dest)


def test_upload_object_calls_upload_file(tmp_path: Path) -> None:
    client = MagicMock()
    path = tmp_path / "in.bin"
    path.write_bytes(b"data")

    upload_object(client, path, "some-bucket", "some-key")

    client.upload_file.assert_called_once_with(str(path), "some-bucket", "some-key")


# --- publish_deterministic ------------------------------------------------------


def test_publish_deterministic_uploads_to_backfill_bucket_at_artifact_key(
    tmp_path: Path,
) -> None:
    client = MagicMock()
    path = tmp_path / "features.parquet"
    path.write_bytes(b"data")

    key = publish_deterministic(client, path, "2019-07", "features")

    assert key == "v1/features/2019-07.parquet"
    client.upload_file.assert_called_once_with(str(path), BACKFILL_BUCKET, key)


# --- ingest_month_to_parquet -----------------------------------------------------


def _mock_client_serving_month_file(source_path: Path) -> MagicMock:
    """A mocked S3 client whose download_file copies source_path's bytes to dest."""
    client = MagicMock()

    def _fake_download(bucket: str, key: str, dest: str) -> None:
        Path(dest).write_bytes(source_path.read_bytes())

    client.download_file.side_effect = _fake_download
    return client


def test_ingest_month_to_parquet_downloads_filters_and_writes_kept_rows(
    tmp_path: Path,
) -> None:
    df = _synthetic_ingest_frame(6)
    df.loc[0, "trip_distance"] = 0.0  # forces one row to be dropped
    source_path = tmp_path / "source" / "yellow_tripdata_2019-07.parquet"
    _write_parquet(df, source_path)

    client = _mock_client_serving_month_file(source_path)
    out_path = tmp_path / "raw.parquet"

    kept_rows = ingest_month_to_parquet(client, "2019-07", out_path, bucket=RAW_BUCKET)

    assert kept_rows == 5
    result = pd.read_parquet(out_path)
    assert len(result) == 5
    client.download_file.assert_called_once_with(
        RAW_BUCKET, "yellow_tripdata_2019-07.parquet", client.download_file.call_args[0][2]
    )


def test_ingest_month_to_parquet_propagates_download_failure(tmp_path: Path) -> None:
    client = MagicMock()
    client.download_file.side_effect = RuntimeError("no such object")
    out_path = tmp_path / "raw.parquet"

    with pytest.raises(RuntimeError, match="no such object"):
        ingest_month_to_parquet(client, "2019-07", out_path)


# --- validate_parquet -------------------------------------------------------------


def test_validate_parquet_writes_validated_rows_and_returns_count(tmp_path: Path) -> None:
    df = _validated_frame(4)
    in_path = tmp_path / "raw.parquet"
    _write_parquet(df, in_path)
    out_path = tmp_path / "validated.parquet"

    n_rows = validate_parquet(in_path, out_path)

    assert n_rows == 4
    assert len(pd.read_parquet(out_path)) == 4


# --- build_features_parquet / dtype preservation ---------------------------------


def test_build_features_parquet_writes_expected_row_count(tmp_path: Path) -> None:
    df = _validated_frame(5)
    in_path = tmp_path / "validated.parquet"
    _write_parquet(df, in_path)
    out_path = tmp_path / "features.parquet"

    n_rows = build_features_parquet(in_path, out_path)

    assert n_rows == 5
    assert len(pd.read_parquet(out_path)) == 5


def test_build_features_parquet_round_trip_preserves_feature_dtype_contract(
    tmp_path: Path,
) -> None:
    """The dtypes lib.features.downcast_features writes are the dtypes the
    next stage reads back.

    Parquet has no native categorical logical type: pyarrow auto-restores
    pandas' embedded metadata for *string*-keyed categorical columns, but not
    for the int-keyed ones this project uses - verified empirically against
    this repo's pinned pandas==2.3.3/pyarrow==25.0.1, a bare pd.read_parquet
    on a categorical PULocationID/DOLocationID/VendorID column returns plain
    int64. Every real consumer in this codebase (lib.train's fit-time cast,
    evaluate_from_parquet's predict-time cast) re-establishes the dtype
    explicitly at the point of use rather than trusting the round trip alone
    - this test proves that reapplying lib.features.downcast_features (what
    those real consumers effectively do) exactly restores build_features's
    original dtype for every FEATURE_COLUMNS entry.
    """
    from lib.features import load_zone_centroids

    df = _validated_frame(6)
    expected = build_features(df, load_zone_centroids())

    in_path = tmp_path / "validated.parquet"
    _write_parquet(df, in_path)
    out_path = tmp_path / "features.parquet"
    build_features_parquet(in_path, out_path)

    read_back = downcast_features(pd.read_parquet(out_path))

    for col in FEATURE_COLUMNS:
        assert read_back[col].dtype == expected[col].dtype, f"dtype mismatch for {col!r}"


# --- build_and_publish_features ---------------------------------------------------


def test_build_and_publish_features_uploads_at_artifact_key(tmp_path: Path) -> None:
    df = _validated_frame(4)
    in_path = tmp_path / "validated.parquet"
    _write_parquet(df, in_path)
    out_path = tmp_path / "features.parquet"
    client = MagicMock()

    n_rows, key = build_and_publish_features(client, in_path, out_path, "2019-07")

    assert n_rows == 4
    assert key == "v1/features/2019-07.parquet"
    client.upload_file.assert_called_once_with(str(out_path), BACKFILL_BUCKET, key)


# --- merge_feature_parquets --------------------------------------------------------


def test_merge_feature_parquets_raises_valueerror_on_empty_in_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        merge_feature_parquets([], tmp_path / "merged.parquet")


def test_merge_feature_parquets_order_independent_of_input_order(tmp_path: Path) -> None:
    df_a = pd.DataFrame({"month": ["2019-07"], "value": [1]})
    df_b = pd.DataFrame({"month": ["2019-08"], "value": [2]})
    df_c = pd.DataFrame({"month": ["2019-09"], "value": [3]})

    path_a = tmp_path / "2019-07.parquet"
    path_b = tmp_path / "2019-08.parquet"
    path_c = tmp_path / "2019-09.parquet"
    _write_parquet(df_a, path_a)
    _write_parquet(df_b, path_b)
    _write_parquet(df_c, path_c)

    descending_out = tmp_path / "merged_descending.parquet"
    ascending_out = tmp_path / "merged_ascending.parquet"

    merge_feature_parquets([path_c, path_b, path_a], descending_out)
    merge_feature_parquets([path_a, path_b, path_c], ascending_out)

    pd.testing.assert_frame_equal(pd.read_parquet(descending_out), pd.read_parquet(ascending_out))


def test_merge_feature_parquets_returns_total_row_count(tmp_path: Path) -> None:
    df_a = pd.DataFrame({"value": [1, 2]})
    df_b = pd.DataFrame({"value": [3, 4, 5]})
    path_a = tmp_path / "a.parquet"
    path_b = tmp_path / "b.parquet"
    _write_parquet(df_a, path_a)
    _write_parquet(df_b, path_b)

    n_rows = merge_feature_parquets([path_a, path_b], tmp_path / "merged.parquet")

    assert n_rows == 5


# --- row-order preservation / byte-identity (REQ-B8 prerequisite) -----------------


def _run_ingest_validate_features_chain(source_path: Path, work_dir: Path) -> Path:
    """Run ingest -> validate -> features once, returning the final features path."""
    client = _mock_client_serving_month_file(source_path)
    raw_path = work_dir / "raw.parquet"
    ingest_month_to_parquet(client, "2019-07", raw_path)

    validated_path = work_dir / "validated.parquet"
    validate_parquet(raw_path, validated_path)

    features_path = work_dir / "features.parquet"
    build_features_parquet(validated_path, features_path)
    return features_path


def test_ingest_validate_features_chain_is_byte_identical_across_runs(
    tmp_path: Path,
) -> None:
    df = _synthetic_ingest_frame(10)
    source_path = tmp_path / "source" / "yellow_tripdata_2019-07.parquet"
    _write_parquet(df, source_path)

    first_features_path = _run_ingest_validate_features_chain(source_path, tmp_path / "run1")
    second_features_path = _run_ingest_validate_features_chain(source_path, tmp_path / "run2")

    first_hash = hashlib.sha256(first_features_path.read_bytes()).hexdigest()
    second_hash = hashlib.sha256(second_features_path.read_bytes()).hexdigest()
    assert first_hash == second_hash


# --- train_from_parquet / evaluate_from_parquet -------------------------------------


def _features_parquet_spanning_split(n_per_side: int, out_path: Path) -> Path:
    """Write a features-shaped Parquet (via the real build_features_parquet
    adapter, so it carries the same tpep_pickup_datetime passthrough column a
    real pipeline run would) with rows on both sides of SPLIT_TIMESTAMP.
    """
    from lib.train import SPLIT_TIMESTAMP

    pre_pickup = pd.date_range(
        SPLIT_TIMESTAMP - pd.Timedelta(days=n_per_side), periods=n_per_side, freq="D"
    )
    post_pickup = pd.date_range(SPLIT_TIMESTAMP, periods=n_per_side, freq="D")
    pickup = pre_pickup.append(post_pickup)
    n = len(pickup)
    dropoff = pickup + pd.to_timedelta([600 + (i % 5) * 60 for i in range(n)], unit="s")

    raw = pd.DataFrame(
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
    raw = add_trip_duration(raw)
    validated_path = out_path.parent / "validated.parquet"
    _write_parquet(raw, validated_path)
    build_features_parquet(validated_path, out_path)
    return out_path


def test_train_from_parquet_writes_a_loadable_model(tmp_path: Path) -> None:
    features_path = tmp_path / "features.parquet"
    _features_parquet_spanning_split(15, features_path)
    model_path = tmp_path / "model.txt"

    train_from_parquet(features_path, model_path)

    assert model_path.exists()


def test_evaluate_from_parquet_writes_metrics_and_returns_rmse(tmp_path: Path) -> None:
    features_path = tmp_path / "features.parquet"
    _features_parquet_spanning_split(15, features_path)
    model_path = tmp_path / "model.txt"
    train_from_parquet(features_path, model_path)

    metrics_path = tmp_path / "metrics.json"
    rmse_value = evaluate_from_parquet(model_path, features_path, metrics_path)

    assert isinstance(rmse_value, float)
    assert rmse_value >= 0.0
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["rmse"] == pytest.approx(rmse_value)
    assert metrics["n_rows"] == 15
