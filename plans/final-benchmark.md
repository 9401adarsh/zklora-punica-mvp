# Final Benchmark Results - CPU Baseline + GPU Bug Check

## Run Artifacts
- CPU baseline pack run: `/workspace/artifacts/runs/phase4b-bounded-peft-20260422T223141Z`
- GPU bug-check runlist: `/workspace/artifacts/runs/telemetry/gpu_bugcheck_runlist_20260423T000537Z.csv`
- GPU bug-check runs:
1. `/workspace/artifacts/runs/phase4b-bounded-peft-20260423T000537Z` (cpu, t=1, r=20)
2. `/workspace/artifacts/runs/phase4b-bounded-peft-20260423T003850Z` (gpu, t=1, r=20)
3. `/workspace/artifacts/runs/phase4b-bounded-peft-20260423T011212Z` (cpu, t=2, r=20)
4. `/workspace/artifacts/runs/phase4b-bounded-peft-20260423T012716Z` (gpu, t=2, r=20)
- Cold/warm GPU runs:
1. Cold: `/workspace/artifacts/runs/phase4b-bounded-peft-20260423T014417Z`
2. Warm: `/workspace/artifacts/runs/phase4b-bounded-peft-20260423T014901Z`

## CPU Baseline Table (Throughput-First)
| threads | requests | req_per_sec | ready | failed | ready_rate | status | notable_error |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 20 | 0.010338 | 20 | 0 | 1.00 | completed | - |
| 2 | 20 | 0.014695 | 16 | 4 | 0.80 | completed | `export: expected at least one ONNX artifact after export` |
| 5 | 20 | 0.017747 | 13 | 7 | 0.65 | completed | `export: expected at least one ONNX artifact after export` |
| 10 | 20 | 0.017619 | 13 | 7 | 0.65 | completed | `export: expected at least one ONNX artifact after export` |

### Headline CPU Metric (per selected rule: throughput-first)
- **Headline CPU throughput:** `0.017747 req/s` at `threads=5, requests=20`
- Reliability at headline point: `13 ready / 7 failed` (`0.65 ready_rate`)

## GPU Bug-Status Table (Matched Pairs)
### Inputs used for trust signals
- `backend_intent`: from run backend (`cpu|gpu`)
- `ezkl_backend_kwarg_supported`: from captured EZKL signature; `False` for `(witness=Ellipsis, model=Ellipsis, pk_path=Ellipsis, proof_path=None, proof_type=Ellipsis, srs_path=None)`
- `gpu_pid_correlation_rate`: from 1s telemetry (`non-empty compute_pids samples / total samples`)
- `telemetry_spike_during_prove`: heuristic over run telemetry (`max util >= 5%` or `max power >= 45W`)

| pair | backend | threads | requests | req_per_sec | ready | failed | backend_intent | ezkl_backend_kwarg_supported | gpu_pid_correlation_rate | telemetry_spike_during_prove | trust |
|---|---|---:|---:|---:|---:|---:|---|---|---:|---|---|
| t=1 matched | cpu | 1 | 20 | 0.010043 | 20 | 0 | cpu | False | 0.997188 | no | n/a |
| t=1 matched | gpu | 1 | 20 | 0.009996 | 20 | 0 | gpu | False | 0.998320 | no | low |
| t=2 matched | cpu | 2 | 20 | 0.022152 | 10 | 10 | cpu | False | 0.993812 | no | n/a |
| t=2 matched | gpu | 2 | 20 | 0.020053 | 11 | 9 | gpu | False | 0.995516 | no | low |

### Notes
- `gpu_pid_correlation_rate` is high for both CPU and GPU runs, so PID presence alone is not discriminative here.
- `telemetry_spike_during_prove` was `no` for all four bug-check runs under this heuristic.

## Known Issue: GPU Intent Can Prove on CPU
- GPU backend intent is set in benchmark configuration, but the current EZKL API signature does not expose backend routing.
- Result: the system can silently prove on CPU without explicit failure when `prover_backend=gpu` is selected.
- Therefore GPU performance claims from this run set are invalid and should not be used as evidence of GPU proving.

### Evidence
- Captured `ezkl.prove` signature lacks a `backend` argument in the active environment.
- GPU-tagged and CPU-control runs show no meaningful compute separation in telemetry.
- Backend confidence remains `low` for GPU-tagged points.

### Required Next Step Before Any GPU Claim
- Enforce fail-fast when `prover_backend=gpu` and backend routing is unsupported so GPU intent cannot silently prove on CPU.

## GPU Cold vs Warm (Cache Root Reuse)
Cache root: `/workspace/artifacts/setup-cache/phase4b-gpu-coldwarm`

| run | req_per_sec | setup_s_avg | witness_s_avg | prove_s_avg | cache_hits | cache_misses | cache_hit_rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold (`t=1,r=1`) | 0.003521 | 191.640715 | 4.632455 | 84.239449 | 0 | 1 | 0.0 |
| warm (`t=1,r=1`) | 0.010442 | 0.000000 | 4.897318 | 87.395499 | 1 | 0 | 1.0 |

## Pure Inference and 1-Token Latency (Separate Microbenchmark)
Measured on **April 23, 2026** using `distilgpt2`, `n=30` samples after warmup.

Scope clarification:
- `prefill inference latency` = `ModelRuntime.infer_prefill(...)` path (single forward prefill, no proof execution).
- `1-token generation latency` = separate autoregressive microbenchmark using `model.generate(max_new_tokens=1)` plus decode.
- These numbers are not from the phase4b proof-throughput harness and should be interpreted separately.

| device | prefill_mean_ms | prefill_p50_ms | prefill_p95_ms | gen1_mean_ms | gen1_p50_ms | gen1_p95_ms |
|---|---:|---:|---:|---:|---:|---:|
| cpu | 26.83 | 26.73 | 29.54 | 28.43 | 28.61 | 30.80 |
| gpu (Tesla T4) | 8.18 | 8.14 | 8.56 | 8.68 | 8.62 | 9.16 |

### Notes
- MVP serving proof scope remains `prefill_only` at one target attention module.
- Current `POST /infer` path in this MVP does not run full autoregressive decoding; the 1-token values above come from a separate direct generation probe.

## Integrity Checks
- CPU baseline mandatory points: all 4 case `summary.json` files present.
- GPU bug-check mandatory points: all 4 case `summary.json` files present.
- Cold/warm mandatory pair: both case `summary.json` files present.
- No lingering `pending` or `queued` statuses in final case summaries for mandatory runs.

## Backend Confidence Statement
As of **April 23, 2026**, GPU proof execution confidence is **low** based on matched control runs in this benchmark cycle: intent was set to `gpu`, but backend kwarg routing was unsupported in this EZKL signature and telemetry did not show clear prove-window GPU spikes relative to controls.
