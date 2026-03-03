#!/usr/bin/env bash
# =============================================================================
# create-instance.sh
# Creates the GCP VM for zklora x punica development.
# Run this once. Then use start/stop scripts to manage the instance.
#
# Usage:
#   ./create-instance.sh          # T4 GPU (default -- dev work)
#   ./create-instance.sh --a100   # A100 GPU (measurement runs only)
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project YOUR_PROJECT_ID
#
# Cost awareness:
#   T4  (~$0.95/hr) -- use for all dev work
#   A100 (~$3.67/hr) -- use only when taking measurements, get Mark's sign-off
#                       for any multi-GPU or extended runs
#
# Safety features baked in:
#   - Auto-shutdown at 2am daily (cron on VM)
#   - Budget alert at $150/month (GCP billing alert)
#   - Firewall: only SSH open, all other ports closed
#   - 150GB disk (not 500GB -- expand if needed, don't pre-allocate)
# =============================================================================

set -euo pipefail

# -- config -- edit these if needed ---------------------------------------------
INSTANCE_NAME="aa-zklora-dev"
ZONE="us-central1-a"
MACHINE_TYPE_A100="a2-highgpu-1g"
MACHINE_TYPE_T4="n1-standard-8"
ACCELERATOR_A100="type=nvidia-tesla-a100,count=1"
ACCELERATOR_T4="type=nvidia-tesla-t4,count=1"
DISK_SIZE="150GB"          # expand with gcloud compute disks resize if needed
DISK_TYPE="pd-ssd"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"
BUDGET_ALERT_USD=150     # monthly alert threshold -- increase if needed
ALERT_EMAIL="adas2133@colorado.edu"             # set this to your email to receive budget alerts

# -- parse args ----------------------------------------------------------------
A100=false
for arg in "$@"; do
  case $arg in
    --a100) A100=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

if [ "$A100" = true ]; then
  MACHINE_TYPE=$MACHINE_TYPE_A100
  ACCELERATOR=$ACCELERATOR_A100
  echo " Using A100 GPU (~\$3.67/hr)"
  echo ""
  echo "  [!]  A100 instances are expensive. Reminders:"
  echo "     - Auto-shutdown is set to 2am daily"
  echo "     - Run ./stop-dev.sh when done for the day"
  echo "     - For multi-GPU or extended runs, get Mark's sign-off first"
  echo ""
  read -rp "  Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
else
  MACHINE_TYPE=$MACHINE_TYPE_T4
  ACCELERATOR=$ACCELERATOR_T4
  echo " Using T4 GPU (~\$0.95/hr) -- default"
fi

# -- check project is set ------------------------------------------------------
PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT" ]; then
  echo "ERROR: No GCP project set. Run: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

echo ""
echo " Project: $PROJECT"
echo " Zone:    $ZONE"
echo " Machine: $MACHINE_TYPE"
echo " Disk:    $DISK_SIZE $DISK_TYPE"
echo ""

# -- firewall rule -- SSH only --------------------------------------------------
# Only open port 22. Jupyter runs over SSH tunnel, not a public port.
echo "Ensuring firewall rule: SSH only..."
if ! gcloud compute firewall-rules describe allow-ssh-zklora \
    --project="$PROJECT" --quiet 2>/dev/null; then
  gcloud compute firewall-rules create allow-ssh-zklora \
    --project="$PROJECT" \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:22 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=aa-zklora-dev \
    --description="SSH only for zklora dev VMs"
  echo "[OK] Firewall rule created (SSH only, port 22)"
else
  echo "[OK] Firewall rule already exists"
fi

# -- create instance -----------------------------------------------------------
echo "Creating instance '$INSTANCE_NAME'..."

gcloud compute instances create "$INSTANCE_NAME" \
  --project="$PROJECT" \
  --zone="$ZONE" \
  --machine-type="$MACHINE_TYPE" \
  --accelerator="$ACCELERATOR" \
  --image-family="$IMAGE_FAMILY" \
  --image-project="$IMAGE_PROJECT" \
  --boot-disk-size="$DISK_SIZE" \
  --boot-disk-type="$DISK_TYPE" \
  --network-interface=nic-type=GVNIC,stack-type=IPV4_ONLY,subnet=lmcache-subnet,no-address \
  --metadata=enable-osconfig=TRUE,enable-oslogin=true \
  --provisioning-model=STANDARD \
  --service-account="790904411643-compute@developer.gserviceaccount.com" \
  --boot-disk-device-name="$INSTANCE_NAME-disk" \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --tags=aa-zklora-dev \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --no-shielded-secure-boot \
  --shielded-vtpm \
  --shielded-integrity-monitoring \
  --labels=goog-ops-agent-policy=v2-x86-template-1-4-0,goog-ec-src=vm_add-gcloud \
  --reservation-affinity=any \
  --metadata=startup-script='#!/bin/bash
set -e

# -- NVIDIA drivers ------------------------------------------------------------
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" \
  | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update -q
apt-get install -y nvidia-container-toolkit ubuntu-drivers-common
ubuntu-drivers autoinstall

# -- Docker --------------------------------------------------------------------
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# Auto-add SSH users to docker group on first login (for OS Login users)
cat > /etc/profile.d/docker-group.sh << 'PROFILE'
if [ -S /var/run/docker.sock ] && ! groups | grep -qw docker; then
  sudo usermod -aG docker "$USER" 2>/dev/null
  echo "[docker] Added $USER to docker group. Run 'newgrp docker' or re-login to activate."
fi
PROFILE
chmod 644 /etc/profile.d/docker-group.sh

# -- Auto-shutdown at 2am daily ------------------------------------------------
# Protects against accidentally leaving the VM running overnight.
# Edit /etc/cron.d/auto-shutdown to change the time.
cat > /etc/cron.d/auto-shutdown << EOF
# Auto-shutdown at 2am daily to prevent accidental overnight billing.
# To disable: sudo rm /etc/cron.d/auto-shutdown
# To change time: edit this file (standard cron syntax)
0 2 * * * root /sbin/shutdown -h now "Auto-shutdown: 2am daily schedule"
EOF
chmod 644 /etc/cron.d/auto-shutdown
echo "[OK] Auto-shutdown cron set for 2am daily"

echo "startup-complete" > /tmp/startup-done
'

echo "[OK] Instance created."
echo ""

# -- budget alert --------------------------------------------------------------
# GCP billing alerts require the Billing API and a billing account linked to
# the project. This creates a budget alert at $BUDGET_ALERT_USD/month.
echo "Setting up budget alert at \$${BUDGET_ALERT_USD}/month..."
BILLING_ACCOUNT=$(gcloud billing projects describe "$PROJECT" \
  --format="value(billingAccountName)" 2>/dev/null | awk -F/ '{print $2}' || echo "")

if [ -z "$BILLING_ACCOUNT" ]; then
  echo ""
  echo "  [!]  Could not auto-detect billing account."
  echo "  Set a budget alert manually in the GCP console:"
  echo "  Billing  Budgets & alerts  Create budget"
  echo "  Recommended: \$${BUDGET_ALERT_USD}/month alert for project $PROJECT"
  echo ""
else
  # Check if gcloud billing budgets is available (requires alpha/beta)
  if gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
      --quiet 2>/dev/null | grep -q "zklora" 2>/dev/null; then
    echo "[OK] Budget alert already exists"
  else
    ALERT_CHANNELS=""
    if [ -n "$ALERT_EMAIL" ]; then
      ALERT_CHANNELS="--threshold-rules=percent=0.5,basis=CURRENT_SPEND \
        --threshold-rules=percent=0.9,basis=CURRENT_SPEND \
        --threshold-rules=percent=1.0,basis=CURRENT_SPEND"
    fi
    gcloud billing budgets create \
      --billing-account="$BILLING_ACCOUNT" \
      --display-name="aa-zklora-dev-budget" \
      --budget-amount="${BUDGET_ALERT_USD}USD" \
      --threshold-rules=percent=0.5,basis=CURRENT_SPEND \
      --threshold-rules=percent=0.9,basis=CURRENT_SPEND \
      --threshold-rules=percent=1.0,basis=CURRENT_SPEND \
      --filter-projects="projects/$PROJECT" \
      2>/dev/null && echo "[OK] Budget alert set at \$${BUDGET_ALERT_USD}/month" \
      || echo "  Could not create budget programmatically -- set one manually in GCP console"
  fi
fi

echo ""
echo "----------------------------------------"
echo "  Instance created. What's been set up:"
echo ""
echo "  [OK] Auto-shutdown at 2am daily"
echo "  [OK] Firewall: SSH only (port 22)"
echo "  [OK] Minimal IAM scopes"
echo "  [OK] Budget alert at \$${BUDGET_ALERT_USD}/month"
echo ""
echo "  Remember:"
echo "   Run ./stop-dev.sh at end of each session"
echo "   Don't leave experiments running unattended"
echo "   Get Mark's sign-off before any large runs"
echo "----------------------------------------"
echo ""
echo "Wait ~3 min for startup script, then run: ./bootstrap-instance.sh"