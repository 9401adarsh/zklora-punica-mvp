## Phase-3 Plan: Telemetry, Load Frontier, and Gate-3 Evidence

### Summary
Implement Phase-3 as an in-process benchmark and observability expansion on top of current Phase-2 server/worker architecture.  
The goal is to produce reproducible Gate-3 artifacts and a stability frontier report using a deterministic synthetic profile and full sampling matrix (`every_request`, `sampled N={2,4,8,16,32}`), with receipt-to-proof lag computed from server/worker timestamps.

### Implementation Changes
- **Telemetry and timing model**
  - Extend proof lifecycle records to include authoritative timestamps: request accepted, sampled decision, witness persisted/job enqueued, worker claim (`pending`), terminal (`ready|failed|dropped_overload|not_sampled`).
  - Add latency/throughput counters and rolling hist data needed for Gate-3 outputs:
    - infer latency p50/p95
    - proofs/sec
    - receipt-to-proof lag p50/p95
    - drop counts by status
    - witness/proof queue depth trend samples over time
  - Keep `/metrics` snapshot-compatible, but include Phase-3 fields needed by load harness export.

- **Load generation harness (in-process MVPServer)**
  - Implement synthetic prefill runner with:
    - fixed deterministic prompt
    - stepped concurrency sweep
    - warmup 2 min + measure 5 min per operating point
    - full matrix over proof modes and sample values
  - Run worker process concurrently in benchmark mode (single worker, current Phase-2 handoff semantics).
  - Persist per-run artifacts under `artifacts/runs/<timestamp>/`:
    - `metrics.jsonl` (time-series samples)
    - `config_snapshot.json`
    - `run_manifest.json` (reproducibility metadata)
    - optional raw per-request event log for audit/debug

- **Analysis/report pipeline**
  - Implement analyzer to compute:
    - max stable req/s frontier point(s)
    - infer latency p50/p95
    - proofs/sec
    - queue depth trend summaries (slope + max)
    - receipt-to-proof lag p50/p95
    - drop counts by status
  - Generate `analysis_summary.md` with:
    - synthetic matrix table
    - selected stable sampled operating point
    - frontier selection rationale
    - reproducibility section keyed to run manifest

- **Stability classification (locked)**
  - Stable point criteria:
    - queue depth trend non-divergent (`slope <= epsilon`)
    - drop rate <= threshold
  - Defaults for implementation:
    - `epsilon = 0.1 queue-items/sec` (linear fit over measure window)
    - drop-rate threshold = `1.0%` of infer requests
  - Report must explicitly show whether each point passed/failed and why.

### Public/Interface Additions
- `ProofRecord` (or equivalent status backend payload) gains lifecycle timestamps required for lag computation.
- Benchmark CLI interfaces become concrete:
  - synthetic run command with mode/sample/concurrency sweep inputs
  - mixed-prompt run command using best sampled `N` from synthetic results
  - analyzer command that consumes run directories and writes `analysis_summary.md`
- `run_manifest.json` must include: commit SHA, container image/digest, CUDA/driver/runtime, model+adapter ids, proof mode/sample config, seeds, hardware descriptor.

### Test Plan
- **Unit**
  - Timestamp capture correctness for each lifecycle transition.
  - Lag computation correctness (enqueue-to-terminal and accepted-to-terminal variants).
  - Stability classifier behavior on controlled queue/drop datasets.
  - Percentile/stat aggregation sanity tests (p50/p95/proofs-sec/drop rate).

- **Integration**
  - Synthetic load run writes all required run artifacts with valid schemas.
  - Analyzer consumes generated run directory and emits complete `analysis_summary.md`.
  - Queue trend and lag metrics are present for sampled and every-request modes.
  - Worker-active benchmark execution does not break existing status semantics.

- **Gate-3 dry-run validation**
  - Execute at least one sampled point + one every-request point end-to-end in container.
  - Confirm reproducibility manifest completeness.
  - Confirm report includes every Gate-3 required metric section.

### Assumptions and Defaults
- Load driver is **in-process** (`MVPServer` direct calls), not HTTP.
- Matrix scope is **full strict Gate-3** (`every_request` + `sampled N={2,4,8,16,32}`).
- Lag source of truth is **server/worker persisted timestamps**.
- Synthetic profile is **fixed prompt + stepped concurrency**.
- Stability rule is **queue-bounded + low drops** with defaults:
  - queue slope epsilon `0.1 items/sec`
  - drop-rate threshold `<=1.0%`
- Single worker process is used for Phase-3 benchmarking (consistent with current Phase-2 implementation).
