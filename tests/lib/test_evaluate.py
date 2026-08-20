"""Exact-value tests for lib.evaluate's rmse, evaluate_model, and beats_champion."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from lib.evaluate import EvaluationResult, beats_champion, evaluate_model, rmse


def test_rmse_hand_computed_pair() -> None:
    y_true = [3.0, 5.0]
    y_pred = [4.0, 5.0]

    result = rmse(y_true, y_pred)

    assert result == pytest.approx(0.7071067811865476)


def test_rmse_raises_on_length_mismatch() -> None:
    with pytest.raises(ValueError):
        rmse([1.0, 2.0, 3.0], [1.0, 2.0])


def test_evaluate_model_reports_rmse_and_row_count() -> None:
    model = MagicMock()
    model.predict.return_value = np.array([4.0, 5.0])
    x_test = pd.DataFrame({"a": [1, 2]})
    y_test = pd.Series([3.0, 5.0])

    result = evaluate_model(model, x_test, y_test)

    assert isinstance(result, EvaluationResult)
    assert result.n_rows == 2
    assert result.rmse == rmse(y_test, model.predict.return_value)


def test_beats_champion_true_when_no_champion() -> None:
    assert beats_champion(10.0, None) is True


def test_beats_champion_true_when_strictly_lower() -> None:
    assert beats_champion(10.0, 12.0) is True


def test_beats_champion_false_when_strictly_higher() -> None:
    assert beats_champion(12.0, 10.0) is False


def test_beats_champion_false_on_exact_tie() -> None:
    assert beats_champion(10.0, 10.0) is False
