"""Exact-value tests for lib.train's chronological split, fixed config, and serialization."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lib.features import FEATURE_COLUMNS, TARGET_COLUMN, ZONE_CATEGORY_DTYPE
from lib.ingest import TLC_END_MONTH, TLC_START_MONTH
from lib.train import (
    LGBM_PARAMS,
    SPLIT_TIMESTAMP,
    chronological_split,
    load_booster,
    save_model,
    train_trip_duration_model,
)


def _straddling_frame() -> pd.DataFrame:
    """6 rows: 3 strictly before SPLIT_TIMESTAMP, 1 exactly on it, 2 strictly after."""
    timestamps = [
        SPLIT_TIMESTAMP - pd.Timedelta(2, unit="D"),
        SPLIT_TIMESTAMP - pd.Timedelta(1, unit="D"),
        SPLIT_TIMESTAMP - pd.Timedelta(1, unit="ns"),
        SPLIT_TIMESTAMP,
        SPLIT_TIMESTAMP + pd.Timedelta(1, unit="D"),
        SPLIT_TIMESTAMP + pd.Timedelta(2, unit="D"),
    ]
    return pd.DataFrame(
        {
            "tpep_pickup_datetime": timestamps,
            "row_id": list(range(6)),
        }
    )


def test_chronological_split_partitions_by_exact_row_index_sets() -> None:
    df = _straddling_frame()

    train, test = chronological_split(df)

    assert set(train["row_id"]) == {0, 1, 2}
    assert set(test["row_id"]) == {3, 4, 5}


def test_chronological_split_boundary_tie_lands_in_test() -> None:
    df = _straddling_frame()

    train, test = chronological_split(df)

    assert 3 in set(test["row_id"])
    assert 3 not in set(train["row_id"])


def test_chronological_split_one_nanosecond_before_lands_in_train() -> None:
    df = _straddling_frame()

    train, test = chronological_split(df)

    assert 2 in set(train["row_id"])
    assert 2 not in set(test["row_id"])


def test_chronological_split_row_counts_sum_and_disjoint() -> None:
    rng = np.random.default_rng(42)
    n = 20
    offsets_days = rng.integers(-10, 10, size=n)
    df = pd.DataFrame(
        {
            "tpep_pickup_datetime": [
                SPLIT_TIMESTAMP + pd.Timedelta(int(d), unit="D") for d in offsets_days
            ],
            "row_id": list(range(n)),
        }
    ).sample(frac=1.0, random_state=7)

    train, test = chronological_split(df)

    assert len(train) + len(test) == len(df)
    assert set(train.index).isdisjoint(set(test.index))


def test_chronological_split_shuffled_order_matches_sorted_order() -> None:
    sorted_df = _straddling_frame()
    shuffled_df = sorted_df.sample(frac=1.0, random_state=3)

    sorted_train, sorted_test = chronological_split(sorted_df)
    shuffled_train, shuffled_test = chronological_split(shuffled_df)

    pd.testing.assert_frame_equal(
        sorted_train.sort_values("row_id").reset_index(drop=True),
        shuffled_train.sort_values("row_id").reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(
        sorted_test.sort_values("row_id").reset_index(drop=True),
        shuffled_test.sort_values("row_id").reset_index(drop=True),
    )


def test_chronological_split_all_before_boundary_raises_naming_test_side() -> None:
    df = pd.DataFrame(
        {
            "tpep_pickup_datetime": [
                SPLIT_TIMESTAMP - pd.Timedelta(2, unit="D"),
                SPLIT_TIMESTAMP - pd.Timedelta(1, unit="D"),
            ],
            "row_id": [0, 1],
        }
    )

    with pytest.raises(ValueError, match="test"):
        chronological_split(df)


def test_chronological_split_all_after_boundary_raises_naming_train_side() -> None:
    df = pd.DataFrame(
        {
            "tpep_pickup_datetime": [
                SPLIT_TIMESTAMP + pd.Timedelta(1, unit="D"),
                SPLIT_TIMESTAMP + pd.Timedelta(2, unit="D"),
            ],
            "row_id": [0, 1],
        }
    )

    with pytest.raises(ValueError, match="train"):
        chronological_split(df)


def test_chronological_split_empty_input_raises() -> None:
    df = pd.DataFrame({"tpep_pickup_datetime": pd.Series([], dtype="datetime64[ns]"), "row_id": []})

    with pytest.raises(ValueError):
        chronological_split(df)


def test_split_timestamp_is_inside_pinned_window_and_on_or_after_march_2020() -> None:
    assert TLC_START_MONTH < "2020-03" <= TLC_END_MONTH
    assert SPLIT_TIMESTAMP.year == 2020
    assert SPLIT_TIMESTAMP.month == 3


def test_chronological_split_docstring_states_half_open_boundary() -> None:
    assert chronological_split.__doc__ is not None
    assert "half-open" in chronological_split.__doc__ or "half open" in chronological_split.__doc__


def _synthetic_feature_frame(n: int) -> pd.DataFrame:
    """A 60-row synthetic feature frame built from lib.features' own column contract."""
    rng = np.random.default_rng(0)
    data = {
        "PULocationID": rng.integers(1, 264, size=n),
        "DOLocationID": rng.integers(1, 264, size=n),
        "VendorID": rng.integers(1, 3, size=n),
        "passenger_count": rng.integers(1, 5, size=n).astype(float),
        "trip_distance": rng.uniform(0.1, 20.0, size=n),
        "trip_distance_km": rng.uniform(0.1, 30.0, size=n),
        "pickup_hour": rng.integers(0, 24, size=n),
        "pickup_dayofweek": rng.integers(0, 7, size=n),
    }
    x = pd.DataFrame(data)[FEATURE_COLUMNS]
    y = pd.Series(rng.uniform(60.0, 3600.0, size=n), name=TARGET_COLUMN)
    return x, y


def test_train_trip_duration_model_predicts_one_finite_value_per_row() -> None:
    x, y = _synthetic_feature_frame(60)

    # train_trip_duration_model casts categorical columns on x in place, and
    # predict-time frames must carry that same dtype forward (see its
    # docstring), so predict against the same x object used to fit.
    model = train_trip_duration_model(x, y)
    predictions = model.predict(x)

    assert len(predictions) == len(x)
    assert np.all(np.isfinite(predictions))


def test_train_trip_duration_model_is_deterministic() -> None:
    x_a, y = _synthetic_feature_frame(60)
    x_b, _ = _synthetic_feature_frame(60)

    model_a = train_trip_duration_model(x_a, y)
    model_b = train_trip_duration_model(x_b, y)
    preds_a = model_a.predict(x_a)
    preds_b = model_b.predict(x_b)

    np.testing.assert_array_equal(preds_a, preds_b)


def test_zone_category_dtype_enumerates_all_263_zones() -> None:
    assert len(ZONE_CATEGORY_DTYPE.categories) == 263
    assert list(ZONE_CATEGORY_DTYPE.categories)[0] == 1
    assert list(ZONE_CATEGORY_DTYPE.categories)[-1] == 263


def test_unseen_zone_scores_without_becoming_missing() -> None:
    x, y = _synthetic_feature_frame(60)
    # A zone within the valid 1-263 range that never appears in the training rows.
    unseen_zone = int(x["PULocationID"].max()) % 263 + 1
    while unseen_zone in set(x["PULocationID"]):
        unseen_zone = unseen_zone % 263 + 1

    model = train_trip_duration_model(x, y)

    # x's PULocationID is now ZONE_CATEGORY_DTYPE (cast in place by train), so
    # assigning a category-valid-but-unseen-in-training value stays a real
    # category rather than becoming NaN.
    predict_x = x.copy()
    predict_x.loc[predict_x.index[0], "PULocationID"] = unseen_zone
    prediction = model.predict(predict_x)

    assert np.isfinite(prediction[0])
    assert not pd.isna(predict_x["PULocationID"].iloc[0])


def test_lgbm_params_contains_random_state_and_is_stable_across_imports() -> None:
    assert "random_state" in LGBM_PARAMS
    from lib.train import LGBM_PARAMS as reimported

    assert reimported == LGBM_PARAMS


def test_save_model_then_load_booster_round_trips_predictions(tmp_path: Path) -> None:
    x, y = _synthetic_feature_frame(60)
    model = train_trip_duration_model(x, y)
    in_memory_preds = model.predict(x)

    model_path = tmp_path / "nested" / "model.txt"
    save_model(model, model_path)
    booster = load_booster(model_path)
    reloaded_preds = booster.predict(x)

    np.testing.assert_allclose(in_memory_preds, reloaded_preds)


def test_save_model_writes_lightgbm_text_format_not_pickle(tmp_path: Path) -> None:
    x, y = _synthetic_feature_frame(60)
    model = train_trip_duration_model(x.copy(), y)
    model_path = tmp_path / "model.txt"

    save_model(model, model_path)

    with open(model_path, "rb") as f:
        first_bytes = f.read(20)
    assert first_bytes[:1] != b"\x80"  # pickle protocol marker
    first_line = first_bytes.decode("ascii", errors="strict")
    assert "tree" in first_line.lower() or "version" in first_line.lower()


def test_load_booster_raises_file_not_found_on_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_booster(tmp_path / "does_not_exist.txt")
