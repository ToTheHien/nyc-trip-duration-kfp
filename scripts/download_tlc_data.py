"""Download the D-07 pinned 12-month TLC Yellow Taxi Parquet window into a local cache."""

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

from lib.ingest import TLC_DATA_DIR, TLC_END_MONTH, TLC_START_MONTH, month_parquet_path
from lib.months import month_range

# Verified this session (02-RESEARCH.md Pitfall 1): the widely-cited legacy
# direct-S3 host answers HTTP 403. This CloudFront host is the only one that
# actually serves the data.
BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/"
REQUEST_TIMEOUT_S = 60.0
CHUNK_SIZE_BYTES = 1024 * 1024


def _stream_download(url: str, part_path: Path, timeout: float) -> int:
    """Stream a URL's response body to part_path in fixed-size chunks. Returns byte count."""
    request = urllib.request.Request(url)
    byte_count = 0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise urllib.error.HTTPError(
                url, response.status, "non-200 status", response.headers, None
            )
        with part_path.open("wb") as handle:
            while True:
                chunk = response.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                handle.write(chunk)
                byte_count += len(chunk)
    return byte_count


def _download_month(month: str, dest_dir: Path, force: bool) -> tuple[str, int]:
    """Download or skip a single month. Returns (status, bytes_on_disk); raises on hard failure."""
    dest_path = month_parquet_path(month, dest_dir)
    if dest_path.exists() and dest_path.stat().st_size > 0 and not force:
        size = dest_path.stat().st_size
        print(f"skip {month}: {dest_path} already present ({size} bytes)")
        return "skipped", size

    url = f"{BASE_URL}yellow_tripdata_{month}.parquet"
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    try:
        byte_count = _stream_download(url, part_path, REQUEST_TIMEOUT_S)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        part_path.unlink(missing_ok=True)
        raise RuntimeError(f"download failed for {month}: {url} -> {exc}") from exc

    if byte_count == 0:
        part_path.unlink(missing_ok=True)
        raise RuntimeError(f"download failed for {month}: {url} -> zero bytes received")

    # Atomic rename: an interrupted transfer never leaves a truncated file at
    # the final destination that a later run would mistake for complete.
    part_path.rename(dest_path)
    print(f"downloaded {month}: {dest_path} ({byte_count} bytes)")
    return "downloaded", byte_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the pinned 12-month TLC Yellow Taxi Parquet window."
    )
    parser.add_argument("--start-month", default=TLC_START_MONTH, help="YYYY-MM")
    parser.add_argument("--end-month", default=TLC_END_MONTH, help="YYYY-MM")
    parser.add_argument("--dest", type=Path, default=TLC_DATA_DIR, help="destination directory")
    parser.add_argument("--force", action="store_true", help="re-fetch files that already exist")
    args = parser.parse_args()

    try:
        months = month_range(args.start_month, args.end_month)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.dest.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    total_bytes = 0
    for month in months:
        try:
            status, byte_count = _download_month(month, args.dest, args.force)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        total_bytes += byte_count
        if status == "downloaded":
            downloaded += 1
        else:
            skipped += 1

    print(
        f"summary: {downloaded} downloaded, {skipped} skipped, "
        f"{total_bytes} bytes on disk under {args.dest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
