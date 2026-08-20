"""RMSE computation and champion-comparison logic for trip-duration model evaluation.

Stays free of any MLflow import so it remains testable without a client - the
champion RMSE arrives as a plain float|None argument, the seam
RESEARCH.md's Architectural Responsibility Map specifies between evaluate.py
(pure math) and registry.py (the MLflow client wrapper).
"""

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd


def rmse(y_true: pd.Series, y_pred: np.ndarray) -> float:
    """Root mean squared error between true and predicted values, as a plain float.

    Raises ValueError on a length mismatch rather than letting numpy silently
    broadcast the shorter array.
    """
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)
    if y_true_arr.shape[0] != y_pred_arr.shape[0]:
        raise ValueError(
            f"rmse requires equal-length inputs, got {y_true_arr.shape[0]} "
            f"true values and {y_pred_arr.shape[0]} predicted values"
        )
    return float(np.sqrt(np.mean((y_true_arr - y_pred_arr) ** 2)))


@dataclass(frozen=True)
class EvaluationResult:
    """RMSE plus the row count it was computed over."""

    rmse: float
    n_rows: int


def evaluate_model(
    model: lgb.LGBMRegressor, x_test: pd.DataFrame, y_test: pd.Series
) -> EvaluationResult:
    """Predict on x_test and package the RMSE alongside the row count it covers.

    The row count matters because a champion comparison computed over a
    handful of rows is not comparable to one computed over a month.
    """
    predictions = np.asarray(model.predict(x_test))
    return EvaluationResult(rmse=rmse(y_test, predictions), n_rows=len(x_test))


def beats_champion(candidate_rmse: float, champion_rmse: float | None) -> bool:
    """True if candidate_rmse should become the new champion.

    True when there is no champion yet (the first-ever run always promotes),
    and otherwise True only when candidate_rmse is strictly lower than
    champion_rmse - an exact tie leaves the incumbent in place, the
    conservative reading that avoids alias churn on a re-run of identical
    data.
    """
    if champion_rmse is None:
        return True
    return candidate_rmse < champion_rmse
