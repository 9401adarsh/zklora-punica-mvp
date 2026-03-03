#!/usr/bin/env bash
# =============================================================================
# snapshot-and-delete.sh
# For extended breaks (>1 week). Snapshots the VM disk, then deletes the VM.
# This stops ALL billing including disk storage.
#
# To restore: run restore-from-snapshot.sh
#
# Cost:
#   Snapshot storage: ~$0.026/GB/month (much cheaper than keeping the disk)
#   150GB disk stopped: ~$36/month
#   150GB snapshot:     ~$3.90/month
#
# Usage:
#   ./snapshot-and-delete.sh
# =============================================================================

set -euo pipefail

INSTANCE_NAME="zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="/home/$USER/zklora-punica-mvp"
SNAPSHOT_NAME="zklora-dev-snap-$(date +%Y%m%d)"

# -- safety check --------------------------------------------------------------
echo "----------------------------------------"
echo "  Snapshot + Delete"
echo ""
echo "  This will:"
echo "  1. Push uncommitted changes to git remote (safety)"
echo "  2. Snapshot the VM disk as: $SNAPSHOT_NAME"
echo "  3. Delete the VM and its disk"
echo ""
echo "  All billing stops. Restore with: ./restore-from-snapshot.sh"
echo "----------------------------------------"
echo ""
read -rp "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# -- check VM status -----------------------------------------------------------
STATUS=$(gcloud compute instances describe "$INSTANCE_NAME" \
  --zone="$ZONE" --format="get(status)" 2>/dev/null || echo "NOT_FOUND")

if [ "$STATUS" = "NOT_FOUND" ]; then
  echo "Instance '$INSTANCE_NAME' not found."
  exit 1
fi

# -- push code to remote before deleting ---------------------------------------
if [ "$STATUS" = "RUNNING" ]; then
  echo "Pushing any uncommitted changes to remote before deleting..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
    cd ${REMOTE_DIR}
    if [ -n \"\$(git status --porcelain)\" ]; then
      git add -A
      git commit -m 'auto-commit before snapshot-and-delete'
      git push && echo '[OK] Changes pushed to remote'
    else
      echo '[OK] No uncommitted changes'
    fi
  " 2>/dev/null && true || echo "  Warning: git push failed -- check manually before deleting"
fi

# -- stop VM if running --------------------------------------------------------
if [ "$STATUS" = "RUNNING" ]; then
  echo "Stopping containers..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
    cd ${REMOTE_DIR}/infra/docker
    docker compose down 2>/dev/null || true
  " 2>/dev/null || true

  echo "Stopping VM..."
  gcloud compute instances stop "$INSTANCE_NAME" --zone="$ZONE"
  echo "[OK] VM stopped"
fi

# -- snapshot disk -------------------------------------------------------------
echo "Creating snapshot '$SNAPSHOT_NAME'..."
gcloud compute disks snapshot "${INSTANCE_NAME}-disk" \
  --zone="$ZONE" \
  --snapshot-names="$SNAPSHOT_NAME" \
  --description="zklora-dev snapshot $(date +%Y-%m-%d)"
echo "[OK] Snapshot created"

# -- delete VM -----------------------------------------------------------------
echo "Deleting VM and disk..."
gcloud compute instances delete "$INSTANCE_NAME" \
  --zone="$ZONE" \
  --delete-disks=boot \
  --quiet
echo "[OK] VM deleted"

echo ""
echo "----------------------------------------"
echo "  All billing stopped."
echo "  Snapshot saved as: $SNAPSHOT_NAME"
echo ""
echo "  To restore: ./restore-from-snapshot.sh"
echo "----------------------------------------"
