"""Precompute the D-06 zone-centroid lookup table from TLC's public taxi-zone shapefile.

One-time, maintainer-run script: downloads TLC's taxi_zones.zip, reprojects its
EPSG:2263 (US survey feet) polygon vertices to EPSG:4326 (lat/lon degrees), and
writes an area-weighted centroid per zone to data/zone_centroids.csv. That
committed CSV is what lib.features.load_zone_centroids reads at runtime; this
script's pyshp/pyproj dependencies never ship to the runtime path.
"""

import argparse
import csv
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import shapefile
from pyproj import Transformer

# Verified this session (02-RESEARCH.md Pitfall 1): the widely-cited legacy
# direct-S3 host answers HTTP 403. This CloudFront host is the only one that
# actually serves the data.
DEFAULT_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "zone_centroids.csv"
REQUEST_TIMEOUT_S = 60.0
CHUNK_SIZE_BYTES = 1024 * 1024

# taxi_zones.shp's .prj declares NAD83 State Plane New York Long Island in US
# survey feet (EPSG:2263) — read directly and verified this session. Every
# raw shapefile vertex must pass through this before it means degrees.
_TRANSFORMER = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)

EXPECTED_SHAPE_COUNT = 263
LAT_BOUNDS = (40.4, 41.1)
LON_BOUNDS = (-74.30, -73.65)
NEWARK_ZONE_ID = 1
NEWARK_LAT = 40.6918
NEWARK_LON = -74.174
NEWARK_TOLERANCE_DEG = 0.01


def _download(url: str, dest_path: Path, timeout: float) -> int:
    """Stream a URL's response body to dest_path. Returns byte count."""
    request = urllib.request.Request(url)
    byte_count = 0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise urllib.error.HTTPError(
                url, response.status, "non-200 status", response.headers, None
            )
        with dest_path.open("wb") as handle:
            while True:
                chunk = response.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                handle.write(chunk)
                byte_count += len(chunk)
    return byte_count


def _extract_zip_safely(zip_path: Path, dest_dir: Path) -> None:
    """Extract zip_path into dest_dir, refusing any member that could escape it (T-02-03)."""
    resolved_dest = dest_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if Path(info.filename).is_absolute():
                raise ValueError(f"refusing to extract absolute-path member: {info.filename!r}")
            is_symlink = (info.external_attr >> 16) & 0o170000 == 0o120000
            if is_symlink:
                raise ValueError(f"refusing to extract symlink member: {info.filename!r}")
            resolved_member = (dest_dir / info.filename).resolve()
            if resolved_member != resolved_dest and resolved_dest not in resolved_member.parents:
                raise ValueError(f"refusing to extract member outside dest dir: {info.filename!r}")
        archive.extractall(dest_dir)


def _ring_centroid(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Shoelace-based area-weighted centroid of one polygon ring. Returns (cx, cy, signed_area)."""
    n = len(points)
    signed_area = cx = cy = 0.0
    for i in range(n - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        cross = x0 * y1 - x1 * y0
        signed_area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    signed_area *= 0.5
    if signed_area == 0:
        xs, ys = zip(*points, strict=True)
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    return cx / (6 * signed_area), cy / (6 * signed_area), signed_area


def _zone_centroid_lonlat(
    points: list[tuple[float, float]], parts: list[int]
) -> tuple[float, float]:
    """Area-weighted centroid across a shape's parts (23/263 zones are multi-part)."""
    ring_bounds = [*parts, len(points)]
    weighted_x = weighted_y = total_area = 0.0
    for start, end in zip(ring_bounds, ring_bounds[1:], strict=False):
        cx, cy, area = _ring_centroid(points[start:end])
        weight = abs(area)
        weighted_x += cx * weight
        weighted_y += cy * weight
        total_area += weight
    x_ft, y_ft = weighted_x / total_area, weighted_y / total_area
    lon, lat = _TRANSFORMER.transform(x_ft, y_ft)
    return lon, lat


def _read_zone_centroids(shp_path: Path) -> dict[int, tuple[float, float]]:
    """Read every zone's (lat, lon) centroid from a taxi_zones.shp, keyed by LocationID."""
    reader = shapefile.Reader(str(shp_path))
    field_names = [field[0] for field in reader.fields[1:]]  # [0] is the deletion-flag pseudo-field
    location_id_index = field_names.index("LocationID")

    centroids: dict[int, tuple[float, float]] = {}
    for shape_record in reader.iterShapeRecords():
        zone_id = int(shape_record.record[location_id_index])
        lon, lat = _zone_centroid_lonlat(shape_record.shape.points, shape_record.shape.parts)
        centroids[zone_id] = (lat, lon)
    return centroids


def _validate_centroids(centroids: dict[int, tuple[float, float]]) -> None:
    """Fail loudly if the shape count or coordinate sanity checks don't hold."""
    if len(centroids) != EXPECTED_SHAPE_COUNT:
        raise ValueError(
            f"expected {EXPECTED_SHAPE_COUNT} shapes, got {len(centroids)} — "
            "refusing to write a centroid file for an unexpected shapefile"
        )

    lat_min, lat_max = LAT_BOUNDS
    lon_min, lon_max = LON_BOUNDS
    for zone_id, (lat, lon) in centroids.items():
        if not (lat_min <= lat <= lat_max) or not (lon_min <= lon <= lon_max):
            raise ValueError(
                f"zone {zone_id} centroid ({lat}, {lon}) falls outside the NYC "
                f"bounding box lat={LAT_BOUNDS} lon={LON_BOUNDS}"
            )

    newark_lat, newark_lon = centroids[NEWARK_ZONE_ID]
    if (
        abs(newark_lat - NEWARK_LAT) > NEWARK_TOLERANCE_DEG
        or abs(newark_lon - NEWARK_LON) > NEWARK_TOLERANCE_DEG
    ):
        raise ValueError(
            f"zone {NEWARK_ZONE_ID} (Newark Airport) centroid ({newark_lat}, {newark_lon}) "
            f"is not within {NEWARK_TOLERANCE_DEG} degrees of the known real-world "
            f"coordinate ({NEWARK_LAT}, {NEWARK_LON})"
        )


def _write_centroids_csv(centroids: dict[int, tuple[float, float]], out_path: Path) -> None:
    """Write the sorted, fixed-precision CSV lib.features.load_zone_centroids reads."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["zone_id", "centroid_lat", "centroid_lon"])
        for zone_id in sorted(centroids):
            lat, lon = centroids[zone_id]
            writer.writerow([zone_id, f"{lat:.6f}", f"{lon:.6f}"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Precompute the D-06 zone-centroid lookup table from TLC's taxi_zones.zip."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="taxi_zones.zip download URL")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output CSV path")
    parser.add_argument(
        "--work-dir", type=Path, default=None, help="scratch dir (default: a temp dir)"
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = args.work_dir if args.work_dir is not None else Path(tmp)
        work_dir.mkdir(parents=True, exist_ok=True)

        zip_path = work_dir / "taxi_zones.zip"
        try:
            _download(args.url, zip_path, REQUEST_TIMEOUT_S)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f"download failed: {args.url} -> {exc}", file=sys.stderr)
            return 1

        extract_dir = work_dir / "taxi_zones"
        try:
            _extract_zip_safely(zip_path, extract_dir)
        except ValueError as exc:
            print(f"unsafe archive member: {exc}", file=sys.stderr)
            return 1

        shp_candidates = list(extract_dir.rglob("taxi_zones.shp"))
        if not shp_candidates:
            print(f"taxi_zones.shp not found under {extract_dir}", file=sys.stderr)
            return 1
        shp_path = shp_candidates[0]

        centroids = _read_zone_centroids(shp_path)

        try:
            _validate_centroids(centroids)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        _write_centroids_csv(centroids, args.out)

    print(f"wrote {len(centroids)} zone centroids to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
