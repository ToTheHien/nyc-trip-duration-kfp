"""The merge KFP component: dsl.Collected per-month Datasets -> one merged Dataset.

The Collected consumer never sorts or indexes parts itself - ordering is
lib.artifacts.merge_feature_parquets's responsibility, deliberately, so a
single tested function owns it (REQ-B8 prerequisite: the merged row order is
independent of the order dsl.Collected returns per-month artifacts).
"""

from kfp import dsl
from kfp.dsl import Dataset, Input, Output

from components import image_for


@dsl.component(base_image=image_for("merge"))
def merge_features(parts: Input[list[Dataset]], merged: Output[Dataset]) -> None:
    from pathlib import Path

    from lib.artifacts import merge_feature_parquets

    in_paths = [Path(part.path) for part in parts]
    n_rows = merge_feature_parquets(in_paths, Path(merged.path))
    merged.metadata["n_rows"] = n_rows
    merged.metadata["n_parts"] = len(in_paths)
