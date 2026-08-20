"""pandera schema validation for the trip-record ingest boundary (REQ-C1 / D-09)."""

import pandas as pd
import pandera.pandas as pa

VALID_ZONE_MIN = 1
VALID_ZONE_MAX = 263
# TLC's lookup CSV lists 265 LocationIDs, but the taxi_zones shapefile only
# has 263 polygons: 264 ("Unknown") and 265 ("Outside of NYC") are real,
# documented placeholder pseudo-zones with no geometry, so no centroid/
# distance can ever be computed for them (RESEARCH.md Pitfall 3). D-09a's
# row-level pre-filter (lib.ingest.filter_trip_quality) drops and counts
# these before a frame ever reaches this schema; VALID_ZONE_MAX therefore
# stops at 263, and PLACEHOLDER_ZONE_IDS is shared with lib.ingest so the two
# tiers cannot silently drift apart.
PLACEHOLDER_ZONE_IDS = frozenset({264, 265})

PASSENGER_COUNT_MIN = 1
PASSENGER_COUNT_MAX = 6

# D-09a two-tier design: lib.ingest.filter_trip_quality pre-filters and counts
# the routine row-level numeric noise every real TLC month has (non-positive
# trip_distance/duration, placeholder zone IDs — RESEARCH.md Pitfall 6 measured
# ~1% baseline rates) BEFORE a frame reaches this schema. By the time
# validate_trips runs, a well-formed month should never trip these Checks —
# they stay real Checks (not removed) precisely so a genuine regression
# upstream (a filter bug, a bypassed ingest path) or true structural drift
# still fails loudly here rather than the schema degrading into a dtype-only
# passthrough that would pass a corrupt month while still looking like
# validation in the diff.
trip_schema = pa.DataFrameSchema(
    columns={
        "tpep_pickup_datetime": pa.Column("datetime64[ns]", nullable=False),
        "tpep_dropoff_datetime": pa.Column("datetime64[ns]", nullable=False),
        "PULocationID": pa.Column(
            int, pa.Check.in_range(VALID_ZONE_MIN, VALID_ZONE_MAX), nullable=False
        ),
        "DOLocationID": pa.Column(
            int, pa.Check.in_range(VALID_ZONE_MIN, VALID_ZONE_MAX), nullable=False
        ),
        "trip_distance": pa.Column(float, pa.Check.gt(0), nullable=False),
        "trip_duration_s": pa.Column(float, pa.Check.gt(0), nullable=False),
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
    """Validate df against trip_schema, letting pandera's own error class propagate.

    Expects a frame that has already been through lib.ingest.filter_trip_quality
    (and lib.ingest.add_trip_duration, so trip_duration_s exists). A failure
    here means genuine structural drift — a missing/renamed column, a wrong
    dtype, or a zone ID outside [VALID_ZONE_MIN, VALID_ZONE_MAX] beyond the
    known 264/265 placeholder case — not routine per-row noise, which is the
    D-09a tier boundary in one sentence.
    """
    return trip_schema.validate(df, lazy=True)
