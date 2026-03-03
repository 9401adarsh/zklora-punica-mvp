#!/usr/bin/env bash
# =============================================================================
# ssh-instance.sh
# SSH into the GCP instance directly (not into the container).
# Useful for docker management, checking disk space, logs etc.
#
# Usage:
#   ./ssh-instance.sh              # plain SSH
#   ./ssh-instance.sh --jupyter    # SSH + set up jupyter port forward
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"

JUPYTER=false
for arg in "$@"; do
  case $arg in
    --jupyter) JUPYTER=true ;;
  esac
done

if [ "$JUPYTER" = true ]; then
  echo "SSH with Jupyter port forward (localhost:8889)..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
    -- -L 8889:localhost:8889
else
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE"
fi
