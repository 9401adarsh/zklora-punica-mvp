#!/usr/bin/env bash
# =============================================================================
# stop-dev.sh
# Stops all dev containers and then stops the GCP VM.
# Your volumes (model weights, proof artifacts, outputs) are preserved.
#
# Cost notes:
#   - You are NOT billed for compute while the VM is stopped.
#   - You ARE still billed for the boot disk (~$0.05/hr for 150GB SSD).
#   - If you won't use the VM for >1 week, run snapshot-and-delete.sh instead.
#
# Usage:
#   ./stop-dev.sh
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="zklora-punica-mvp"

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      echo "Usage: ./stop-dev.sh"
      exit 0
      ;;
    --soft)
      echo "ERROR: --soft is no longer supported. stop-dev.sh now always stops containers and VM."
      exit 1
      ;;
    *)
      echo "ERROR: Unknown argument: $1"
      echo "Usage: ./stop-dev.sh"
      exit 1
      ;;
  esac
fi

# -- check VM status -----------------------------------------------------------
STATUS=$(gcloud compute instances describe "$INSTANCE_NAME" \
  --zone="$ZONE" --format="get(status)" 2>/dev/null || echo "NOT_FOUND")

if [ "$STATUS" = "NOT_FOUND" ]; then
  echo "Instance '$INSTANCE_NAME' not found -- nothing to stop."
  exit 0
elif [ "$STATUS" = "TERMINATED" ]; then
  echo "Instance already stopped."
  exit 0
fi

# -- stop containers -----------------------------------------------------------
echo "Stopping all dev containers..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  cd ${REMOTE_DIR}/infra/docker
  docker compose down --remove-orphans 2>/dev/null || true
  AA_ZKLORA_IMAGE_TAG=ezkl-gpu docker compose down --remove-orphans 2>/dev/null || true
  docker compose --profile jupyter down --remove-orphans 2>/dev/null || true
  AA_ZKLORA_IMAGE_TAG=ezkl-gpu docker compose --profile jupyter down --remove-orphans 2>/dev/null || true
  docker rm -f aa-zklora-dev zklora-jupyter 2>/dev/null || true
" 2>/dev/null || true
echo "[OK] Containers stopped"

# -- stop VM -------------------------------------------------------------------
echo "Stopping VM..."
gcloud compute instances stop "$INSTANCE_NAME" --zone="$ZONE"
echo "[OK] VM stopped"
echo ""
echo "----------------------------------------"
echo "  Compute billing stopped."
echo "  Disk storage (~\$0.05/hr) continues."
echo ""
echo "  If you won't use this VM for >1 week:"
echo "   Run ./snapshot-and-delete.sh to stop disk billing too"
echo "----------------------------------------"
