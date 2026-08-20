"""Zone-centroid haversine distance and feature-frame construction (REQ-C2)."""

from pathlib import Path

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0
ZONE_CENTROID_PATH = Path(__file__).resolve().parent.parent / "data" / "zone_centroids.csv"

# Pinned once here so lib.train and lib.evaluate never renegotiate the
# training-frame column contract independently.
FEATURE_COLUMNS = [
    "PULocationID",
    "DOLocationID",
    "VendorID",
    "passenger_count",
    "trip_distance",
    "trip_distance_km",
    "pickup_hour",
    "pickup_dayofweek",
]
TARGET_COLUMN = "trip_duration_s"


def load_zone_centroids(path: Path = ZONE_CENTROID_PATH) -> pd.DataFrame:
    """Read the committed static zone-centroid lookup table (zone_id/centroid_lat/centroid_lon)."""
    return pd.read_csv(path)


def haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    """Fully vectorized great-circle distance in km between two sets of (lat, lon) points."""
    lat1_r, lon1_r, lat2_r, lon2_r = (np.radians(s) for s in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2.0) ** 2
    # Clamp the arcsin argument into [0.0, 1.0]: identical coordinates should
    # yield exactly 0.0 rather than NaN from a marginally-negative radicand
    # introduced by floating-point error.
    a_clamped = np.clip(a, 0.0, 1.0)
    return pd.Series(EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a_clamped)), index=lat1.index)


def build_features(df: pd.DataFrame, centroids: pd.DataFrame) -> pd.DataFrame:
    """Join zone centroids onto pickup/dropoff zones, derive the feature frame + target."""
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

    merged["trip_distance_km"] = haversine_km(
        merged["pu_lat"], merged["pu_lon"], merged["do_lat"], merged["do_lon"]
    )
    merged["pickup_hour"] = merged["tpep_pickup_datetime"].dt.hour
    merged["pickup_dayofweek"] = merged["tpep_pickup_datetime"].dt.dayofweek

    return merged[[*FEATURE_COLUMNS, TARGET_COLUMN]]
