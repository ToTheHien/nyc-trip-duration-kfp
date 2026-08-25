"""CLI entrypoint compiling train_pipeline to versioned IR YAML for CI."""

import argparse
from pathlib import Path

from kfp.compiler import Compiler

from pipelines.train_pipeline import train_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile train_pipeline to IR YAML.")
    parser.add_argument(
        "--out", default="dist/train_pipeline.yaml", help="Output YAML path (default: %(default)s)"
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Compiler().compile(pipeline_func=train_pipeline, package_path=str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
