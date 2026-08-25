"""The validate KFP component: raw Dataset -> validated Dataset via lib.schemas."""

from kfp import dsl
from kfp.dsl import Dataset, Input, Output

from components import image_for


@dsl.component(base_image=image_for("validate"))
def validate(raw: Input[Dataset], validated: Output[Dataset]) -> None:
    from pathlib import Path

    from lib.artifacts import validate_parquet

    n_rows = validate_parquet(Path(raw.path), Path(validated.path))
    validated.metadata["n_rows"] = n_rows
