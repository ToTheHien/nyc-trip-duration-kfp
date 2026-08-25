#!/usr/bin/env bash
# D-12: a dedicated MinIO pod plus an in-cluster MLflow (SQLite backend
# store, MinIO artifact root) in the "mlflow" namespace, with credentials
# generated (or read from the environment) and passed to Helm only by
# Kubernetes Secret reference - never as a --set argument, never echoed.
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

BIN_DIR="$REPO_ROOT/.deploy-bin"
mkdir -p "$BIN_DIR"
export PATH="$BIN_DIR:$PATH"

NAMESPACE="mlflow"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm not found on PATH - installing into ${BIN_DIR} (no sudo)"
  INSTALLER="$(mktemp)"
  curl -fsSL -o "$INSTALLER" https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
  if ! grep -q 'HELM_INSTALL_DIR' "$INSTALLER"; then
    echo "REFUSED: downloaded helm installer no longer honours HELM_INSTALL_DIR - inspect $INSTALLER by hand before proceeding." >&2
    rm -f "$INSTALLER"
    exit 1
  fi
  USE_SUDO=false HELM_INSTALL_DIR="$BIN_DIR" bash "$INSTALLER"
  rm -f "$INSTALLER"
fi
command -v helm >/dev/null 2>&1 || {
  echo "REFUSED: helm install did not produce a usable binary on PATH" >&2
  exit 1
}
echo "helm version: $(helm version --short)"

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

# --- Credentials: generated from a cryptographic random source unless
# already exported, never printed, never passed as a --set argument. ---
if [ -z "${MINIO_ROOT_USER:-}" ]; then
  MINIO_ROOT_USER="$(python3 -c 'import secrets; print("minioadmin" + secrets.token_hex(4))')"
fi
if [ -z "${MINIO_ROOT_PASSWORD:-}" ]; then
  MINIO_ROOT_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"
fi

# minio-root-creds: the MinIO chart's existingSecret schema (rootUser/rootPassword).
kubectl create secret generic minio-root-creds \
  --namespace "$NAMESPACE" \
  --from-literal=rootUser="$MINIO_ROOT_USER" \
  --from-literal=rootPassword="$MINIO_ROOT_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

# mlflow-minio-creds: AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY the S3-facing
# clients (MLflow's server, and every task pod that touches MinIO) expect.
# The MinIO root user IS the access key here - this chart has no separate
# IAM-user-provisioning step, so reusing the root credential as the S3
# access key/secret is the correct mapping, not a shortcut.
# Required in BOTH namespaces: MLflow's server pod reads it in `mlflow`,
# and KFP standalone runs pipeline task pods in `kubeflow`, where
# use_secret_as_env resolves the Secret in the task pod's own namespace. A
# Secret present in only one namespace would produce a confusing mid-run
# credential failure rather than an install-time error.
for ns in "$NAMESPACE" kubeflow; do
  kubectl create secret generic mlflow-minio-creds \
    --namespace "$ns" \
    --from-literal=AWS_ACCESS_KEY_ID="$MINIO_ROOT_USER" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD" \
    --dry-run=client -o yaml | kubectl apply -f -
done

for ns in "$NAMESPACE" kubeflow; do
  kubectl get secret mlflow-minio-creds -n "$ns" >/dev/null 2>&1 || {
    echo "REFUSED: mlflow-minio-creds did not land in namespace '${ns}'" >&2
    exit 1
  }
done
echo "OK: credentials generated/reused and stored only in Kubernetes Secrets (mlflow, kubeflow)."

# --- MinIO ---
helm repo add minio https://charts.min.io/ >/dev/null 2>&1 || true
helm repo update minio >/dev/null

echo "Installing/upgrading MinIO..."
helm upgrade --install minio minio/minio \
  --namespace "$NAMESPACE" \
  -f "$REPO_ROOT/deploy/minio-values.yaml" \
  --wait --timeout 5m

echo "Waiting for the MinIO pod to be Ready..."
kubectl wait pods -n "$NAMESPACE" -l app=minio --for condition=ready --timeout=300s

# --- MLflow ---
MLFLOW_CHART_REF="oci://ghcr.io/mlflow/charts/mlflow"
MLFLOW_CHART_VERSION="$(helm show chart "$MLFLOW_CHART_REF" 2>/dev/null | awk -F': ' '/^version:/{print $2}')"
if [ -z "$MLFLOW_CHART_VERSION" ]; then
  echo "REFUSED: could not resolve the published MLflow Helm chart version via 'helm show chart ${MLFLOW_CHART_REF}'." >&2
  exit 1
fi
echo "Resolved MLflow chart version: ${MLFLOW_CHART_VERSION}"

echo "Installing/upgrading MLflow..."
helm upgrade --install mlflow "$MLFLOW_CHART_REF" \
  --version "$MLFLOW_CHART_VERSION" \
  --namespace "$NAMESPACE" \
  -f "$REPO_ROOT/deploy/mlflow-values.yaml" \
  --wait --timeout 5m

echo "Waiting for the MLflow pod to be Ready..."
kubectl wait pods -n "$NAMESPACE" -l app.kubernetes.io/name=mlflow --for condition=ready --timeout=300s

echo "Checking MLflow logs for a SQLite permission error (03-RESEARCH.md Open Question 2)..."
if kubectl logs -n "$NAMESPACE" deploy/mlflow --tail=200 2>/dev/null | grep -qi 'unable to open database file'; then
  echo "REFUSED: MLflow cannot open its SQLite database file on the PVC - override podSecurityContext.fsGroup in deploy/mlflow-values.yaml and re-run this script." >&2
  exit 1
fi
echo "OK: no SQLite permission error in MLflow's logs."

echo "--- Verification ---"

echo "1. Both pods Ready in the mlflow namespace:"
kubectl get pods -n "$NAMESPACE"
NOT_READY=$(kubectl get pods -n "$NAMESPACE" --no-headers | grep -cvE ' (Running|Completed) ' || true)
POD_COUNT=$(kubectl get pods -n "$NAMESPACE" --no-headers | wc -l)
if [ "$POD_COUNT" -lt 2 ]; then
  echo "REFUSED: expected at least 2 pods (minio, mlflow) in namespace '${NAMESPACE}', found ${POD_COUNT}." >&2
  exit 1
fi
if [ "$NOT_READY" -ne 0 ]; then
  echo "REFUSED: ${NOT_READY} pod(s) in '${NAMESPACE}' are not Running/Completed." >&2
  exit 1
fi
echo "OK: ${POD_COUNT} pod(s) Running/Completed."

echo "2. MLflow reachable from INSIDE the cluster (never the host):"
if ! kubectl run mlflow-health-check --rm -i --restart=Never --image=curlimages/curl:8.11.1 \
  --namespace "$NAMESPACE" --command -- \
  sh -c 'curl -sf -o /dev/null -w "%{http_code}" http://mlflow.mlflow.svc.cluster.local:5000/health' | grep -qE '^2'; then
  echo "REFUSED: MLflow did not answer a successful status over in-cluster DNS." >&2
  exit 1
fi
echo "OK: MLflow answered a 2xx over in-cluster DNS."

echo "3. mlflow-minio-creds present in both namespaces:"
for ns in "$NAMESPACE" kubeflow; do
  kubectl get secret mlflow-minio-creds -n "$ns" >/dev/null 2>&1 || {
    echo "REFUSED: mlflow-minio-creds missing from namespace '${ns}'" >&2
    exit 1
  }
done
echo "OK: mlflow-minio-creds present in mlflow and kubeflow."

echo "MinIO + MLflow (D-12 topology) are installed and verified."
