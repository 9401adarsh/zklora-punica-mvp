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

## Set Up SSH Key on VM (one time)

The repo is private, so the VM needs SSH access to GitHub.

```bash
# SSH into the VM
./infra/scripts/ssh-instance.sh

# On the VM: generate an SSH key
ssh-keygen -t ed25519 -C "zklora-vm" -N "" -f ~/.ssh/id_ed25519

# Show the public key -- copy this
cat ~/.ssh/id_ed25519.pub

# Exit back to local
exit
```

Then add the key as a deploy key:
1. Go to https://github.com/9401adarsh/zklora-punica-mvp/settings/keys
2. Click "Add deploy key"
3. Paste the public key, name it `zklora-vm`, check "Allow write access"

Note: after a reboot, you may need to re-SSH first (`nvidia-smi` needs a reboot
after initial driver install). The bootstrap script handles the wait automatically.

## Bootstrap (one time)

```bash
./infra/scripts/bootstrap-instance.sh
```

This will:
1. Wait for NVIDIA drivers and Docker to install on the VM
2. Add GitHub to SSH known hosts
3. Clone `9401adarsh/zklora-punica-mvp` (with submodules) onto the VM
4. Build the Docker image (~10-15 min)
5. Verify GPU is accessible inside the container

## GPU Note: T4 vs A100

Punica's CUDA kernels (SGMV, BGMV) are compiled for sm_80 (A100) only.
T4 (sm_75) lacks bfloat16 intrinsics that Punica requires at compile time.

- T4 (~$0.95/hr) -- use for Python-level dev: hooks, prover, registry, tests
- A100 (~$3.67/hr) -- use when running actual SGMV kernels or taking measurements

To switch to A100:
```bash
./infra/scripts/stop-dev.sh --hard
# Delete current instance and recreate with A100
./infra/scripts/create-instance.sh --a100
./infra/scripts/bootstrap-instance.sh
```

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

### Option A: VS Code Remote SSH (recommended)

Add to `~/.ssh/config` on your local machine:
```
Host aa-zklora-dev
    HostName aa-zklora-dev
    User ext_adas2133_colorado_edu
    IdentityFile ~/.ssh/google_compute_engine
    ProxyCommand gcloud compute start-iap-tunnel %h 22 --listen-on-stdin --zone=us-central1-a --project=gbc-oit-rc-basil-app-bo
```

Then in VS Code:
1. Install the "Remote - SSH" extension
2. Cmd+Shift+P -> "Remote-SSH: Connect to Host..." -> select `aa-zklora-dev`
3. Open folder -> `~/zklora-punica-mvp`

### Option B: Terminal SSH

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

### Running code inside the container

`start-dev.sh` is a LOCAL script only -- do not run it from the VM.
If you are already on the VM (via VS Code or SSH), use Docker directly:

```bash
cd ~/zklora-punica-mvp/infra/docker
docker compose up -d dev            # start container (if not running)
docker exec -it aa-zklora-dev bash  # shell into container
```

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
