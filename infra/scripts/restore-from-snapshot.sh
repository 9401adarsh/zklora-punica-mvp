#!/usr/bin/env bash
# =============================================================================
# restore-from-snapshot.sh
# Restores the dev VM from a snapshot created by snapshot-and-delete.sh.
#
# Usage:
#   ./restore-from-snapshot.sh                    # uses most recent snapshot
#   ./restore-from-snapshot.sh --snapshot=NAME    # uses specific snapshot
# =============================================================================

set -euo pipefail

INSTANCE_NAME="zklora-dev"
ZONE="us-central1-a"
SNAPSHOT_NAME=""

for arg in "$@"; do
  case $arg in
    --snapshot=*) SNAPSHOT_NAME="${arg#*=}" ;;
  esac
done

PROJECT=$(gcloud config get-value project 2>/dev/null)

# -- find snapshot -------------------------------------------------------------
if [ -z "$SNAPSHOT_NAME" ]; then
  echo "Finding most recent zklora snapshot..."
  SNAPSHOT_NAME=$(gcloud compute snapshots list \
    --filter="name~zklora-dev-snap" \
    --sort-by="~creationTimestamp" \
    --format="value(name)" \
    --limit=1 2>/dev/null || echo "")

  if [ -z "$SNAPSHOT_NAME" ]; then
    echo "ERROR: No zklora snapshots found."
    echo "Available snapshots:"
    gcloud compute snapshots list --format="table(name,creationTimestamp,diskSizeGb)"
    exit 1
  fi
fi

echo " Restoring from snapshot: $SNAPSHOT_NAME"
echo ""

# -- get machine type from create-instance.sh defaults ------------------------
# Restore as T4 by default -- cheapest option
MACHINE_TYPE="n1-standard-8"
ACCELERATOR="type=nvidia-tesla-t4,count=1"

echo "Restoring as T4 instance (default). Use create-instance.sh --a100 if needed."
echo ""

# -- recreate disk from snapshot -----------------------------------------------
DISK_NAME="${INSTANCE_NAME}-disk"
echo "Creating disk from snapshot..."
gcloud compute disks create "$DISK_NAME" \
  --zone="$ZONE" \
  --source-snapshot="$SNAPSHOT_NAME" \
  --type=pd-ssd
echo "[OK] Disk restored"

# -- recreate instance with restored disk -------------------------------------
echo "Creating instance with restored disk..."
gcloud compute instances create "$INSTANCE_NAME" \
  --project="$PROJECT" \
  --zone="$ZONE" \
  --machine-type="$MACHINE_TYPE" \
  --accelerator="$ACCELERATOR" \
  --disk="name=${DISK_NAME},boot=yes,auto-delete=yes" \
  --network-interface=nic-type=GVNIC,stack-type=IPV4_ONLY,subnet=lmcache-subnet,no-address \
  --metadata=enable-osconfig=TRUE,enable-oslogin=true \
  --provisioning-model=STANDARD \
  --service-account="790904411643-compute@developer.gserviceaccount.com" \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --tags=zklora-dev \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --no-shielded-secure-boot \
  --shielded-vtpm \
  --shielded-integrity-monitoring \
  --labels=goog-ops-agent-policy=v2-x86-template-1-4-0,goog-ec-src=vm_add-gcloud \
  --reservation-affinity=any \
  --metadata=startup-script='#!/bin/bash
    # Re-enable auto-shutdown cron (may have been wiped if snapshot was old)
    cat > /etc/cron.d/auto-shutdown << EOF
0 2 * * * root /sbin/shutdown -h now "Auto-shutdown: 2am daily schedule"
EOF
    chmod 644 /etc/cron.d/auto-shutdown
    # Restart docker in case it needs it after restore
    systemctl restart docker
    echo "startup-complete" > /tmp/startup-done
  '

echo "[OK] Instance restored from snapshot"
echo ""
echo "Wait ~1 minute, then run: ./start-dev.sh"
