# V1 CPU/GPU Split Pipeline Plan (Single-GPU, Exposed Stage Statuses)

## Summary
Refactor proof execution into a staged pipeline so CPU prep overlaps with GPU proving, while exposing explicit lifecycle statuses and preserving partial metrics for timed-out runs.

Scope is fixed to:
- Single-GPU execution (`proof_gpu_workers=1`)
- Exposed statuses: `cpu_preparing`, `cpu_ready`, `gpu_running`
- In-process threaded pipeline (no multi-process or multi-GPU scheduler in v1)

## Architecture + Timeline Diagrams

### Current Design (Today)
```mermaid
flowchart LR
  Q[queued] --> P[pending]
  P --> C[CPU prep: load/resolve/export/setup/witness]
  C --> G[GPU prove]
  G --> R[ready|failed]
```

### Proposed V1 Design
```mermaid
flowchart LR
  Q[queued] --> CP[cpu_preparing]
  CP --> CR[cpu_ready]
  CR --> GR[gpu_running]
  GR --> R[ready|failed]
```

### Execution Timeline Comparison
```text
Current (per-thread mixed CPU+GPU)
t0    [CPU prep J1][GPU prove J1]------------------done
t1                [CPU prep J2][GPU prove J2]------done
t2                                [CPU prep J3][GPU prove J3]

Proposed (pipelined)
CPU:  [prep J1][prep J2][prep J3][prep J4]...
GPU:           [prove J1]------[prove J2]------[prove J3]...
```

## Implementation Changes
- Refactor [prover_worker.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/prover_worker.py) into 3 staged components.
- Stage A claim loop:
  - Claim manifest jobs.
  - Set status `cpu_preparing`.
  - Push to bounded `claimed_queue`.
- Stage B CPU prep pool (`proof_cpu_prep_threads`):
  - Execute load/resolve/export/setup/witness work.
  - Emit `PreparedProofJob` to bounded `prepared_queue`.
  - Set status `cpu_ready`.
  - On exception, terminal `failed` with `error_code=prep_failed`.
- Stage C GPU prove worker (`proof_gpu_workers=1`):
  - Set status `gpu_running`.
  - Execute prove-only path.
  - On success set `ready` with artifacts/timings.
  - On exception set `failed` with `error_code=prove_failed`.
- Add adapter split in [zklora_adapter.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/zklora_adapter.py):
  - `prepare(job) -> PreparedProofJob`
  - `prove_prepared(prepared_job) -> ProveResult`
  - Keep `prove(job)` as compatibility wrapper in v1.
- Update [proof_store.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/proof_store.py):
  - Transition graph for `queued -> cpu_preparing -> cpu_ready -> gpu_running -> ready|failed`
  - Timestamp keys: `cpu_prep_started_at`, `cpu_prep_finished_at`, `gpu_prove_started_at`, `gpu_prove_finished_at`.
- Keep benchmark timeout summary behavior already patched:
  - Partial `req_per_sec`, `stage_timing_s`, `prover_duration_ms` from proof store.

## Public Interface / Config Additions
- `ProofRecord.status` adds:
  - `cpu_preparing`, `cpu_ready`, `gpu_running`
- `AppConfig` adds:
  - `proof_cpu_prep_threads` default `max(1, proof_worker_threads)`
  - `proof_gpu_workers` default `1` (validated to `1` in v1)
  - `proof_claim_queue_size` default `64`
  - `proof_prepared_queue_size` default `16`

## What To Expect
- Observable behavior:
  - More granular status progression in proof records and API responses.
  - `pending` no longer overloaded as “everything before terminal.”
- Throughput behavior (single GPU):
  - If CPU prep is non-trivial, expect measurable gain from overlap.
  - If GPU prove dominates entirely, expect small gain.
- Practical expectation band for this codepath:
  - Typical: `+10% to +35%` throughput when prep is a meaningful fraction.
  - Best case (prep-heavy): up to `~50%`.
  - Worst case (prove-only bottleneck): near `0%`.
- Validation criteria for success:
  - GPU worker utilization visibly steadier.
  - Inter-ready spacing trends closer to prove duration than prep+prove duration.
  - Timeout summaries retain partial performance metrics, not zeros.

## Test Plan
- Unit:
  - New proof store transitions and timestamp fields.
  - Adapter `prepare` and `prove_prepared` success/failure paths.
  - Queue backpressure and stage shutdown behavior.
- Integration:
  - End-to-end status progression with terminal correctness.
  - Timeout case emits partial metrics with non-empty stage stats when available.
- Benchmark verification:
  - Run old-vs-new matrix on same container/GPU settings.
  - Compare `req_per_sec`, stage timings, and status distribution.

## Assumptions / Defaults
- Exposed stage statuses are acceptable to downstream consumers.
- Single-GPU-only in v1 is acceptable.
- No multi-process GPU worker redesign in v1.
