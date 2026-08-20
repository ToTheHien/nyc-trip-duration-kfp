"""Fixed-config LightGBM trip-duration regression training (REQ-D2)."""

from typing import Any

import lightgbm as lgb
import pandas as pd

CATEGORICAL_FEATURES = ["PULocationID", "DOLocationID", "VendorID"]

# Single fixed, documented hyperparameter set. REQ-D2 explicitly forbids any
# tuning framework or sweep code anywhere in this repo — these values are
# deliberately untuned. Typed dict[str, Any] (rather than the inferred
# dict[str, object]) so mypy accepts the **-unpack below against
# LGBMRegressor's heterogeneously-typed keyword parameters.
LGBM_PARAMS: dict[str, Any] = {
    "objective": "regression",
    "metric": "rmse",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 300,
    "random_state": 42,
    "n_jobs": 1,
    "verbose": -1,
}


def train_trip_duration_model(x: pd.DataFrame, y: pd.Series) -> lgb.LGBMRegressor:
    """Fit a fixed-config LGBMRegressor on x/y, treating CATEGORICAL_FEATURES as categorical.

    Casts the categorical columns on x in place (not a copy): LightGBM records
    the exact category set seen during fit and requires an identically-typed
    frame at predict time, so the caller's x must carry the same dtype
    forward rather than a train-only copy silently diverging from it.
    """
    for col in CATEGORICAL_FEATURES:
        x[col] = x[col].astype("category")
    model = lgb.LGBMRegressor(**LGBM_PARAMS)
    model.fit(x, y, categorical_feature=CATEGORICAL_FEATURES)
    return model
