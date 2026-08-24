"""The train KFP component: merged Dataset -> trained LightGBM Model."""

from kfp import dsl
from kfp.dsl import Dataset, Input, Model, Output

from components import image_for


@dsl.component(base_image=image_for("train"))
def train(merged: Input[Dataset], model: Output[Model]) -> None:
    from pathlib import Path

    from lib.artifacts import train_from_parquet

    train_from_parquet(Path(merged.path), Path(model.path))
    model.metadata["framework"] = "lightgbm"
