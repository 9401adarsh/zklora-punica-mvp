#!/usr/bin/env bash
# =============================================================================
# sync-workspace.sh
# Syncs code between your local machine and the GCP instance.
#
# Since the repo is cloned on the VM (via bootstrap-instance.sh), the
# preferred workflow is to edit directly on the VM via SSH. This script
# is a convenience for pulling/pushing changes via git.
#
# Usage:
#   ./sync-workspace.sh           # pull latest on VM (git pull + submodule update)
#   ./sync-workspace.sh --push    # push VM changes to remote (git push)
# =============================================================================

set -euo pipefail

INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
REMOTE_DIR="/home/$USER/zklora-punica-mvp"

PUSH=false
for arg in "$@"; do
  case $arg in
    --push) PUSH=true ;;
  esac
done

if [ "$PUSH" = true ]; then
  echo "Pushing VM changes to remote..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
    cd ${REMOTE_DIR}
    git add -A
    git status --short
    echo ''
    echo 'Pushing to remote...'
    git push
    echo '[OK] Pushed'
  "
else
  echo "Pulling latest onto VM..."
  gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --command="
    cd ${REMOTE_DIR}
    git pull
    git submodule update --init --recursive
    echo '[OK] Pulled'
  "
fi
