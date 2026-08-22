"""Zone-centroid haversine distance and feature-frame construction (REQ-C2 / REQ-C3).

Feature-stage output dtype contract (REQ-C3) — applied by `downcast_features`,
which `build_features` always calls before returning:

- `trip_distance`, `trip_distance_km`, `trip_duration_s`, `passenger_count`
  -> `float32`. `passenger_count` is TLC's nullable float64, never int — a
  float downcast tolerates NaN natively, an int downcast would raise on it.
- `PULocationID`, `DOLocationID` -> `ZONE_CATEGORY_DTYPE` (fixed 1-263
  categories). A zone seen only in the post-drift evaluation window must
  still score as that zone, not become missing.
- `VendorID` -> `category`. Low-cardinality, LightGBM-native categorical
  split support.
- `pickup_hour`, `pickup_dayofweek` -> `int8`. Derived, always populated,
  bounded by construction (0-23 / 0-6).
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0
ZONE_CENTROID_PATH = Path(__file__).resolve().parent.parent / "data" / "zone_centroids.csv"

# Pinned once here so lib.train and lib.evaluate never renegotiate the
# training-frame column contract independently. A tuple, not a list: module
# constants must stay immutable so two processes importing this module (e.g.
# Phase 3's per-month fan-out) can never observe or induce a shared mutation.
FEATURE_COLUMNS: tuple[str, ...] = (
    "PULocationID",
    "DOLocationID",
    "VendorID",
    "passenger_count",
    "trip_distance",
    "trip_distance_km",
    "pickup_hour",
    "pickup_dayofweek",
)
TARGET_COLUMN = "trip_duration_s"

# The full TLC zone-ID range (1-263; 264/265 are the placeholder "Unknown"/
# "Outside of NYC" pseudo-zones with no geometry, excluded here). Building the
# PULocationID/DOLocationID categorical dtype from this explicit range - not
# from whatever zones happen to appear in a given split - matters because
# LightGBM aligns pandas categories observed at fit time and treats any
# category unseen at fit time as missing at predict time; a zone that only
# appears in the post-drift evaluation window must still score as that zone.
# A CategoricalDtype instance is itself immutable, so this constant carries no
# shared mutable state despite being built from a `range`.
ZONE_CATEGORY_DTYPE = pd.CategoricalDtype(categories=list(range(1, 264)))

# downcast_features' per-column mapping, named once so the implementation and
# the module-docstring table above cannot silently drift apart.
_FLOAT32_COLUMNS = ("trip_distance", "trip_distance_km", "trip_duration_s", "passenger_count")
_INT8_COLUMNS = ("pickup_hour", "pickup_dayofweek")


def load_zone_centroids(path: Path = ZONE_CENTROID_PATH) -> pd.DataFrame:
    """Read the committed static zone-centroid lookup table (zone_id/centroid_lat/centroid_lon).

    Reads the CSV fresh on every call and returns a new frame - deliberately
    not memoised into a module-level cache. The file is 263 rows, so there is
    nothing worth caching, and a module-level mutable cache would be shared
    state that Phase 3's parallel per-month fan-out would have several
    processes touching concurrently.

    Raises FileNotFoundError naming the path if the CSV is absent (pandas'
    own read_csv already raises exactly that for a missing file).
    """
    if not path.exists():
        raise FileNotFoundError(f"zone-centroid lookup table not found at {path}")
    return pd.read_csv(path)


def haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    """Fully vectorized great-circle distance in km between two sets of (lat, lon) points.

    Entirely numpy ufuncs over whole Series - no `.apply`, no Python-level
    loop - which is the production distance path REQ-C2 exists to prove.
    """
    lat1_r, lon1_r, lat2_r, lon2_r = (np.radians(s) for s in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2.0) ** 2
    # Clamp the arcsin argument into [0.0, 1.0]: identical coordinates should
    # yield exactly 0.0 rather than NaN from a marginally-negative radicand
    # introduced by floating-point error.
    a_clamped = np.clip(a, 0.0, 1.0)
    return pd.Series(EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a_clamped)), index=lat1.index)


def haversine_km_rowwise(df: pd.DataFrame) -> pd.Series:
    """Readable row-wise haversine baseline over df's pu_lat/pu_lon/do_lat/do_lon columns.

    Implemented with `DataFrame.apply` over the four coordinate columns using
    the same math-level formula as `haversine_km`. This function exists for
    two reasons named in REQ-C2's acceptance criterion: it is the comparison
    arm scripts/benchmark_features.py measures against, and it is the test
    oracle that proves the vectorized path is the same formula, not merely
    fast. It must never be called from `build_features`.
    """

    def _row_distance(row: pd.Series) -> float:
        lat1, lon1, lat2, lon2 = (
            math.radians(row["pu_lat"]),
            math.radians(row["pu_lon"]),
            math.radians(row["do_lat"]),
            math.radians(row["do_lon"]),
        )
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        a_clamped = min(max(a, 0.0), 1.0)
        return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a_clamped))

    return df.apply(_row_distance, axis=1)


def join_zone_centroids(df: pd.DataFrame, centroids: pd.DataFrame) -> pd.DataFrame:
    """Left-join pickup and dropoff zone centroids onto df; row count is invariant.

    Two left merges of the centroid table - once keyed PULocationID -> zone_id
    producing pu_lat/pu_lon, once keyed DOLocationID -> zone_id producing
    do_lat/do_lon. Left merges (not inner) keep the row count invariant; an
    inner merge would silently drop rows on any zone-id mismatch, and that
    count change would be easy to miss. A row whose zone id has no centroid
    row gets a null coordinate here rather than being dropped - build_features
    is what turns a surviving null into a loud failure.
    """
    pu_centroids = centroids.rename(
        columns={
            "zone_id": "PULocationID",
            "centroid_lat": "pu_lat",
            "centroid_lon": "pu_lon",
        }
    )
    do_centroids = centroids.rename(
        columns={
            "zone_id": "DOLocationID",
            "centroid_lat": "do_lat",
            "centroid_lon": "do_lon",
        }
    )
    merged = df.merge(pu_centroids, on="PULocationID", how="left")
    merged = merged.merge(do_centroids, on="DOLocationID", how="left")
    return merged


def downcast_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the feature-stage dtype contract documented in the module docstring, on a copy.

    Operates on a copy throughout and leaves df's own dtypes unchanged.
    `passenger_count` is downcast via `pd.to_numeric(..., downcast="float")`
    (never an integer downcast): TLC stores it as a nullable float64, and an
    integer downcast raises on any NaN, while float32 carries NaN natively at
    no extra cost here.
    """
    result = df.copy()
    for col in _FLOAT32_COLUMNS:
        # A direct astype(np.float32), not pd.to_numeric(downcast="float"):
        # to_numeric's downcast only takes effect when the round trip through
        # the smaller dtype is exactly lossless, which real-valued continuous
        # columns (trip_distance_km, trip_duration_s, ...) essentially never
        # are - it would silently leave them at float64, nullifying REQ-C3's
        # memory-reduction claim. astype(np.float32) always downcasts and
        # handles NaN in passenger_count natively (unlike an integer downcast,
        # which is the case pd.to_numeric's NaN-safety advice was guarding
        # against - not a reason to prefer to_numeric here).
        result[col] = result[col].astype(np.float32)
    result["PULocationID"] = result["PULocationID"].astype(ZONE_CATEGORY_DTYPE)
    result["DOLocationID"] = result["DOLocationID"].astype(ZONE_CATEGORY_DTYPE)
    result["VendorID"] = result["VendorID"].astype("category")
    for col in _INT8_COLUMNS:
        result[col] = result[col].astype("int8")
    return result


def build_features(df: pd.DataFrame, centroids: pd.DataFrame) -> pd.DataFrame:
    """Join zone centroids onto pickup/dropoff zones, derive the feature frame + target.

    Pure and idempotent: operates on copies throughout (df.merge always
    returns a new frame, and downcast_features copies again), never assigns
    into the caller's df, and calling this twice on the same input returns
    equal frames. Raises ValueError naming every offending zone id if any
    row's PULocationID/DOLocationID survives the centroid join with no
    matching coordinate - plan 02-04's row-level filter already removes the
    known 264/265 placeholder zones upstream, so anything still unmapped here
    is a genuine centroid-table/trip-data inconsistency that must fail rather
    than silently emitting a null distance feature.
    """
    merged = join_zone_centroids(df, centroids)

    coord_columns = ["pu_lat", "pu_lon", "do_lat", "do_lon"]
    missing_coords = merged[coord_columns].isna().any(axis=1)
    if missing_coords.any():
        unmapped_pu = merged.loc[merged["pu_lat"].isna(), "PULocationID"].tolist()
        unmapped_do = merged.loc[merged["do_lat"].isna(), "DOLocationID"].tolist()
        unmapped_ids = sorted({*unmapped_pu, *unmapped_do})
        raise ValueError(
            f"build_features: {len(unmapped_ids)} zone id(s) have no centroid row in the "
            f"D-06 lookup table and cannot be scored: {unmapped_ids}"
        )

    merged["trip_distance_km"] = haversine_km(
        merged["pu_lat"], merged["pu_lon"], merged["do_lat"], merged["do_lon"]
    )
    merged["pickup_hour"] = merged["tpep_pickup_datetime"].dt.hour
    merged["pickup_dayofweek"] = merged["tpep_pickup_datetime"].dt.dayofweek

    downcast = downcast_features(merged)
    return downcast[[*FEATURE_COLUMNS, TARGET_COLUMN]]
