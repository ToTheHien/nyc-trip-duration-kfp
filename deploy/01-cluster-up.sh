#!/usr/bin/env bash
# D-10: attempt the k3d cluster bring-up directly, time-boxed. Installs k3d
# (no sudo, pinned release) and creates the single-node "mlops" cluster this
# phase's KFP standalone install and pipeline runs execute against.
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

BIN_DIR="$REPO_ROOT/.deploy-bin"
mkdir -p "$BIN_DIR"
export PATH="$BIN_DIR:$PATH"

K3D_VERSION="v5.9.0"
CLUSTER_NAME="mlops"
# k3d's memory flag sets a Docker `--memory` cap on the k3s server
# container, but that cap is advisory, not an enforced cgroup limit that
# guarantees the node can't be pushed into OOM territory under real
# pressure (PITFALLS.md Pitfall 1). The actual protection against RAM
# exhaustion is the dsl.ParallelFor concurrency cap and the per-task
# resources.requests/limits already compiled into
# pipelines/train_pipeline.py - this flag is a coarse budget, not the
# safety net.
# k3d passes this straight through to Docker's `--memory` flag ("[From
# docker]" per `k3d cluster create --help"), which parses Docker's own unit
# suffixes (b/k/m/g), not Kubernetes' Gi/Mi resource-quantity suffixes - a
# "10Gi" value is rejected at cluster-create time with "invalid suffix:
# 'gi'" (confirmed empirically this run).
SERVERS_MEMORY="10g"

if ! command -v k3d >/dev/null 2>&1; then
  echo "k3d not found on PATH - installing ${K3D_VERSION} into ${BIN_DIR} (no sudo)"
  INSTALLER="$(mktemp)"
  curl -fsSL -o "$INSTALLER" https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh
  # Read before executing - never pipe a network response straight into a
  # shell (threat model T-03-11).
  if ! grep -q 'K3D_INSTALL_DIR' "$INSTALLER"; then
    echo "REFUSED: downloaded k3d installer no longer honours K3D_INSTALL_DIR - inspect $INSTALLER by hand before proceeding." >&2
    rm -f "$INSTALLER"
    exit 1
  fi
  USE_SUDO=false K3D_INSTALL_DIR="$BIN_DIR" TAG="$K3D_VERSION" bash "$INSTALLER"
  rm -f "$INSTALLER"
fi

command -v k3d >/dev/null 2>&1 || {
  echo "REFUSED: k3d install did not produce a usable binary on PATH" >&2
  exit 1
}
echo "k3d version: $(k3d version)"

if k3d cluster list "$CLUSTER_NAME" >/dev/null 2>&1; then
  echo "k3d cluster '${CLUSTER_NAME}' already exists - skipping create (script is safe to re-run)"
else
  echo "Creating k3d cluster '${CLUSTER_NAME}' (1 server, 0 agents, ${SERVERS_MEMORY} advisory memory budget)"
  # No local registry: component images come from public GHCR, so a local
  # registry is one more moving part with no purpose in this project.
  k3d cluster create "$CLUSTER_NAME" \
    --servers 1 --agents 0 \
    --servers-memory "$SERVERS_MEMORY" \
    --wait
fi

echo "Verifying node readiness..."
if ! kubectl get nodes --no-headers | grep -qE '\bReady\b'; then
  echo "REFUSED: no k3d node reports Ready" >&2
  kubectl get nodes >&2
  exit 1
fi

kubectl get nodes
echo "k3d cluster '${CLUSTER_NAME}' is up."
