FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ARG SOURCE=""
ARG REVISION=""
LABEL org.opencontainers.image.source=${SOURCE}
LABEL org.opencontainers.image.revision=${REVISION}

WORKDIR /app

# LightGBM's compiled extension dynamically links libgomp (OpenMP), which
# python:3.12-slim does not ship - lib.evaluate imports lightgbm at module
# level, so lib.artifacts (and therefore this component) fails to import at
# all without it. Discovered by locally running this image and reproducing
# the exact `import lib.artifacts` this component's runtime performs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Pin uv to this repo's dev-machine version (confirmed via `uv --version`)
# via the official distroless binary image, rather than a curl-based
# installer script.
COPY --from=ghcr.io/astral-sh/uv:0.11.0 /uv /usr/local/bin/uv

# Export the locked ml+pipeline dependency set and install it at build time -
# kfp must be present in the image so KFP's function-component bootstrap
# resolves it locally instead of reaching PyPI at pod start (REQ-B3: no
# packages_to_install / runtime dependency installation).
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --format requirements.txt --extra ml --extra pipeline \
        --no-dev --no-emit-project -o requirements.txt \
    && uv pip install --system --no-cache -r requirements.txt \
    && rm requirements.txt

COPY lib/ /app/lib/
COPY components/__init__.py /app/components/__init__.py
COPY components/features/__init__.py /app/components/features/__init__.py
COPY components/features/component.py /app/components/features/component.py
# lib.features.ZONE_CENTROID_PATH resolves to /app/data/zone_centroids.csv
# (Path(__file__).resolve().parent.parent / "data" / "zone_centroids.csv") -
# a small static lookup table, not per-run generated data, so it is safe and
# correct to bake into the image rather than fetch at runtime. Its absence
# was never caught before plan 03-04 Task 3's first real cluster run: every
# earlier compile-only/unit-test check ran against the host checkout, where
# the file is simply present on disk at the same relative path.
COPY data/zone_centroids.csv /app/data/zone_centroids.csv
ENV PYTHONPATH=/app
