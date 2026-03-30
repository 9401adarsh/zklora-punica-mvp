#!/usr/bin/env bash
# =============================================================================
# bootstrap-instance.sh
# Run once after create-instance.sh to:
#   1. Clone the repo (with submodules) onto the instance
#   2. Build both docker image variants on the instance
#   3. Verify package labels and GPU runtime for the GPU image
#
# Usage:
#   ./bootstrap-instance.sh
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="zklora-punica-mvp"

usage() {
  cat <<'USAGE'
Usage:
  ./bootstrap-instance.sh
USAGE
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --ezkl-package|--ezkl-package=*)
      echo "ERROR: --ezkl-package is no longer supported."
      echo "bootstrap-instance.sh now builds BOTH cpu and gpu images in one run."
      exit 1
      ;;
    *)
      echo "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
fi

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

# -- build both docker image variants on instance ------------------------------
echo ""
echo "Building CPU image: aa-zklora-dev:ezkl"
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  cd ${REMOTE_DIR}/infra/docker
  docker build --build-arg EZKL_PYPI_PACKAGE=ezkl --progress=plain -t aa-zklora-dev:ezkl .
"
echo "[OK] CPU image built"

echo ""
echo "Building GPU image: aa-zklora-dev:ezkl-gpu"
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  cd ${REMOTE_DIR}/infra/docker
  docker build --build-arg EZKL_PYPI_PACKAGE=ezkl-gpu --progress=plain -t aa-zklora-dev:ezkl-gpu .
"
echo "[OK] GPU image built"

# -- verify labels and package identity ----------------------------------------
echo ""
echo "Verifying image labels and package identity..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command='
  set -e
  echo "cpu_label=$(docker image inspect aa-zklora-dev:ezkl --format='"'"'{{ index .Config.Labels "aa.ezkl_pypi_package" }}'"'"')"
  echo "gpu_label=$(docker image inspect aa-zklora-dev:ezkl-gpu --format='"'"'{{ index .Config.Labels "aa.ezkl_pypi_package" }}'"'"')"
  docker run --rm aa-zklora-dev:ezkl python3 -c "import importlib.metadata as m; print('"'"'cpu_pkg'"'"', m.version('"'"'ezkl'"'"'))"
  docker run --rm aa-zklora-dev:ezkl-gpu python3 -c "import importlib.metadata as m; print('"'"'gpu_pkg'"'"', m.version('"'"'ezkl-gpu'"'"'))"
'
echo "[OK] Labels and package identity verified"

# -- verify GPU runtime against GPU image --------------------------------------
echo ""
echo "Verifying GPU runtime against aa-zklora-dev:ezkl-gpu..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command='docker run --rm --gpus all aa-zklora-dev:ezkl-gpu nvidia-smi --query-gpu=name,driver_version --format=csv,noheader'
echo "[OK] GPU runtime verified"

echo ""
echo "Bootstrap complete. This is a one-time setup."
echo "Both image modes are ready:"
echo "  - CPU: aa-zklora-dev:ezkl"
echo "  - GPU: aa-zklora-dev:ezkl-gpu"
echo ""
echo "To start CPU mode: ./scripts/start-dev.sh --container cpu"
echo "To start GPU mode: ./scripts/start-dev.sh --container gpu"
