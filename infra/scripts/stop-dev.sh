#!/usr/bin/env bash
# =============================================================================
# stop-dev.sh
# Gracefully stops the dev container and then stops the GCP VM.
# Your volumes (model weights, proof artifacts, outputs) are preserved.
#
# Cost notes:
#   - You are NOT billed for compute while the VM is stopped.
#   - You ARE still billed for the boot disk (~$0.05/hr for 150GB SSD).
#   - If you won't use the VM for >1 week, run snapshot-and-delete.sh instead.
#
# Usage:
#   ./stop-dev.sh           # stop container + stop VM (do this every night)
#   ./stop-dev.sh --soft    # stop container only, leave VM running
# =============================================================================

set -euo pipefail

INSTANCE_NAME="zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="/home/$USER/zklora-punica-mvp"

SOFT=false
for arg in "$@"; do
  case $arg in
    --soft) SOFT=true ;;
  esac
done

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
echo "Stopping containers..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
  cd ${REMOTE_DIR}/infra/docker
  docker compose down 2>/dev/null || true
  docker compose --profile jupyter down 2>/dev/null || true
" 2>/dev/null || true
echo "[OK] Containers stopped"

# -- stop VM -------------------------------------------------------------------
if [ "$SOFT" = false ]; then
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
else
  echo "VM left running (--soft mode). Containers are stopped."
fi
