"""Month-range enumeration for backfill windows."""

import re

_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")


def _parse_month(value: str) -> tuple[int, int]:
    match = _MONTH_PATTERN.match(value)
    if match is None:
        raise ValueError(f"expected a 'YYYY-MM' month string, got {value!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"month must be in 01-12, got {value!r}")
    return year, month


def month_range(start_month: str, end_month: str) -> list[str]:
    """Return the ascending list of 'YYYY-MM' strings, inclusive of both endpoints."""
    start_year, start_month_num = _parse_month(start_month)
    end_year, end_month_num = _parse_month(end_month)
    if (end_year, end_month_num) < (start_year, start_month_num):
        raise ValueError(f"end_month {end_month!r} sorts before start_month {start_month!r}")

    suffix: int = ""
    months: list[str] = []
    year, month = start_year, start_month_num
    while (year, month) <= (end_year, end_month_num):
        months.append(f"{year:04d}-{month:02d}" + suffix)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months
