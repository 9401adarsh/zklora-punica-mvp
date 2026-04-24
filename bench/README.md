# Phase 4b Bounded Benchmark Harness (Full PEFT)

This document explains how to run the bounded proving benchmark harness:

- Script: `bench/phase4b_bounded_peft.py`
- Goal: compare `cpu` vs `gpu`, worker threads, and request counts with a strict timeout.
- Proof path: real/full PEFT + real exporter + real EZKL (no fake proof runner in harness mode).

## What This Harness Measures

Per matrix point `(backend, threads, requests)` it will:

1. Create an isolated artifacts directory.
2. Start `MVPServer` in `proof_mode=every_request`.
3. Enqueue synthetic 3D inference packets (stable proof input generation).
4. Run `ProverWorker` with configured thread count.
5. Stop each point on completion or timeout.
6. Persist per-point `summary.json` and run-level summaries.

## Prerequisites

1. Dev container is running (or run directly in an environment with all deps).
2. Python deps used by `mvp_server` + EZKL + PEFT are installed in that environment.
3. Sufficient free disk space.

Disk note: full matrix runs can be large. In our recent run, one matrix consumed about `33G`.

## Quick Start

From repo root:

```bash
docker exec aa-zklora-dev python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends cpu,gpu \
  --threads 1,2 \
  --requests 5,20 \
  --timeout-sec 900 \
  --request-concurrency 1 \
  --output-root /workspace/artifacts/runs
```

The script prints the run directory at the end, for example:

```text
/workspace/artifacts/runs/phase4b-bounded-peft-YYYYMMDDTHHMMSSZ
```

## CLI Options

- `--backends` CSV, default: `cpu,gpu`
- `--threads` CSV, default: `1,2`
- `--requests` CSV, default: `5,20`
- `--timeout-sec` int, default: `900`
- `--request-concurrency` int, default: `1`
- `--output-root` path, default: `artifacts/runs`
- `--prompt` text prompt template
- `--seed` optional int
- `--hidden-dim` int, default: `768`
- `--seq-len` int, default: `1`
- `--base-model-id` model id/path, default: `distilgpt2`
- `--adapter-id` adapter id/path, default: `ng0-k1/distilgpt2-finetuned-es`
- `--setup-cache-root` optional path for persistent setup cache reuse across runs
- `--gpu-routing-policy` one of `strict|fallback`, default: `strict` in this harness

GPU acceleration note for `ezkl-gpu`: set `ENABLE_ICICLE_GPU=true` in GPU benchmark shells. Keep `ICICLE_SMALL_K` unset unless you are explicitly tuning small-`k` behavior.

## Canonical Benchmark Runbook (April 23, 2026)

This is the full terminal-only runbook for the CPU baseline + GPU bug-check cycle.
All commands are copy/paste ready.

### 0) Preflight (mandatory)

Confirm containers are running:

```bash
docker ps --format '{{.Names}}' | rg '^aa-zklora-(cpu|gpu)$'
```

Resolve local model/adapter snapshots and enforce offline mode in CPU container:

```bash
docker exec aa-zklora-cpu bash -lc '
set -euo pipefail
base=$(ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1)
adapter=$(ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1)
test -d "$base" && test -d "$adapter"
echo "BASE=$base"
echo "ADAPTER=$adapter"
echo "HF_HUB_OFFLINE=1"
echo "TRANSFORMERS_OFFLINE=1"
'
```

Resolve snapshots and verify GPU stack in GPU container:

```bash
docker exec aa-zklora-gpu bash -lc '
set -euo pipefail
base=$(ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1)
adapter=$(ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1)
test -d "$base" && test -d "$adapter"
export ENABLE_ICICLE_GPU=true
python3 - <<PY
import inspect
import ezkl
print("ezkl.prove signature:", inspect.signature(ezkl.prove))
PY
nvidia-smi
'
```

### 1) CPU baseline pack (mandatory order)

```bash
docker exec aa-zklora-cpu bash -lc '
set -euo pipefail
base=$(ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1)
adapter=$(ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

common="python3 /workspace/bench/phase4b_bounded_peft.py \
  --timeout-sec 7200 \
  --request-concurrency 1 \
  --output-root /workspace/artifacts/runs \
  --setup-cache-root /workspace/artifacts/setup-cache/phase4b-cpu-baseline \
  --base-model-id $base \
  --adapter-id $adapter \
  --gpu-routing-policy strict"

$common --backends cpu --threads 1 --requests 20
$common --backends cpu --threads 2 --requests 20
$common --backends cpu --threads 5 --requests 20
$common --backends cpu --threads 10 --requests 20
'
```

Optional extension:

```bash
docker exec aa-zklora-cpu bash -lc '
set -euo pipefail
base=$(ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1)
adapter=$(ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends cpu \
  --threads 10 \
  --requests 50 \
  --timeout-sec 7200 \
  --request-concurrency 1 \
  --output-root /workspace/artifacts/runs \
  --setup-cache-root /workspace/artifacts/setup-cache/phase4b-cpu-baseline \
  --base-model-id "$base" \
  --adapter-id "$adapter" \
  --gpu-routing-policy strict
'
```

### 2) GPU bug-check pack with 1s telemetry (mandatory)

```bash
docker exec aa-zklora-gpu bash -lc '
set -euo pipefail
mkdir -p /workspace/artifacts/runs/telemetry
base=$(ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1)
adapter=$(ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export ENABLE_ICICLE_GPU=true

run_with_telemetry () {
  backend="$1"; threads="$2"; requests="$3"; tag="$4"; policy="$5"
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  csv="/workspace/artifacts/runs/telemetry/${tag}-${ts}.csv"
  log="/workspace/artifacts/runs/telemetry/${tag}-${ts}.log"
  (
    echo "ts_utc,utilization_gpu,memory_used_mb,power_w,compute_pids" > "$csv"
    while true; do
      now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -n 1 | tr -d " ")
      mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -n 1 | tr -d " ")
      pwr=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits | head -n 1 | tr -d " ")
      pids=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | tr "\n" ";" | sed "s/;*$//")
      echo "$now,${util:-0},${mem:-0},${pwr:-0},\"${pids}\"" >> "$csv"
      sleep 1
    done
  ) &
  tele_pid=$!
  set +e
  python3 /workspace/bench/phase4b_bounded_peft.py \
    --backends "$backend" \
    --threads "$threads" \
    --requests "$requests" \
    --timeout-sec 7200 \
    --request-concurrency 1 \
    --output-root /workspace/artifacts/runs \
    --setup-cache-root /workspace/artifacts/setup-cache/phase4b-gpu-bugcheck \
    --base-model-id "$base" \
    --adapter-id "$adapter" \
    --gpu-routing-policy "$policy" > "$log" 2>&1
  rc=$?
  set -e
  kill "$tele_pid" 2>/dev/null || true
  wait "$tele_pid" 2>/dev/null || true
  echo "$tag rc=$rc csv=$csv log=$log"
  return $rc
}

# Use strict by default; switch to fallback only for explicit bug diagnosis.
run_with_telemetry cpu 1 20 gpucheck-cpu-t1-r20 strict
run_with_telemetry gpu 1 20 gpucheck-gpu-t1-r20 strict
run_with_telemetry cpu 2 20 gpucheck-cpu-t2-r20 strict
run_with_telemetry gpu 2 20 gpucheck-gpu-t2-r20 strict
'
```

### 3) GPU cold vs warm proof (mandatory)

```bash
docker exec aa-zklora-gpu bash -lc '
set -euo pipefail
base=$(ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1)
adapter=$(ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export ENABLE_ICICLE_GPU=true
cache_root=/workspace/artifacts/setup-cache/phase4b-gpu-coldwarm
rm -rf "$cache_root"

python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends gpu \
  --threads 1 \
  --requests 1 \
  --timeout-sec 7200 \
  --request-concurrency 1 \
  --output-root /workspace/artifacts/runs \
  --setup-cache-root "$cache_root" \
  --base-model-id "$base" \
  --adapter-id "$adapter" \
  --gpu-routing-policy strict

python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends gpu \
  --threads 1 \
  --requests 1 \
  --timeout-sec 7200 \
  --request-concurrency 1 \
  --output-root /workspace/artifacts/runs \
  --setup-cache-root "$cache_root" \
  --base-model-id "$base" \
  --adapter-id "$adapter" \
  --gpu-routing-policy strict
'
```

### 4) Post-run integrity checks

```bash
docker exec aa-zklora-cpu bash -lc \
"find /workspace/artifacts/runs -path '*/backend-*/summary.json' -print | sort"
```

```bash
docker exec aa-zklora-cpu python3 - <<PY
import glob, json
bad = []
for path in glob.glob("/workspace/artifacts/runs/phase4b-bounded-peft-*/backend-*/summary.json"):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    counts = data.get("status_counts", {})
    if counts.get("pending", 0) or counts.get("queued", 0):
        bad.append(path)
print("pending_or_queued_cases:", len(bad))
for p in bad:
    print(p)
PY
```

### 5) Extract slide-ready tables and confidence statement

```bash
docker exec aa-zklora-cpu python3 - <<PY
import glob, json
rows = []
for path in sorted(glob.glob("/workspace/artifacts/runs/phase4b-bounded-peft-*/backend-*/summary.json")):
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    trust = d.get("backend_trust", {})
    rows.append({
        "path": path,
        "backend": d.get("backend"),
        "threads": d.get("threads"),
        "requests": d.get("requests"),
        "req_per_sec": d.get("req_per_sec"),
        "ready": d.get("status_counts", {}).get("ready", 0),
        "failed": d.get("status_counts", {}).get("failed", 0),
        "backend_effective": trust.get("backend_effective"),
        "routing_supported": trust.get("backend_routing_supported"),
        "fallback_used": trust.get("backend_fallback_used"),
        "confidence": trust.get("confidence"),
    })
for r in rows:
    print(r)
PY
```

Confidence statement template:

```text
As of April 23, 2026, GPU proof execution confidence is LOW unless strict routing passes with backend_effective=gpu and no fallback.
```

### Expected outputs checklist

- Every mandatory case has `backend-*/summary.json`.
- No mandatory case ends with lingering `pending` or `queued`.
- CPU baseline table has all required thread points and one throughput headline.
- GPU bug-check rows include `backend_effective`, `backend_routing_supported`, and confidence.
- Cold/warm pair shows setup-cache miss then hit.

### Guardrail

Do not claim GPU performance unless runs were executed with `--gpu-routing-policy strict` and results show routable GPU (`backend_effective=gpu`, `backend_fallback_used=false`, confidence not `low`).

## Example Runs

### 1) Small smoke run

```bash
docker exec aa-zklora-dev python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends cpu \
  --threads 1 \
  --requests 2 \
  --timeout-sec 300 \
  --output-root /workspace/artifacts/runs
```

### 2) Compare thread scaling only

```bash
docker exec aa-zklora-dev python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends cpu \
  --threads 1,2,4 \
  --requests 20 \
  --timeout-sec 1200 \
  --output-root /workspace/artifacts/runs
```

### 3) GPU-only sweep

```bash
docker exec aa-zklora-dev bash -lc '
export ENABLE_ICICLE_GPU=true
python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends gpu \
  --threads 1,2 \
  --requests 5,20,40 \
  --timeout-sec 1200 \
  --output-root /workspace/artifacts/runs
'
```

## Cached Setup Mode (Opt-In)

Use `--setup-cache-root` to persist setup artifacts across timestamped benchmark runs.

- First run with a fresh cache root: setup cache misses are expected.
- Re-running with the same cache root and same fingerprint inputs (backend/model/adapter/module/EZKL version): setup cache hits are expected.
- If fingerprint inputs change, cache entries are rebuilt automatically.

Example (shared cache root):

```bash
docker exec aa-zklora-dev bash -lc '
export ENABLE_ICICLE_GPU=true
python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends gpu \
  --threads 1 \
  --requests 5 \
  --timeout-sec 1200 \
  --setup-cache-root /workspace/artifacts/setup-cache/phase4b \
  --output-root /workspace/artifacts/runs
'
```

Note: cache reuse across runs only works when `--setup-cache-root` points to a stable path.

## Output Layout

For a run directory:

```text
artifacts/runs/phase4b-bounded-peft-<timestamp>/
  summary.json
  summary.md
  backend-<backend>-threads-<n>-requests-<m>/
    summary.json
    runtime_artifacts/
      proof/proof_store.json
      proofs/...
      proof_setup/...
```

### Important status values

- `completed`: all requests reached terminal state for that case.
- `timed_out`: case hit timeout before all requests completed.
- `failed_fast`: case failed quickly (for example startup/runtime error).

## Reading Results

Use each case `summary.json`:

- `status_counts`: how many ended `ready`, `failed`, `pending`, `queued`
- `worker_wall_s`: case wall time
- `req_per_sec`: throughput (completed cases, or partial throughput for timed-out cases)
- `prover_duration_ms`: recorded worker-side proof duration stats
- `stage_timing_s`: average setup/witness/prove/total stage timings when available
- `setup_cache`: cache telemetry (`enabled`, `hits`, `misses`, `hit_rate`) for setup reuse

## Run Tests In CPU/GPU Containers

Use this when you want to validate the project test suite in explicit CPU and GPU container modes.

Prerequisites:
- Images are present (`aa-zklora-dev:ezkl` and `aa-zklora-dev:ezkl-gpu`).
- Run from repo root.

### GPU container test run

Spin up a GPU container:

```bash
docker rm -f aa-zklora-gpu-test 2>/dev/null || true
docker run -d --name aa-zklora-gpu-test --gpus all \
  -v "$PWD":/workspace \
  -v "$PWD/punica":/opt/punica \
  -v "$PWD/zklora":/opt/zkLoRA \
  -w /workspace \
  aa-zklora-dev:ezkl-gpu sleep infinity
```

Run tests:

```bash
docker exec aa-zklora-gpu-test python3 -m pytest -q mvp_server/tests
```

Cleanup:

```bash
docker rm -f aa-zklora-gpu-test
```

### CPU container test run

Spin up a CPU container:

```bash
docker rm -f aa-zklora-cpu-test 2>/dev/null || true
docker run -d --name aa-zklora-cpu-test \
  -v "$PWD":/workspace \
  -v "$PWD/punica":/opt/punica \
  -v "$PWD/zklora":/opt/zkLoRA \
  -w /workspace \
  aa-zklora-dev:ezkl sleep infinity
```

Run tests:

```bash
docker exec aa-zklora-cpu-test python3 -m pytest -q mvp_server/tests
```

Cleanup:

```bash
docker rm -f aa-zklora-cpu-test
```

### Notes

- Use `mvp_server/tests` target to avoid collecting third-party submodule tests under `punica/third_party`.
- If you run `pytest` from repo root without a target, test discovery may include unrelated external tests.

## Troubleshooting

### 1) `No space left on device`

Symptom: EZKL/setup/export/proof_store write errors (`Errno 28`).

Check space:

```bash
df -h /
du -sh artifacts/runs/phase4b-bounded-peft-*
```

Clean old runs:

```bash
rm -rf artifacts/runs/phase4b-bounded-peft-<old-timestamp>
```

### 2) Many `timed_out` points

Increase bound:

```bash
--timeout-sec 1800
```

Also test smaller matrix first (`requests=5`) and scale up.

### 3) GPU unavailable

If backend is `gpu` and CUDA is unavailable, proofs should fail with a clear runtime message.

### 4) Hugging Face adapter download/TLS failure

Symptom: errors like `MaxRetryError` / `SSLError` while requesting `adapter_model.safetensors` from `huggingface.co`.

Use a local adapter path to avoid network fetches during benchmark runs:

```bash
--adapter-id /workspace/path/to/local/adapter
```

You can also override base model if needed:

```bash
--base-model-id distilgpt2
```

If you already have both model and adapter cached in-container, run fully offline to avoid HF TLS/network flakiness:

Verify cache paths exist first:

```bash
docker exec aa-zklora-dev bash -lc '
ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1
ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1
'
```

```bash
docker exec aa-zklora-dev bash -lc '
base=$(ls -1d /root/.cache/huggingface/hub/models--distilgpt2/snapshots/* | head -n 1)
adapter=$(ls -1d /root/.cache/huggingface/hub/models--ng0-k1--distilgpt2-finetuned-es/snapshots/* | head -n 1)
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ENABLE_ICICLE_GPU=true \
python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends gpu \
  --threads 8 \
  --requests 100 \
  --timeout-sec 7200 \
  --request-concurrency 1 \
  --output-root /workspace/artifacts/runs \
  --base-model-id "$base" \
  --adapter-id "$adapter"
'
```

### 5) Verify EZKL backend support

Some EZKL versions expose `backend` in `ezkl.prove`, others do not.
If backend is not supported, proving may still run but without GPU backend routing.

```bash
docker exec aa-zklora-dev python3 - <<'PY'
import inspect
import ezkl
print(inspect.signature(ezkl.prove))
PY
```

### 6) Map GPU PID to benchmark run

Use this when `nvidia-smi` shows GPU processes and you want to know which run owns each PID.

Map GPU PIDs to full commands:

```bash
nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits \
| tr -d ' ' \
| xargs -I{} ps -fp {}
```

If running inside Docker, list container processes with host PIDs:

```bash
docker top aa-zklora-dev -eo pid,ppid,cmd
```

Container-scoped variant:

```bash
docker exec aa-zklora-dev bash -lc \
"nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits \
| tr -d ' ' \
| xargs -I{} ps -fp {}"
```

### 7) Stop benchmark runs cleanly

Stop all `phase4b_bounded_peft.py` processes in the container:

```bash
# Graceful stop first
docker exec aa-zklora-dev bash -lc \
"pkill -TERM -f 'phase4b_bounded_peft.py' || true; sleep 3"

# Force-kill any leftovers
docker exec aa-zklora-dev bash -lc \
"pkill -KILL -f 'phase4b_bounded_peft.py' || true"
```

Verify nothing is left:

```bash
docker exec aa-zklora-dev bash -lc \
"ps -eo pid,ppid,cmd | grep phase4b_bounded_peft.py | grep -v grep || true"
```

Kill one specific run by PID:

```bash
docker top aa-zklora-dev -eo pid,ppid,cmd
docker exec aa-zklora-dev kill -TERM <pid>
# if needed
docker exec aa-zklora-dev kill -KILL <pid>
```

### 8) Incomplete top-level summary after interruption

If interrupted mid-run, case-level `summary.json` files may still be usable. Use those for partial analysis.

## Tips For Better CPU vs GPU Comparison

1. Run with larger `requests` (for example `40+`) so one-time setup cost is amortized.
2. Keep `seq_len` / problem size realistic for your target workload.
3. Compare both:
   - end-to-end wall time
   - stage-level timings (`setup`, `witness`, `prove`)
4. Treat first request separately (cold setup) from steady-state requests.
5. Keep disk healthy; low-space conditions can distort timings.
