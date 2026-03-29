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
docker exec aa-zklora-dev python3 /workspace/bench/phase4b_bounded_peft.py \
  --backends gpu \
  --threads 1,2 \
  --requests 5,20,40 \
  --timeout-sec 1200 \
  --output-root /workspace/artifacts/runs
```

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
- `req_per_sec`: throughput (for completed cases)
- `prover_duration_ms`: recorded worker-side proof duration stats
- `stage_timing_s`: average setup/witness/prove/total stage timings when available

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

### 4) Verify EZKL backend support

Some EZKL versions expose `backend` in `ezkl.prove`, others do not.
If backend is not supported, proving may still run but without GPU backend routing.

```bash
docker exec aa-zklora-dev python3 - <<'PY'
import inspect
import ezkl
print(inspect.signature(ezkl.prove))
PY
```

### 5) Map GPU PID to benchmark run

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

### 6) Stop benchmark runs cleanly

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

### 7) Incomplete top-level summary after interruption

If interrupted mid-run, case-level `summary.json` files may still be usable. Use those for partial analysis.

## Tips For Better CPU vs GPU Comparison

1. Run with larger `requests` (for example `40+`) so one-time setup cost is amortized.
2. Keep `seq_len` / problem size realistic for your target workload.
3. Compare both:
   - end-to-end wall time
   - stage-level timings (`setup`, `witness`, `prove`)
4. Treat first request separately (cold setup) from steady-state requests.
5. Keep disk healthy; low-space conditions can distort timings.
