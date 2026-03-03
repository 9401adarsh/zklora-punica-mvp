#!/usr/bin/env bash
# =============================================================================
# add-data-disk.sh
# Creates and attaches a persistent data disk to an existing zklora-dev VM.
# Can be run at any time — the disk is independent of VM lifecycle.
#
# Usage:
#   ./add-data-disk.sh                  # 500GB pd-balanced (default)
#   ./add-data-disk.sh --size=200       # custom size in GB
#
# What it does:
#   1. Creates a pd-balanced (standard SSD) disk
#   2. Attaches it to the running VM
#   3. SSHs into the VM to format (ext4) and mount at /mnt/data
#   4. Adds an fstab entry so it persists across reboots
#
# The disk is NOT auto-deleted with the VM. If you delete and recreate
# the VM, the disk survives and can be re-attached.
#
# To detach later:
#   gcloud compute instances detach-disk zklora-dev \
#     --disk=zklora-dev-data --zone=us-central1-a
#
# To delete the disk entirely:
#   gcloud compute disks delete zklora-dev-data --zone=us-central1-a
# =============================================================================

set -euo pipefail

# -- config -------------------------------------------------------------------
INSTANCE_NAME="zklora-dev"
ZONE="us-central1-a"
DISK_NAME="${INSTANCE_NAME}-data"
DISK_TYPE="pd-balanced"       # standard SSD — cheaper than pd-ssd, still fast
DISK_SIZE="500"               # GB — override with --size=N
MOUNT_POINT="/mnt/data"
DEVICE_NAME="persistent-data"

# -- parse args ---------------------------------------------------------------
for arg in "$@"; do
  case $arg in
    --size=*) DISK_SIZE="${arg#*=}" ;;
    *) echo "Unknown argument: $arg"; echo "Usage: $0 [--size=N]"; exit 1 ;;
  esac
done

# -- check project ------------------------------------------------------------
PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT" ]; then
  echo "ERROR: No GCP project set. Run: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

echo ""
echo "  Data Disk Setup"
echo "  ─────────────────────────────────"
echo "  Instance:  $INSTANCE_NAME"
echo "  Disk:      $DISK_NAME"
echo "  Size:      ${DISK_SIZE} GB"
echo "  Type:      $DISK_TYPE (standard SSD)"
echo "  Mount:     $MOUNT_POINT"
echo "  Project:   $PROJECT"
echo "  Zone:      $ZONE"
echo ""

# -- step 1: create the disk (if not exists) ----------------------------------
if gcloud compute disks describe "$DISK_NAME" \
    --project="$PROJECT" --zone="$ZONE" --quiet 2>/dev/null; then
  echo "[OK] Disk '$DISK_NAME' already exists — skipping creation"
else
  echo "Creating disk '$DISK_NAME' (${DISK_SIZE}GB $DISK_TYPE)..."
  gcloud compute disks create "$DISK_NAME" \
    --project="$PROJECT" \
    --zone="$ZONE" \
    --size="${DISK_SIZE}GB" \
    --type="$DISK_TYPE"
  echo "[OK] Disk created"
fi

# -- step 2: attach to VM (if not already attached) ---------------------------
if gcloud compute instances describe "$INSTANCE_NAME" \
    --project="$PROJECT" --zone="$ZONE" \
    --format="value(disks[].source)" 2>/dev/null | grep -q "$DISK_NAME"; then
  echo "[OK] Disk already attached to '$INSTANCE_NAME'"
else
  echo "Attaching disk to '$INSTANCE_NAME'..."
  gcloud compute instances attach-disk "$INSTANCE_NAME" \
    --project="$PROJECT" \
    --zone="$ZONE" \
    --disk="$DISK_NAME" \
    --device-name="$DEVICE_NAME" \
    --mode=rw
  echo "[OK] Disk attached"
fi

# -- step 3: format and mount via SSH -----------------------------------------
echo "Formatting and mounting disk on VM..."
echo ""

gcloud compute ssh "$INSTANCE_NAME" \
  --project="$PROJECT" \
  --zone="$ZONE" \
  --command="
set -euo pipefail

DEVICE=\"/dev/disk/by-id/google-${DEVICE_NAME}\"
MOUNT=\"${MOUNT_POINT}\"

# Wait for device to appear
for i in \$(seq 1 10); do
  [ -e \"\$DEVICE\" ] && break
  echo \"  Waiting for device to appear... (\$i/10)\"
  sleep 2
done

if [ ! -e \"\$DEVICE\" ]; then
  echo \"ERROR: Device \$DEVICE not found after waiting\"
  exit 1
fi

# Only format if no filesystem exists (safe for re-runs)
if ! sudo blkid \"\$DEVICE\" | grep -q 'TYPE='; then
  echo \"  Formatting \$DEVICE as ext4...\"
  sudo mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard \"\$DEVICE\"
  echo \"  [OK] Formatted\"
else
  echo \"  [OK] Filesystem already exists — skipping format\"
fi

# Create mount point and mount
sudo mkdir -p \"\$MOUNT\"
if mountpoint -q \"\$MOUNT\" 2>/dev/null; then
  echo \"  [OK] Already mounted at \$MOUNT\"
else
  sudo mount -o discard,defaults \"\$DEVICE\" \"\$MOUNT\"
  echo \"  [OK] Mounted at \$MOUNT\"
fi

# Add to fstab for persistence across reboots (idempotent)
FSTAB_ENTRY=\"\$DEVICE \$MOUNT ext4 discard,defaults,nofail 0 2\"
if ! grep -qF \"$DEVICE_NAME\" /etc/fstab; then
  echo \"\$FSTAB_ENTRY\" | sudo tee -a /etc/fstab > /dev/null
  echo \"  [OK] Added to /etc/fstab\"
else
  echo \"  [OK] fstab entry already exists\"
fi

# Make accessible to current user
sudo chmod 777 \"\$MOUNT\"

echo \"\"
echo \"  Disk ready:\"
df -h \"\$MOUNT\" | tail -1 | awk '{printf \"    Size: %s  Used: %s  Available: %s\n\", \$2, \$3, \$4}'
"

echo ""
echo "────────────────────────────────────"
echo "  [OK] Data disk ready at $MOUNT_POINT"
echo ""
echo "  The disk is independent of the VM."
echo "  It will survive VM deletion and can"
echo "  be re-attached to a new instance."
echo "────────────────────────────────────"
echo ""
