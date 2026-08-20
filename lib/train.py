"""Fixed-config LightGBM trip-duration regression training (REQ-D2) and the
D-08 chronological train/test split."""

from pathlib import Path
from typing import Any

import lightgbm as lgb
import pandas as pd

from lib.features import ZONE_CATEGORY_DTYPE

# REQ-D1/D-08: the pinned 12-month window (lib.ingest.TLC_START_MONTH /
# TLC_END_MONTH = 2019-07 / 2020-06) runs across the March-2020 COVID demand
# collapse. This boundary puts the eight pre-collapse months (2019-07 through
# 2020-02) in training and the four COVID-affected months (2020-03 through
# 2020-06) in evaluation - the drift demonstration REQ-D1 and D-08 exist to
# produce. A random split would average across the collapse and hide exactly
# this signal, which is why D-08 requires a chronological split instead.
SPLIT_TIMESTAMP = pd.Timestamp("2020-03-01")

CATEGORICAL_FEATURES = ["PULocationID", "DOLocationID", "VendorID"]

# Single fixed, documented hyperparameter set. REQ-D2 explicitly forbids any
# tuning framework or sweep code anywhere in this repo - these values are
# deliberately untuned. Typed dict[str, Any] (rather than the inferred
# dict[str, object]) so mypy accepts the **-unpack below against
# LGBMRegressor's heterogeneously-typed keyword parameters.
LGBM_PARAMS: dict[str, Any] = {
    "objective": "regression",  # states the loss explicitly rather than relying on defaults
    "metric": "rmse",  # the metric this project evaluates and reports on
    "num_leaves": 31,  # LightGBM's own documented default - left alone deliberately
    "learning_rate": 0.05,  # conventional slow-and-steady pairing with n_estimators=300
    "n_estimators": 300,  # conventional slow-and-steady pairing with learning_rate=0.05
    "random_state": 42,  # fixes the seed so runs are byte-reproducible
    "n_jobs": 1,  # single-threaded: required for byte-reproducible determinism
    "deterministic": True,  # LightGBM's own deterministic-mode flag, pairs with n_jobs=1
    "verbose": -1,  # keeps test suite output readable
}


def chronological_split(
    df: pd.DataFrame, split_ts: pd.Timestamp = SPLIT_TIMESTAMP
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partition df into (train, test) by each row's own tpep_pickup_datetime value.

    The boundary is half-open: a row whose tpep_pickup_datetime is strictly
    before split_ts is training, and a row at or after split_ts (including an
    exact tie) is test. Partitioning happens on each row's own timestamp
    value, never on which source file/month the row came from - some TLC
    monthly files contain rows whose pickup timestamp falls years outside
    their nominal month, and splitting by file would leak those rows into the
    wrong side. Input row order is preserved in each returned partition;
    both are copies, so the caller's frame is left untouched.

    Raises ValueError naming the empty side if either partition would be
    empty (including when df itself is empty) - an empty partition here is
    always a configuration error, and failing here is far more legible than
    the opaque error a downstream LightGBM fit would raise on an empty frame.
    """
    train_mask = df["tpep_pickup_datetime"] < split_ts
    train = df.loc[train_mask].copy()
    test = df.loc[~train_mask].copy()

    if len(train) == 0:
        raise ValueError(
            f"chronological_split produced an empty train side: every row's "
            f"tpep_pickup_datetime is on or after split_ts={split_ts!r}"
        )
    if len(test) == 0:
        raise ValueError(
            f"chronological_split produced an empty test side: every row's "
            f"tpep_pickup_datetime is strictly before split_ts={split_ts!r}"
        )
    return train, test


def train_trip_duration_model(x: pd.DataFrame, y: pd.Series) -> lgb.LGBMRegressor:
    """Fit a fixed-config LGBMRegressor on x/y, treating CATEGORICAL_FEATURES as categorical.

    Casts the categorical columns on x in place (not a copy): LightGBM records
    the exact category set seen during fit and requires an identically-typed
    frame at predict time, so the caller's x must carry the same dtype
    forward rather than a train-only copy silently diverging from it. The
    PULocationID/DOLocationID columns are cast against ZONE_CATEGORY_DTYPE's
    explicit 1-263 category range (not whatever zones are present in x) so a
    zone seen only outside the training split still scores as that zone
    rather than becoming a missing value.
    """
    for col in ("PULocationID", "DOLocationID"):
        x[col] = x[col].astype(ZONE_CATEGORY_DTYPE)
    for col in CATEGORICAL_FEATURES:
        if col not in ("PULocationID", "DOLocationID"):
            x[col] = x[col].astype("category")
    model = lgb.LGBMRegressor(**LGBM_PARAMS)
    model.fit(x, y, categorical_feature=CATEGORICAL_FEATURES)
    return model


def save_model(model: lgb.LGBMRegressor, path: Path) -> None:
    """Persist model through LightGBM's native text format (no object-serialization module).

    The saved artifact will later be pulled from a different service (Phase
    3's MLflow-backed registry); LightGBM's own text format carries no
    code-execution surface on load, unlike a general Python pickle/joblib
    file. Creates the parent directory if it does not exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(path))


def load_booster(path: Path) -> lgb.Booster:
    """Load a Booster from LightGBM's native text format. Raises FileNotFoundError if absent."""
    if not path.exists():
        raise FileNotFoundError(f"model file not found: {path!r}")
    return lgb.Booster(model_file=str(path))
