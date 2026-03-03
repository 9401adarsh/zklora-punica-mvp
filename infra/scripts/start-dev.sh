#!/usr/bin/env bash
# =============================================================================
# start-dev.sh
# Starts the GCP instance (if stopped) and brings up the dev container.
# Drops you into a shell inside the container.
#
# Usage:
#   ./start-dev.sh              # start VM + container, drop into shell
#   ./start-dev.sh --jupyter    # also start jupyter lab
#   ./start-dev.sh --no-shell   # start container but don't attach
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="zklora-punica-mvp"

JUPYTER=false
NO_SHELL=false
for arg in "$@"; do
  case $arg in
    --jupyter)  JUPYTER=true ;;
    --no-shell) NO_SHELL=true ;;
  esac
done

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
  # wait for SSH to be ready
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

# -- bring up container --------------------------------------------------------
echo "Bringing up dev container..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  cd ${REMOTE_DIR}/infra/docker
  docker compose up -d dev
"
echo "[OK] Container up"

# -- optionally start jupyter --------------------------------------------------
if [ "$JUPYTER" = true ]; then
  echo "Starting Jupyter Lab..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
    cd ${REMOTE_DIR}/infra/docker
    docker compose --profile jupyter up -d jupyter
  "
  # set up port forwarding for jupyter in background
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
