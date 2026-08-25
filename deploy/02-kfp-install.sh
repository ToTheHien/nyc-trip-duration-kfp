#!/usr/bin/env bash
# Install KFP standalone 2.17.0 via the env/platform-agnostic overlay (never
# env/dev - see the note below), then verify REQ-B1 and 03-RESEARCH.md
# Pitfall 9 mechanically rather than trusting a clean `kubectl apply`.
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

BIN_DIR="$REPO_ROOT/.deploy-bin"
export PATH="$BIN_DIR:$PATH"

PIPELINE_VERSION="2.17.0"

echo "Applying cluster-scoped-resources kustomization at ref=${PIPELINE_VERSION}..."
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=${PIPELINE_VERSION}"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io

# Use env/platform-agnostic, never env/dev. Despite the pinned `?ref=` only
# controlling which git tag the kustomize *manifests themselves* are read
# from, env/dev's own kustomization.yaml at 2.17.0 carries an `images:`
# override block that repoints every KFP component image to `newTag:
# master` - a floating tag that moves independently of the release you
# thought you pinned (03-RESEARCH.md Pitfall 9). env/platform-agnostic has
# no such override, so it inherits the base manifests' images pinned to
# 2.17.0 exactly.
echo "Applying env/platform-agnostic kustomization at ref=${PIPELINE_VERSION}..."
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/platform-agnostic?ref=${PIPELINE_VERSION}"

echo "Waiting for ml-pipeline pods to be ready (first-time image pulls can be slow)..."
kubectl wait pods -n kubeflow -l app=ml-pipeline --for condition=ready --timeout=600s

echo "--- Verification (the real product of this script) ---"

echo "1. Every pod in kubeflow is Running or Completed:"
kubectl get pods -n kubeflow
POD_COUNT=$(kubectl get pods -n kubeflow --no-headers | wc -l)
if [ "$POD_COUNT" -lt 1 ]; then
  echo "REFUSED: kubeflow namespace has zero pods - the install did not run, the check cannot pass vacuously." >&2
  exit 1
fi
NOT_READY=$(kubectl get pods -n kubeflow --no-headers | grep -cvE ' (Running|Completed) ' || true)
if [ "$NOT_READY" -ne 0 ]; then
  echo "REFUSED: ${NOT_READY} pod(s) in kubeflow are not Running/Completed." >&2
  exit 1
fi
echo "OK: ${POD_COUNT} pod(s) Running/Completed."

echo "2. Every ghcr.io/kubeflow/kfp-* image is pinned to :${PIPELINE_VERSION}:"
IMAGES=$(kubectl get pods -n kubeflow -o jsonpath='{.items[*].spec.containers[*].image}' | tr ' ' '\n' | grep 'ghcr.io/kubeflow/kfp' || true)
if [ -z "$IMAGES" ]; then
  echo "REFUSED: image scan returned zero ghcr.io/kubeflow/kfp images - a check with an empty scan set must not pass." >&2
  exit 1
fi
FLOATING=$(echo "$IMAGES" | grep -v ":${PIPELINE_VERSION}\$" || true)
if [ -n "$FLOATING" ]; then
  echo "REFUSED: image(s) not pinned to :${PIPELINE_VERSION}:" >&2
  echo "$FLOATING" >&2
  exit 1
fi
echo "OK: $(echo "$IMAGES" | wc -l) image(s), all pinned to :${PIPELINE_VERSION}."

echo "3. No istio-system namespace exists (REQ-B1 - KFP standalone, not the multi-user distribution):"
if kubectl get namespace istio-system >/dev/null 2>&1; then
  echo "REFUSED: istio-system namespace exists - this is not a standalone install." >&2
  exit 1
fi
echo "OK: istio-system namespace absent."

echo "KFP standalone ${PIPELINE_VERSION} is installed and verified."
