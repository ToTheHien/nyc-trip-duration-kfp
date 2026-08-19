"""Exact-value tests for lib.months.month_range."""

import pytest

from lib.months import month_range


def test_month_range_crosses_year_boundary() -> None:
    assert month_range("2019-11", "2020-02") == [
        "2019-11",
        "2019-12",
        "2020-01",
        "2020-02",
    ]


def test_month_range_single_month() -> None:
    assert month_range("2019-05", "2019-05") == ["2019-05"]


def test_month_range_full_year() -> None:
    result = month_range("2019-01", "2019-12")
    assert len(result) == 12
    assert result == [
        "2019-01",
        "2019-02",
        "2019-03",
        "2019-04",
        "2019-05",
        "2019-06",
        "2019-07",
        "2019-08",
        "2019-09",
        "2019-10",
        "2019-11",
        "2019-12",
    ]


def test_month_range_rejects_month_out_of_range() -> None:
    with pytest.raises(ValueError):
        month_range("2019-13", "2019-14")


def test_month_range_rejects_unpadded_month() -> None:
    with pytest.raises(ValueError):
        month_range("2019-5", "2019-06")


def test_month_range_rejects_end_before_start() -> None:
    with pytest.raises(ValueError):
        month_range("2020-02", "2019-11")
