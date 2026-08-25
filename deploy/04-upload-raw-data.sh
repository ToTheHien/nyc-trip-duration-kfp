#!/usr/bin/env bash
# Uploads the locally cached TLC months into the tlc-raw bucket, under the
# exact object name lib.artifacts.ingest_month_to_parquet downloads (via
# lib.ingest.month_parquet_path's filename shape), so component pods can
# read them.
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

BIN_DIR="$REPO_ROOT/.deploy-bin"
export PATH="$BIN_DIR:$PATH"

DATA_DIR="$REPO_ROOT/data/tlc"
NAMESPACE="mlflow"
LOCAL_PORT=9000

shopt -s nullglob
FILES=("$DATA_DIR"/yellow_tripdata_*.parquet)
if [ "${#FILES[@]}" -eq 0 ]; then
  echo "REFUSED: no yellow_tripdata_*.parquet files found under ${DATA_DIR} - run scripts/download_tlc_data.py first." >&2
  exit 1
fi
echo "Found ${#FILES[@]} local month file(s) to upload."

# Credentials are read from the Secret at runtime and only ever exported
# into this script's own environment - never printed, never written to a
# file.
MINIO_ROOT_USER="$(kubectl get secret minio-root-creds -n "$NAMESPACE" -o jsonpath='{.data.rootUser}' | base64 -d)"
MINIO_ROOT_PASSWORD="$(kubectl get secret minio-root-creds -n "$NAMESPACE" -o jsonpath='{.data.rootPassword}' | base64 -d)"
if [ -z "$MINIO_ROOT_USER" ] || [ -z "$MINIO_ROOT_PASSWORD" ]; then
  echo "REFUSED: could not read minio-root-creds from namespace '${NAMESPACE}' - run deploy/03-storage-tracking.sh first." >&2
  exit 1
fi

kubectl port-forward -n "$NAMESPACE" svc/minio "${LOCAL_PORT}:9000" >/tmp/minio-upload-port-forward.log 2>&1 &
PF_PID=$!
cleanup() { kill "$PF_PID" >/dev/null 2>&1 || true; }
trap cleanup EXIT

READY=0
for _ in $(seq 1 30); do
  if curl -sf -o /dev/null "http://127.0.0.1:${LOCAL_PORT}/minio/health/live"; then
    READY=1
    break
  fi
  sleep 1
done
if [ "$READY" -ne 1 ]; then
  echo "REFUSED: MinIO port-forward on ${LOCAL_PORT} never became healthy." >&2
  exit 1
fi

AWS_ACCESS_KEY_ID="$MINIO_ROOT_USER" \
AWS_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD" \
UV_PROJECT_ENVIRONMENT="$REPO_ROOT/path/to/venv" \
uv run --extra dev --extra ml --extra pipeline python - "$DATA_DIR" "127.0.0.1:${LOCAL_PORT}" <<'PYEOF'
"""Upload every local yellow_tripdata_*.parquet file into tlc-raw, printing
only the object name and byte count - never a credential."""

import sys
from pathlib import Path

from lib.artifacts import RAW_BUCKET, default_s3_client, upload_object

data_dir = Path(sys.argv[1])
endpoint_url = f"http://{sys.argv[2]}"

files = sorted(data_dir.glob("yellow_tripdata_*.parquet"))
if not files:
    raise SystemExit(f"REFUSED: no yellow_tripdata_*.parquet files found under {data_dir}")

client = default_s3_client(endpoint_url)
for path in files:
    size = path.stat().st_size
    upload_object(client, path, RAW_BUCKET, path.name)
    print(f"uploaded {path.name}: {size} bytes -> s3://{RAW_BUCKET}/{path.name}")

print(f"summary: {len(files)} object(s) uploaded to bucket '{RAW_BUCKET}'")
PYEOF
