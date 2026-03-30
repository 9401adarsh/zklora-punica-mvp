# MVP Check-In Deck Plan (March 30, 2026)

## 1) 10-Minute Talk Track

### Slide 1 (0:00-1:00) - Goal and Scope
- **Objective:** frame the independent study target: verifiable LoRA serving with strict proof semantics.
- **Talk points:**
  - `Observed`: async proof pipeline is integrated into `mvp_server`.
  - `Planned`: validate proof performance path and GPU backend trust.
  - `Planned`: converge on bottleneck-focused next experiments.

### Slide 2 (1:00-2:30) - MVP Server Design Recap
- **Objective:** show the current architecture and invariant.
- **Talk points:**
  - `Observed`: `POST /infer` returns receipt immediately.
  - `Observed`: worker handles `queued -> pending -> ready|failed`.
  - `Observed`: design intent is inference/proof decoupling.
  - `Inferred`: current bottlenecks are mostly in proof path and runtime overhead, not API contract shape.

### Slide 3 (2:30-3:45) - Design Justification (New)
- **Objective:** justify why multithreading + backend routing is the right MVP lever.
- **Talk points:**
  - `Observed`: proof jobs are independent and queue-backed.
  - `Inferred`: thread pool should improve throughput by overlapping proof work, even if single-proof latency stays similar.
  - `Observed`: backend switch (`cpu|gpu`) keeps API and proof semantics unchanged while enabling controlled A/B runs.
  - `Inferred`: this isolates two variables cleanly:
    - parallelism effect (`threads=1` vs `2`)
    - compute backend effect (`ezkl` CPU path vs `ezkl-gpu` path)

### Slide 4 (3:45-5:30) - Phase 4b Harness + Partial Results
- **Objective:** present method first, then available evidence.
- **Talk points:**
  - `Observed`: bounded matrix harness exists for `backend x threads x requests`.
  - `Observed`: output includes `req_per_sec`, status counts, and stage timings.
  - `Observed`: some points are complete, others are still running/pending.
  - `Planned`: finish missing matrix cells for stronger backend confidence.

### Slide 5 (5:30-7:00) - Original zkLoRA Benchmark: `ezkl` vs `ezkl-gpu` (New)
- **Objective:** compare baseline zkLoRA path outside MVP harness.
- **Talk points:**
  - `Planned`: run same sample flow with identical inputs and environment, changing only EZKL package/runtime.
  - `Planned`: compare wall time, proof stage time, and failure signatures.
  - `Inferred`: if `ezkl-gpu` truly routes prove to GPU, stage-level profile and runtime behavior should differ from CPU baseline.

### Slide 6 (7:00-8:15) - GPU Backend Trust Check (New)
- **Objective:** address the core risk: “is proving actually on GPU?”
- **Talk points:**
  - `Observed`: concern remains open while VM run is in progress.
  - `Planned`: validate with:
    - CUDA visibility checks
    - runtime backend intent
    - GPU PID observation during prove
    - stage-time delta against CPU control
  - `Inferred`: no single signal is sufficient; confidence should come from consistent multi-signal evidence.

### Slide 7 (8:15-9:30) - Blockers and Under-Utilization Hypotheses
- **Objective:** show concrete blockers and experimental next steps.
- **Talk points:**
  - `Observed`: GPU under-utilization concern persists.
  - `Inferred`: likely contributors include setup amortization, short runs, thread contention, and I/O overhead.
  - `Planned`: prioritize runs that separate cold-start vs steady-state and backend vs threading effects.

### Slide 8 (9:30-10:00) - Discussion Asks
- **Objective:** end with decisions needed from professor.
- **Talk points:**
  - validate diagnosis approach for GPU backend trust.
  - validate next experiment ordering.
  - confirm success criteria for “backend confidence” in next check-in.

## 2) Evidence Contracts (Use in Slides 5-6)

### Backend Validation Table

| Run ID | Backend intent | CUDA visible | GPU PID observed during prove | prove-stage delta vs CPU | Confidence |
|---|---|---|---|---|---|
| run-001 | gpu | yes/no | yes/no (+pid) | +/-% | low/med/high |
| run-002 | cpu | yes/no | yes/no (+pid) | baseline | low/med/high |
| run-003 | gpu | yes/no | yes/no (+pid) | +/-% | low/med/high |

### Original zkLoRA Comparison Table

| Benchmark case | ezkl | ezkl-gpu | % delta | notes |
|---|---:|---:|---:|---|
| sample-flow-1 wall time (s) |  |  |  |  |
| sample-flow-1 prove stage (s) |  |  |  |  |
| sample-flow-1 verify stage (s) |  |  |  |  |
| stability/errors |  |  |  |  |

## 3) Validation Scenarios to Include

1. Same benchmark inputs under `ezkl` and `ezkl-gpu`, fixed environment.
2. GPU-intended run with concurrent GPU PID tracking during proof generation.
3. CPU-intended control run to verify no proof-time GPU PID signal.
4. `threads=1` vs `threads=2` run on same workload to isolate threading effect.
5. Cold-start vs steady-state reporting split so setup cost is not misattributed.

## 4) Execution Appendix (Commands)

### A. Capture active EZKL package/runtime

```bash
python3 -m pip show ezkl || true
python3 -m pip show ezkl-gpu || true
python3 - <<'PY'
import inspect
import ezkl
print("ezkl module:", ezkl.__file__)
print("ezkl.prove signature:", inspect.signature(ezkl.prove))
PY
```

### B. CPU baseline run (`ezkl`)

```bash
# package switch (CPU baseline)
python3 -m pip install --no-cache-dir --force-reinstall ezkl

# terminal 1: contributor (A)
python3 /workspace/zklora/src/scripts/lora_contributor_sample_script.py \
  --host 127.0.0.1 \
  --port_a 30000 \
  --base_model distilgpt2 \
  --lora_model_id ng0-k1/distilgpt2-finetuned-es \
  --out_dir /workspace/artifacts/zkbench/ezkl_cpu

# terminal 2: base user (B) + wall clock
/usr/bin/time -f "wall_s=%e" \
python3 /workspace/zklora/src/scripts/base_model_user_sample_script.py \
  --host_a 127.0.0.1 \
  --port_a 30000 \
  --base_model distilgpt2
```

### C. GPU-path run (`ezkl-gpu`)

```bash
# package switch (GPU path)
python3 -m pip install --no-cache-dir --force-reinstall ezkl-gpu \
  || python3 -m pip install --no-cache-dir --force-reinstall /path/to/ezkl_gpu.whl

# terminal 1: contributor (A)
python3 /workspace/zklora/src/scripts/lora_contributor_sample_script.py \
  --host 127.0.0.1 \
  --port_a 30000 \
  --base_model distilgpt2 \
  --lora_model_id ng0-k1/distilgpt2-finetuned-es \
  --out_dir /workspace/artifacts/zkbench/ezkl_gpu

# terminal 2: base user (B) + wall clock
/usr/bin/time -f "wall_s=%e" \
python3 /workspace/zklora/src/scripts/base_model_user_sample_script.py \
  --host_a 127.0.0.1 \
  --port_a 30000 \
  --base_model distilgpt2
```

### D. Trust check while GPU run is active

```bash
# Watch GPU compute processes
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory \
  --format=csv,noheader -l 1

# Map active GPU PIDs to commands
nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits \
| tr -d ' ' \
| xargs -I{} ps -fp {}
```

### E. Optional proof verification timing

```bash
/usr/bin/time -f "verify_wall_s=%e" \
python3 /workspace/zklora/src/scripts/verify_proofs.py \
  --proof_dir /workspace/artifacts/zkbench/ezkl_gpu \
  --verbose
```

## 5) Live Risk Statement (If VM run is still active)

- `Observed`: benchmark run is currently in progress on VM.
- `Observed`: available results are partial.
- `Planned`: use partial evidence + fixed methodology in this check-in, then publish completed matrix and backend-confidence update after run completion.
