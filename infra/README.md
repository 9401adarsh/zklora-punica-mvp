# zkLoRA × Punica -- Dev Infrastructure

Dockerised GCP dev environment. One T4 VM for development, upgrade to A100 for measurement runs only. Bring it up and down as needed.

---

## Cost Guidelines (Read First)

These apply to all lab cloud usage:

- **Stop your VM every night.** Run `./scripts/stop-dev.sh` at end of each session. Compute billing stops immediately.
- **Don't leave experiments running unattended.** Auto-shutdown is set at 2am daily as a backstop -- not a substitute for stopping manually.
- **Use T4 for development.** Only switch to A100 when you're actually taking measurements. T4 is ~$0.95/hr, A100 is ~$3.67/hr.
- **Get Mark's sign-off for large runs.** Any experiment using multiple GPUs or running for an extended period needs review first.
- **Snapshot and delete for extended breaks.** A stopped VM still bills for disk (~$0.05/hr). If you won't use it for >1 week, run `./scripts/snapshot-and-delete.sh`. Restore is one command.
- **Budget alert is set at $150/month.** You'll get an email if you're approaching this. It's a warning, not a hard cap.

| Config          | $/hr   | $/day (4hr session) | $/month (20 sessions) |
|-----------------|--------|---------------------|-----------------------|
| T4 running      | ~$0.95 | ~$3.80              | ~$76                  |
| A100 running    | ~$3.67 | ~$14.68             | ~$294                 |
| VM stopped      | ~$0.05 | ~$1.20 (disk only)  | ~$36                  |
| Snapshot        | --      | --                   | ~$3.90                |

---

## Directory Structure

```
infra/
├─ docker/
│   ├─ Dockerfile                # dev image (CUDA 11.8, PyTorch, ezkl, Punica, zkLoRA)
│   └─ docker-compose.yml        # container config + named volumes
├─ scripts/
│   ├─ create-instance.sh        # one-time VM creation (T4 default, --a100 flag)
│   ├─ bootstrap-instance.sh     # one-time docker build on the VM
│   ├─ start-dev.sh              # start VM + container, drop into shell
│   ├─ stop-dev.sh               # stop container + stop VM (run this nightly)
│   ├─ snapshot-and-delete.sh    # for breaks >1 week -- stops all billing
│   ├─ restore-from-snapshot.sh  # restore from snapshot
│   ├─ add-data-disk.sh          # attach a persistent data disk (on demand)
│   ├─ ssh-instance.sh           # SSH into the VM directly
│   ├─ sync-workspace.sh         # push/pull local workspace ↔ instance
│   └─ status.sh                 # GPU, containers, disk at a glance
├─ README.md                     # this file
└─ ../workspace/                 # your code -- live-mounted into container
```

---

## First-Time Setup

### 0. Prerequisites

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID # get project id from gcloud list projects

chmod +x scripts/*.sh
```

Set your email in `create-instance.sh` for budget alerts:
```bash
ALERT_EMAIL="your@email.com"   # line 42 of create-instance.sh
```

Check A100 quota if you'll eventually need it:
```bash
gcloud compute regions describe us-central1 \
  --format="json(quotas)" | grep -A1 NVIDIA_A100
```
If `limit` is 0, request an increase in the GCP console -- approvals take 24-48 hours. Not needed for T4.

---

### 1. Create the VM (one time)

```bash
# T4 -- default, use for all development work (~$0.95/hr)
./scripts/create-instance.sh

# A100 -- measurement runs only, get Mark's sign-off first (~$3.67/hr)
./scripts/create-instance.sh --a100
```

The A100 flag requires confirmation. Both options include:
- Auto-shutdown at 2am daily
- SSH-only firewall (port 22, no public Jupyter port)
- Shielded VM (vtpm + integrity monitoring, secure boot disabled)
- Budget alert at $150/month

Wait ~3 minutes for the startup script to finish.

---

### 2. Bootstrap the VM (one time)

```bash
./scripts/bootstrap-instance.sh
```

Copies Docker files and workspace to the VM, builds the Docker image (~10-15 min first time), and verifies GPU access inside the container.

---

### 3. Daily workflow

```bash
# Morning: start VM + container, drop into shell
./scripts/start-dev.sh

# Morning: start with Jupyter Lab too
./scripts/start-dev.sh --jupyter

# Evening: stop container + stop VM -- billing stops
./scripts/stop-dev.sh
```

Your work is preserved in named Docker volumes across stop/start cycles.

---

## Scripts Reference

### `create-instance.sh` — One-Time VM Creation

Creates the GCP VM with T4 GPU (default) or A100 (`--a100`). Sets up firewall, auto-shutdown cron, and budget alerts. Installs NVIDIA drivers and Docker via startup script.

```bash
./scripts/create-instance.sh          # T4 GPU (default)
./scripts/create-instance.sh --a100   # A100 GPU
```

### `bootstrap-instance.sh` — One-Time Docker Build

Waits for the startup script to complete, copies Docker config and workspace to the VM, builds the Docker image, and verifies GPU is visible inside the container.

```bash
./scripts/bootstrap-instance.sh
```

### `start-dev.sh` — Start VM + Container

Starts the VM (if stopped), brings up the dev container, and drops you into a shell. Optionally starts Jupyter Lab with port forwarding.

```bash
./scripts/start-dev.sh              # start VM + container, drop into shell
./scripts/start-dev.sh --jupyter    # also start Jupyter Lab (localhost:8889)
./scripts/start-dev.sh --no-shell   # start container but don't attach
```

### `stop-dev.sh` — Stop Container + VM

Gracefully stops Docker containers, then stops the VM. Run this at the end of every session.

```bash
./scripts/stop-dev.sh           # stop containers + stop VM
./scripts/stop-dev.sh --soft    # stop containers only, leave VM running
```

### `snapshot-and-delete.sh` — Extended Break Cost Saver

For breaks >1 week. Pulls workspace locally (safety copy), snapshots the boot disk, then deletes the VM. Stops **all** billing. Requires interactive confirmation.

```bash
./scripts/snapshot-and-delete.sh
```

> **Note:** Only snapshots the boot disk. If you have a data disk attached (from `add-data-disk.sh`), it is not affected — it persists independently.

### `restore-from-snapshot.sh` — Restore from Snapshot

Recreates the VM from a snapshot. Uses the most recent snapshot by default, or a specific one.

```bash
./scripts/restore-from-snapshot.sh                    # most recent snapshot
./scripts/restore-from-snapshot.sh --snapshot=NAME    # specific snapshot
```

Always restores as a T4 instance. If you need A100, recreate using `create-instance.sh --a100` instead.

### `add-data-disk.sh` — Attach Persistent Data Disk

Creates and attaches a separate `pd-balanced` (standard SSD) data disk. Can be run at any time — does not need to be part of VM creation. The disk is independent of the VM lifecycle and survives VM deletion.

```bash
./scripts/add-data-disk.sh                # 500GB pd-balanced (default)
./scripts/add-data-disk.sh --size=200     # custom size in GB
```

The disk is formatted as ext4 and mounted at `/mnt/data`. Useful for witness logs, proof artifacts, and large datasets that should persist independently of the boot disk.

To detach or delete the disk later:
```bash
gcloud compute instances detach-disk zklora-dev --disk=zklora-dev-data --zone=us-central1-a
gcloud compute disks delete zklora-dev-data --zone=us-central1-a
```

### `ssh-instance.sh` — SSH into VM

Quick SSH into the VM host (not the Docker container). Useful for Docker management, checking disk space, and viewing logs.

```bash
./scripts/ssh-instance.sh              # plain SSH
./scripts/ssh-instance.sh --jupyter    # SSH + Jupyter port forward (localhost:8889)
```

### `sync-workspace.sh` — Push/Pull Workspace

Syncs the local `workspace/` directory to/from the GCP instance via SCP.

```bash
./scripts/sync-workspace.sh           # push local → instance
./scripts/sync-workspace.sh --pull    # pull instance → local
```

### `status.sh` — Environment Dashboard

Shows VM status, GPU utilization, running containers, disk usage, and Docker volume sizes in one command.

```bash
./scripts/status.sh
```

---

## Extended Breaks (>1 Week)

A stopped VM still bills ~$36/month for the 150GB disk. For breaks longer than a week:

```bash
# Snapshot disk + delete VM -- stops ALL billing
./scripts/snapshot-and-delete.sh

# When you're back
./scripts/restore-from-snapshot.sh
```

Snapshot storage costs ~$3.90/month instead of $36/month.

---

## Switching to A100 for Measurement Runs

When you're ready to take measurements:

1. Get Mark's sign-off on the experiment plan
2. Make sure you know how long the run will take
3. Stop and delete the T4 instance: `./scripts/snapshot-and-delete.sh`
4. Create A100 instance:
```bash
./scripts/create-instance.sh --a100
./scripts/bootstrap-instance.sh
```
5. **Run `./scripts/stop-dev.sh` immediately when the experiment finishes.**

Switch back to T4 for any further development after measurements are done.

---

## Security

- **Firewall**: only port 22 (SSH) is open. Jupyter runs over SSH tunnel, not a public port.
- **IAM scopes**: `cloud-platform` scope (gated by service account IAM roles).
- **Shielded VM**: vTPM and integrity monitoring enabled, secure boot disabled (required for NVIDIA drivers).
- **No API keys in the repo.** Use environment variables at runtime, not committed files.
- **Don't open additional ports** without thinking about it. The SSH tunnel approach for Jupyter is intentional.

---

## Docker Setup

### Dockerfile

Base image: `nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04`

Pre-installed:
- Python 3.10, PyTorch 2.1.0 (CUDA 11.8)
- ezkl, ONNX, ONNX Runtime
- Punica (from source, with SGMV CUDA kernels)
- zkLoRA (from source)
- Transformers, PEFT, Accelerate, Datasets
- FastAPI, Uvicorn (for proof delivery API)
- JupyterLab
- Dev tools (pytest, rich, tqdm, matplotlib, seaborn)

### Docker Compose

| Service   | Ports              | Description                          | Activation              |
|-----------|--------------------|--------------------------------------|-------------------------|
| `dev`     | 8888, 8000         | Main dev container (interactive)     | Default                 |
| `jupyter` | 8889               | JupyterLab server                    | `--profile jupyter`     |

---

## Volumes

Named Docker volumes persist across stop/start cycles and are included in snapshots.

| Volume               | Mounted at                    | Contents                        |
|----------------------|-------------------------------|---------------------------------|
| `model-weights`      | `/root/.cache/huggingface`    | HuggingFace model downloads     |
| `proof-artifacts`    | `/artifacts`                  | Witness tensors, proof files    |
| `experiment-outputs` | `/outputs`                    | Measurement results, plots      |

If a data disk is attached via `add-data-disk.sh`, it is mounted at `/mnt/data` on the VM host (outside Docker). You can use this for large persistent storage that survives VM deletion.

---

## Troubleshooting

**GPU not visible inside container**
```bash
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
```

**Punica CUDA kernels fail to compile**
First `import punica` compiles SGMV kernels -- takes a few minutes. If it fails, it's usually a CUDA version mismatch. Dockerfile pins CUDA 11.8 + PyTorch 2.1.0+cu118.

**Out of disk space**
```bash
docker system prune   # cleans unused images/containers (not volumes)
# If you need more disk:
gcloud compute disks resize zklora-dev-disk --size=300GB --zone=us-central1-a
```

**Budget alert fired**
Run `./scripts/status.sh`, then check GCP console → Billing → Cost breakdown.
Common causes: VM left running overnight, experiment still running, old snapshot not cleaned up.