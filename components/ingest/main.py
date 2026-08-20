"""Thin CLI wrapper around lib.months.month_range."""

import argparse
import sys

import pandas as pd

from lib.months import month_range


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the inclusive month range.")
    parser.add_argument("--start-month", required=True, help="YYYY-MM")
    parser.add_argument("--end-month", required=True, help="YYYY-MM")
    args = parser.parse_args()

    try:
        months = month_range(args.start_month, args.end_month)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    frame = pd.DataFrame({"month": months})
    for month in frame["month"]:
        print(month)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
