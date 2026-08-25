"""The features KFP component: validated Dataset -> published feature Dataset.

s3_endpoint_url must always be an in-cluster service DNS name, never a
host-forwarded address (PITFALLS.md Pitfall 7); the pipeline's default
encodes that.
"""

from kfp import dsl
from kfp.dsl import Dataset, Input, Output

from components import image_for


@dsl.component(base_image=image_for("features"))
def build_features_component(
    validated: Input[Dataset],
    month: str,
    features_version: str,
    s3_endpoint_url: str,
    features: Output[Dataset],
) -> None:
    from pathlib import Path

    from lib.artifacts import build_and_publish_features, default_s3_client

    client = default_s3_client(s3_endpoint_url)
    n_rows, backfill_key = build_and_publish_features(
        client, Path(validated.path), Path(features.path), month, features_version
    )
    features.metadata["month"] = month
    features.metadata["n_rows"] = n_rows
    features.metadata["backfill_key"] = backfill_key
