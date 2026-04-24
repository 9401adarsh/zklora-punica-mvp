## Check-In Plan Update (March 30, 2026): MVP Design, Backend Validation, and GPU-Utilization Risk

### Summary
- Keep the 10-minute check-in, but add three explicit additions:
1. A comparison plan for original zkLoRA benchmark on `ezkl` (CPU path baseline; you wrote “exkl”) vs `ezkl-gpu`.
2. A proof-backend validation section focused on “is proving actually on GPU?”.
3. A dedicated design-justification slide for multithreaded worker + backend switch (`cpu|gpu`).

### Key Changes to Talk Track
1. `0:00-1:00` Problem + objective: verifiable LoRA serving with strict proof semantics.
2. `1:00-2:30` MVP server design recap: async pipeline, status lifecycle, decoupled inference/proof.
3. `2:30-3:45` **Design Justification slide (new):**
   - Why threads: throughput gain via overlapping independent proof jobs.
   - Why backend switch: preserve correctness parity while enabling CPU/GPU measurement and routing.
   - Why this should work: same proof contract, different execution path + concurrency control.
4. `3:45-5:30` Phase 4b bounded harness methodology + partial results.
5. `5:30-7:00` **Original zkLoRA benchmark comparison (new):**
   - Run/compare original benchmark under `ezkl` vs `ezkl-gpu`.
   - Report deltas in wall time, prove-stage time, and stability/failure signatures.
6. `7:00-8:15` **GPU backend trust check (new):**
   - Current concern: backend may not actually be executing on GPU.
   - Validation evidence plan: runtime backend flag behavior, CUDA visibility, GPU process/PID mapping during proving, and stage-time shift expectations.
   - Mention current VM run is in progress and results are pending.
7. `8:15-9:30` Blockers + under-utilization hypotheses + prioritized next experiments.
8. `9:30-10:00` Discussion asks: confirm diagnosis path and experiment ordering.

### Public Interfaces / Evidence Contracts
- Add one “backend validation” evidence table with columns:
  - `Run ID`, `Backend intent`, `CUDA visible`, `GPU PID observed during prove`, `prove-stage delta vs CPU`, `Confidence`.
- Add one “original benchmark comparison” table:
  - `Benchmark case`, `ezkl`, `ezkl-gpu`, `% delta`, `notes`.
- Label each statement as `Observed`, `Inferred`, or `Planned`.

### Test and Validation Scenarios to Include
1. Same benchmark inputs, `ezkl` vs `ezkl-gpu`, fixed environment.
2. GPU-intended run with concurrent `nvidia-smi`/PID mapping to active prove process.
3. CPU-intended control run to verify absence of GPU prove activity.
4. Thread comparison (`1` vs `2`) on same workload to isolate throughput impact from backend impact.
5. Cold vs steady-state split to avoid misattributing setup costs to GPU inefficiency.

### Assumptions and Defaults
- “exkl” is treated as `ezkl` CPU-capable baseline; `ezkl-gpu` is GPU-capable path.
- Current VM benchmark may finish before the check-in; if not, present partial results + methodology + live risk statement.
- Main meeting outcome remains: validate backend/GPU diagnosis and lock next experiment order.
