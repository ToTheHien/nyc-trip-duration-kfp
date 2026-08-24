"""Shared component-image reference helper.

Lives here (not in pipelines/) so components/ stays free of any import from
pipelines/ - components/ never imports the pipeline definition, matching the
one-directional lib/ <- components/ <- pipelines/ boundary ARCHITECTURE.md
documents.
"""

import os

IMAGE_REGISTRY = "ghcr.io/tothehien/nyc-trip-duration-kfp"
# CI and the submit script always export the git SHA via COMPONENT_IMAGE_TAG;
# "dev" is a deliberately unpublished placeholder so a mis-wired compile
# fails loudly at image pull rather than silently running stale code
# (PITFALLS.md Pitfall 6: a mutable image reference breaks KFP's cache-key
# semantics).
IMAGE_TAG = os.environ.get("COMPONENT_IMAGE_TAG", "dev")


def image_for(name: str) -> str:
    """Return the full GHCR image reference for component `name` at IMAGE_TAG."""
    return f"{IMAGE_REGISTRY}/{name}:{IMAGE_TAG}"
