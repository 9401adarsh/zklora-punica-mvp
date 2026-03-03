# Setup Guide

## Prerequisites

- [ ] `gcloud` CLI installed and authenticated (`gcloud auth login`)
- [ ] GCP project set (`gcloud config set project gbc-oit-rc-basil-app-bo`)
- [ ] `gh` CLI installed and authenticated (`gh auth login`)
- [ ] Fork `punica-ai/punica` to `9401adarsh/punica` on GitHub
- [ ] Fork `bageldotcom/zkLoRA` to `9401adarsh/zkLoRA` on GitHub
- [ ] Add both forks as git submodules in this repo:

```bash
cd zklora-punica-mvp
git submodule add git@github.com:9401adarsh/punica.git punica
git submodule add git@github.com:9401adarsh/zkLoRA.git zklora
git commit -m "add punica and zklora submodules"
git push
```

## Create the VM

```bash
chmod +x infra/scripts/*.sh

# Set your email for budget alerts (line 41 of create-instance.sh)
# ALERT_EMAIL="adas2133@colorado.edu"

# Create VM (T4 default, ~$0.95/hr)
./infra/scripts/create-instance.sh

# Wait ~3 minutes for startup script to finish
```

## Bootstrap (one time)

```bash
./infra/scripts/bootstrap-instance.sh
```

This will:
1. Wait for NVIDIA drivers and Docker to install on the VM
2. Clone `9401adarsh/zklora-punica-mvp` (with submodules) onto the VM
3. Build the Docker image (~10-15 min)
4. Verify GPU is accessible inside the container

## Start Working

```bash
# Start VM + container, drop into shell
./infra/scripts/start-dev.sh

# Start with Jupyter Lab
./infra/scripts/start-dev.sh --jupyter
```

## Daily Workflow

```
Morning:  ./infra/scripts/start-dev.sh
          SSH into VM in a separate terminal to edit code
          Changes reflect inside the container immediately
Evening:  ./infra/scripts/stop-dev.sh
```

## Editing Code

SSH into the VM:
```bash
./infra/scripts/ssh-instance.sh
```

On the VM, the repo is at `~/zklora-punica-mvp/`. Edit any of:
- `src/` -- your project code (maps to /workspace/src in container)
- `punica/` -- your Punica fork (maps to /opt/punica in container)
- `zklora/` -- your zkLoRA fork (maps to /opt/zkLoRA in container)
- `tests/`, `experiments/`, `notebooks/` -- all under /workspace/

All changes are live inside the container. No rebuild needed.

## Extended Break (>1 week)

```bash
# Snapshot disk + delete VM (stops all billing)
./infra/scripts/snapshot-and-delete.sh

# When you return
./infra/scripts/restore-from-snapshot.sh
./infra/scripts/bootstrap-instance.sh
./infra/scripts/start-dev.sh
```

## Optional: Data Disk

For witness logs, proof artifacts, and large datasets. Run whenever you need it:

```bash
./infra/scripts/add-data-disk.sh              # 500GB pd-balanced
./infra/scripts/add-data-disk.sh --size=200   # custom size
```

Mounts at `/mnt/data` on the VM. Survives VM deletion.

## Quick Reference

| Task | Command |
|------|---------|
| Create VM | `./infra/scripts/create-instance.sh` |
| Bootstrap | `./infra/scripts/bootstrap-instance.sh` |
| Start | `./infra/scripts/start-dev.sh` |
| Stop | `./infra/scripts/stop-dev.sh` |
| SSH | `./infra/scripts/ssh-instance.sh` |
| Status | `./infra/scripts/status.sh` |
| Sync (pull on VM) | `./infra/scripts/sync-workspace.sh` |
| Sync (push from VM) | `./infra/scripts/sync-workspace.sh --push` |
| Snapshot + delete | `./infra/scripts/snapshot-and-delete.sh` |
| Restore | `./infra/scripts/restore-from-snapshot.sh` |
| Add data disk | `./infra/scripts/add-data-disk.sh` |
