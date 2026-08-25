"""Compile train_pipeline with a real image tag and submit it to the KFP API.

Mirrors pipelines/compile.py's own Compiler().compile(...) call so a submitted
run and CI's released YAML cannot diverge, and refuses to submit against the
unpublished "dev" placeholder tag (components.IMAGE_TAG's default) so a
mis-wired submission fails loudly here instead of several minutes into a run
via a confusing image-pull failure.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# The unpublished placeholder components.IMAGE_TAG falls back to when
# COMPONENT_IMAGE_TAG is unset - kept in sync with components/__init__.py's
# own IMAGE_TAG default rather than importing it (importing components here
# would bind IMAGE_TAG before this script gets a chance to set the env var).
_PLACEHOLDER_IMAGE_TAG = "dev"

_DEFAULT_KFP_HOST = "http://localhost:8888"
_DEFAULT_EXPERIMENT = "nyc-trip-duration-backfill"
_COMPILED_PACKAGE_PATH = Path("dist/train_pipeline.yaml")


def _current_git_sha() -> str:
    """Return the current commit's full SHA via `git rev-parse HEAD`."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile and submit train_pipeline to a running KFP instance."
    )
    parser.add_argument("--start-month", default="2020-02", help="YYYY-MM (default: %(default)s)")
    parser.add_argument("--end-month", default="2020-04", help="YYYY-MM (default: %(default)s)")
    parser.add_argument(
        "--features-version", default="v1", help="Backfill artifact version (default: %(default)s)"
    )
    parser.add_argument(
        "--model-name", default="nyc-trip-duration", help="MLflow registered model name"
    )
    parser.add_argument(
        "--experiment",
        default=_DEFAULT_EXPERIMENT,
        help=f"KFP experiment name (default: {_DEFAULT_EXPERIMENT})",
    )
    parser.add_argument(
        "--image-tag",
        default=None,
        help="Component image tag to submit against (default: `git rev-parse HEAD`)",
    )
    parser.add_argument(
        "--kfp-host",
        default=_DEFAULT_KFP_HOST,
        help=f"KFP API host, normally a port-forwarded endpoint (default: {_DEFAULT_KFP_HOST})",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable KFP per-run caching so every task actually re-executes",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    image_tag = args.image_tag or _current_git_sha()
    if image_tag == _PLACEHOLDER_IMAGE_TAG:
        print(
            f"REFUSED: --image-tag resolved to the unpublished placeholder "
            f"{_PLACEHOLDER_IMAGE_TAG!r}. Pass a real published image tag "
            f"(normally a git SHA CI has built and pushed to GHCR) - submitting "
            f"the placeholder would fail with a confusing image-pull error "
            f"several minutes into the run instead of at submit time.",
            file=sys.stderr,
        )
        return 1

    # COMPONENT_IMAGE_TAG must be set BEFORE importing anything under
    # components/ or pipelines/: components.IMAGE_TAG (and therefore every
    # component's image reference) is bound at import time, not call time.
    import os

    os.environ["COMPONENT_IMAGE_TAG"] = image_tag

    from kfp.client import Client
    from kfp.compiler import Compiler

    from pipelines.train_pipeline import train_pipeline

    _COMPILED_PACKAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # The exact same call pipelines/compile.py's main() makes, against the
    # exact same train_pipeline object, so a submitted run and CI's released
    # YAML are built by identical code - the only variable is COMPONENT_IMAGE_TAG.
    Compiler().compile(pipeline_func=train_pipeline, package_path=str(_COMPILED_PACKAGE_PATH))
    print(f"compiled {_COMPILED_PACKAGE_PATH} at image tag {image_tag}")

    client = Client(host=args.kfp_host)
    run_name = f"backfill-{args.start_month}-{args.end_month}-{image_tag[:12]}"
    result = client.create_run_from_pipeline_package(
        pipeline_file=str(_COMPILED_PACKAGE_PATH),
        arguments={
            "start_month": args.start_month,
            "end_month": args.end_month,
            "features_version": args.features_version,
            "model_name": args.model_name,
        },
        run_name=run_name,
        experiment_name=args.experiment,
        enable_caching=not args.no_cache,
    )

    print(f"run_id={result.run_id}")
    print(f"run_url={args.kfp_host}/#/runs/details/{result.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
