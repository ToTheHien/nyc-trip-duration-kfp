"""pandera schema validation for the trip-record ingest boundary (REQ-C1 / D-09)."""

import pandas as pd
import pandera.pandas as pa

VALID_ZONE_MIN = 1
VALID_ZONE_MAX = 263
# TLC LocationIDs 264 ("Unknown") and 265 ("Outside of NYC") are real,
# documented values with no shapefile geometry — no centroid is computable
# for them (RESEARCH.md Pitfall 3). Plan 02-04's row-level pre-filter drops
# and logs these rather than letting them fail the whole month.
PLACEHOLDER_ZONE_IDS = (264, 265)

PASSENGER_COUNT_MIN = 1
PASSENGER_COUNT_MAX = 6

# D-09a: this schema enforces structural integrity only (columns present,
# correct dtypes, zone IDs within the valid geographic range, dropoff not
# before pickup). Row-level numeric-quality noise (non-positive distance,
# non-positive duration) has a real ~1% baseline rate in every TLC month
# (RESEARCH.md Pitfall 6) and is pre-filtered-and-logged by lib.ingest before
# reaching this schema, not enforced here.
trip_schema = pa.DataFrameSchema(
    columns={
        "tpep_pickup_datetime": pa.Column("datetime64[ns]", nullable=False),
        "tpep_dropoff_datetime": pa.Column("datetime64[ns]", nullable=False),
        "PULocationID": pa.Column(int, pa.Check.in_range(VALID_ZONE_MIN, VALID_ZONE_MAX)),
        "DOLocationID": pa.Column(int, pa.Check.in_range(VALID_ZONE_MIN, VALID_ZONE_MAX)),
        "trip_distance": pa.Column(float, pa.Check.gt(0)),
        "passenger_count": pa.Column(
            float,
            pa.Check.in_range(PASSENGER_COUNT_MIN, PASSENGER_COUNT_MAX),
            nullable=True,
        ),
    },
    checks=[
        pa.Check(lambda frame: frame["tpep_dropoff_datetime"] >= frame["tpep_pickup_datetime"]),
    ],
    strict=False,  # extra columns (congestion_surcharge, airport_fee, ...) pass through unchecked
)


def validate_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Validate df against trip_schema, letting pandera's own error class propagate."""
    return trip_schema.validate(df, lazy=True)
