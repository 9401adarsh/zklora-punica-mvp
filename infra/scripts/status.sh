#!/usr/bin/env bash
# =============================================================================
# status.sh
# Shows current state of the instance, containers, GPU, and disk usage.
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="zklora-punica-mvp"

echo "=========================================="
echo "  zkLoRA Dev Environment Status"
echo "=========================================="
echo ""

# -- VM status -----------------------------------------------------------------
STATUS=$(gcloud compute instances describe "$INSTANCE_NAME" \
  --zone="$ZONE" \
  --format="get(status)" 2>/dev/null || echo "NOT_FOUND")

MACHINE_TYPE=$(gcloud compute instances describe "$INSTANCE_NAME" \
  --zone="$ZONE" \
  --format="get(machineType)" 2>/dev/null | awk -F/ '{print $NF}' || echo "unknown")

echo "VM Status:    $STATUS"
echo "Machine Type: $MACHINE_TYPE"
echo "Zone:         $ZONE"
echo ""

if [ "$STATUS" != "RUNNING" ]; then
  echo "VM is not running. Start with: ./start-dev.sh"
  exit 0
fi

# -- GPU status ----------------------------------------------------------------
echo "-- GPU -----------------------------------"
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --quiet --command="
  nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu \
    --format=csv,noheader,nounits \
  | awk -F, '{printf \"  %s | VRAM: %sMiB / %sMiB | GPU: %s%% | Temp: %sC\n\", \$1, \$2, \$3, \$4, \$5}'
" 2>/dev/null
echo ""

# -- container status ----------------------------------------------------------
echo "-- Containers ----------------------------"
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --quiet --command="
  docker ps --format '  {{.Names}} | {{.Status}} | {{.Ports}}' 2>/dev/null || echo '  No containers running'
" 2>/dev/null
echo ""

# -- disk usage ----------------------------------------------------------------
echo "-- Disk ----------------------------------"
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --quiet --command="
  df -h / | tail -1 | awk '{printf \"  Root disk:  %s used / %s total (%s)\n\", \$3, \$2, \$5}'
  docker system df 2>/dev/null | grep -v '^TYPE' | awk '{printf \"  %-20s %s\n\", \$1, \$4}' || true
" 2>/dev/null
echo ""

# -- volume sizes -------------------------------------------------------------
echo "-- Volumes -------------------------------"
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --quiet --command="
  docker volume ls -q 2>/dev/null | while read vol; do
    size=\$(docker run --rm -v \$vol:/vol alpine du -sh /vol 2>/dev/null | cut -f1)
    printf '  %-35s %s\n' \$vol \$size
  done
" 2>/dev/null
echo ""

echo "=========================================="
