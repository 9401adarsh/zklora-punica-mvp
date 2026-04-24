#!/usr/bin/env bash
# =============================================================================
# start-dev.sh
# Starts the GCP instance (if stopped) and brings up the dev container.
# Drops you into a shell inside the selected container mode.
#
# Usage:
#   ./start-dev.sh                               # start VM + CPU container, drop into shell
#   ./start-dev.sh --container gpu               # start VM + GPU container, drop into shell
#   ./start-dev.sh --jupyter                     # also start jupyter lab
#   ./start-dev.sh --no-shell                    # start container but don't attach
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="zklora-punica-mvp"

usage() {
  cat <<'USAGE'
Usage:
  ./start-dev.sh [--container {cpu|gpu}] [--jupyter] [--no-shell]
USAGE
}

TARGET_CONTAINER="cpu"
JUPYTER=false
NO_SHELL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --container)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --container requires a value: cpu or gpu"
        usage
        exit 1
      fi
      TARGET_CONTAINER="$2"
      shift 2
      ;;
    --container=*)
      TARGET_CONTAINER="${1#*=}"
      shift
      ;;
    --jupyter)
      JUPYTER=true
      shift
      ;;
    --no-shell)
      NO_SHELL=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

case "$TARGET_CONTAINER" in
  cpu)
    IMAGE_TAG="ezkl"
    ;;
  gpu)
    IMAGE_TAG="ezkl-gpu"
    ;;
  *)
    echo "ERROR: Invalid --container '$TARGET_CONTAINER'. Expected: cpu or gpu"
    exit 1
    ;;
esac

# -- start VM if stopped -------------------------------------------------------
STATUS=$(gcloud compute instances describe "$INSTANCE_NAME" \
  --zone="$ZONE" --format="get(status)" 2>/dev/null || echo "NOT_FOUND")

if [ "$STATUS" = "NOT_FOUND" ]; then
  echo "ERROR: Instance '$INSTANCE_NAME' not found. Run create-instance.sh first."
  exit 1
elif [ "$STATUS" = "TERMINATED" ]; then
  echo "Starting instance..."
  gcloud compute instances start "$INSTANCE_NAME" --zone="$ZONE"
  echo "Waiting for SSH..."
  sleep 15
  for i in $(seq 1 12); do
    if gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
      --command="echo ok" --quiet 2>/dev/null; then
      break
    fi
    sleep 5
  done
  echo "[OK] Instance started"
elif [ "$STATUS" = "RUNNING" ]; then
  echo "[OK] Instance already running"
fi

echo "Selected container mode: ${TARGET_CONTAINER}"
echo "Selected image tag: aa-zklora-dev:${IMAGE_TAG}"

# -- fail fast if requested image is missing -----------------------------------
if ! gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  docker image inspect aa-zklora-dev:${IMAGE_TAG} >/dev/null 2>&1
" >/dev/null 2>&1; then
  echo "ERROR: Image aa-zklora-dev:${IMAGE_TAG} was not found on the VM."
  echo "Run one-time bootstrap to build both images: ./scripts/bootstrap-instance.sh"
  exit 1
fi

# -- bring up selected container ------------------------------------------------
echo "Bringing up dev container..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  cd ${REMOTE_DIR}/infra/docker
  AA_ZKLORA_IMAGE_TAG=${IMAGE_TAG} docker compose up --no-build -d --force-recreate dev
"
echo "[OK] Container up"

# -- optionally start jupyter --------------------------------------------------
if [ "$JUPYTER" = true ]; then
  echo "Starting Jupyter Lab..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
    cd ${REMOTE_DIR}/infra/docker
    AA_ZKLORA_IMAGE_TAG=${IMAGE_TAG} docker compose --profile jupyter up --no-build -d --force-recreate jupyter
  "
  echo "Setting up port forwarding for Jupyter (localhost:8889)..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
    -- -NL 8889:localhost:8889 &
  PF_PID=$!
  echo "[OK] Jupyter available at http://localhost:8889 (token: zklora)"
  echo "  Port forward PID: $PF_PID"
  echo "  Kill port forward: kill $PF_PID"
fi

# -- drop into shell -----------------------------------------------------------
if [ "$NO_SHELL" = false ]; then
  echo ""
  echo "Dropping into container shell..."
  echo "(Type 'exit' to leave the shell -- container keeps running)"
  echo ""
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
    docker exec -it aa-zklora-dev /bin/bash
  " -- -t
fi
