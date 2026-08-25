"""Print a reproducibility table (month, key, byte size, sha256) for every
month's `features` artifact in the `backfill` bucket.

03-RESEARCH.md verified empirically, against this repository's pinned
pandas/pyarrow/lightgbm versions, that no Parquet-normalisation or
metadata-stripping step is needed before hashing - the raw bytes are hashed
directly. Refuses loudly (and prints no rows at all) if any expected key is
missing, since a partial table would silently understate a failed comparison.
"""

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import botocore.exceptions

from lib.artifacts import BACKFILL_BUCKET, artifact_key, default_s3_client
from lib.months import month_range


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print sha256 + byte size for every month's backfill features key."
    )
    parser.add_argument("--start-month", required=True, help="YYYY-MM")
    parser.add_argument("--end-month", required=True, help="YYYY-MM")
    parser.add_argument(
        "--features-version", default="v1", help="Backfill artifact version (default: %(default)s)"
    )
    parser.add_argument(
        "--endpoint-url",
        required=True,
        help="S3-compatible endpoint URL for the MinIO instance holding the backfill bucket",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="Optional path to also write the table as markdown"
    )
    return parser.parse_args()


def _object_exists(client: Any, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except botocore.exceptions.ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey"):
            return False
        raise
    return True


def _sha256_of_object(client: Any, bucket: str, key: str) -> tuple[int, str]:
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    return len(body), hashlib.sha256(body).hexdigest()


def main() -> int:
    args = _parse_args()

    try:
        months = month_range(args.start_month, args.end_month)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    client = default_s3_client(args.endpoint_url)
    keys = [(month, artifact_key(month, "features", args.features_version)) for month in months]

    missing = [key for _month, key in keys if not _object_exists(client, BACKFILL_BUCKET, key)]
    if missing:
        print(
            f"REFUSED: {len(missing)} expected key(s) missing from bucket "
            f"'{BACKFILL_BUCKET}': {missing}. Printing no partial table - a partial "
            f"table would silently understate a failed comparison.",
            file=sys.stderr,
        )
        return 1

    rows: list[tuple[str, str, int, str]] = []
    for month, key in keys:
        byte_size, digest = _sha256_of_object(client, BACKFILL_BUCKET, key)
        rows.append((month, key, byte_size, digest))

    header = f"{'month':<10} {'key':<30} {'bytes':>12} {'sha256':<64}"
    print(header)
    for month, key, byte_size, digest in rows:
        print(f"{month:<10} {key:<30} {byte_size:>12} {digest:<64}")

    if args.out is not None:
        lines = [
            "| month | key | bytes | sha256 |",
            "|---|---|---|---|",
        ]
        for month, key, byte_size, digest in rows:
            lines.append(f"| {month} | {key} | {byte_size} | {digest} |")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote markdown table to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
