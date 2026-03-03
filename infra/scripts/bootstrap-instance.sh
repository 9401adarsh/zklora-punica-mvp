#!/usr/bin/env bash
# =============================================================================
# bootstrap-instance.sh
# Run once after create-instance.sh to:
#   1. Clone the repo (with submodules) onto the instance
#   2. Build the docker image on the instance
#   3. Verify GPU is visible inside the container
#
# Usage:
#   ./bootstrap-instance.sh
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="zklora-punica-mvp"

# -- check startup is done -----------------------------------------------------
echo "Checking startup script completed..."
MAX_WAIT=180
WAITED=0
while ! gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
    --command="test -f /tmp/startup-done" --quiet 2>/dev/null; do
  if [ $WAITED -ge $MAX_WAIT ]; then
    echo "ERROR: Startup script did not complete within ${MAX_WAIT}s."
    echo "SSH in manually and check: sudo journalctl -u google-startup-scripts"
    exit 1
  fi
  echo "  Waiting for startup... (${WAITED}s elapsed)"
  sleep 10
  WAITED=$((WAITED + 10))
done
echo "[OK] Startup complete"

# -- verify nvidia driver ------------------------------------------------------
echo "Verifying NVIDIA driver..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
  --command="nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
echo "[OK] GPU visible"

# -- clone repo (with submodules) onto VM --------------------------------------
echo "Cloning repo onto instance..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  set -e
  # Trust GitHub's SSH host key
  mkdir -p ~/.ssh
  ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null

  if [ ! -d ${REMOTE_DIR}/.git ]; then
    git clone --recurse-submodules git@github.com:9401adarsh/zklora-punica-mvp.git ${REMOTE_DIR}
    echo '[OK] Repo cloned with submodules'
  else
    echo '[OK] Repo already exists -- pulling latest'
    cd ${REMOTE_DIR}
    git pull
    git submodule update --init --recursive
  fi
"

# -- build docker image on instance -------------------------------------------
echo ""
echo "Building docker image on instance (this will take 10-15 minutes)..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  cd ${REMOTE_DIR}/infra/docker
  docker build --progress=plain -t aa-zklora-dev:latest .
"
echo "[OK] Docker image built"

# -- verify GPU inside container -----------------------------------------------
echo "Verifying GPU inside container..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command='
  docker run --rm --gpus all aa-zklora-dev:latest \
    python3 -c "import torch; print(\"CUDA:\", torch.cuda.is_available(), \"|\", torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"none\")"
'
echo "[OK] GPU verified inside container"

echo ""
echo "Bootstrap complete. Instance is ready."
echo ""
echo "To SSH in and start working:  ./ssh-instance.sh"
echo "To bring up the container:    ./start-dev.sh"
