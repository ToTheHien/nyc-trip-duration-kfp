#!/usr/bin/env bash
set -uo pipefail

# Locate ourselves so every path below resolves against the repo root,
# regardless of the caller's working directory.
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# Reconcile the CLAUDE.MD-mandated local venv with CI: locally, target the
# pinned venv explicitly; under CI, leave it unset so the runner's own
# uv-managed environment (already synced by the workflow) is used.
if [ -z "${CI:-}" ]; then
  export UV_PROJECT_ENVIRONMENT="$REPO_ROOT/path/to/venv"
fi

# Build the uv invocation prefix once so no subcommand can forget the dev
# extra: `uv run` implicitly syncs the default dependency set first, and a
# bare `uv run <tool>` would prune ruff/mypy/pytest from the environment.
if [ -n "${CI:-}" ]; then
  UV_RUN=(uv run --frozen --extra dev)
else
  UV_RUN=(uv run --extra dev)
fi

case "${1:-}" in
  lint)
    "${UV_RUN[@]}" ruff check .
    ;;
  format)
    "${UV_RUN[@]}" ruff format --check .
    ;;
  typecheck)
    "${UV_RUN[@]}" mypy --strict lib
    ;;
  test)
    "${UV_RUN[@]}" pytest
    ;;
  boundary)
    echo "Running scripts/check_component_boundary.sh"
    "$REPO_ROOT/scripts/check_component_boundary.sh"
    ;;
  *)
    echo "usage: scripts/qa.sh {lint|format|typecheck|test|boundary}" >&2
    exit 2
    ;;
esac
