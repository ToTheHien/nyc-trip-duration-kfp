"""The ingest KFP component: month -> Output[Dataset] raw."""

from kfp import dsl
from kfp.dsl import Dataset, Output

from components import image_for


@dsl.component(base_image=image_for("ingest"))
def ingest(month: str, s3_endpoint_url: str, raw: Output[Dataset]) -> None:
    from pathlib import Path

    from lib.artifacts import default_s3_client, ingest_month_to_parquet

    client = default_s3_client(s3_endpoint_url)
    n_rows = ingest_month_to_parquet(client, month, Path(raw.path))
    raw.metadata["month"] = month
    raw.metadata["n_rows"] = n_rows
