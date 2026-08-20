"""RMSE computation for trip-duration model evaluation."""

import numpy as np
import pandas as pd


def rmse(y_true: pd.Series, y_pred: np.ndarray) -> float:
    """Root mean squared error between true and predicted values, as a plain float."""
    return float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2)))
