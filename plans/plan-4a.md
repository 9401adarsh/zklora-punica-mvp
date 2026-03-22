## Phase-4a Plan: Thread-Pooled Prover Throughput Upgrade

### Summary
- Goal: increase proof **throughput** (not single-proof latency) using a **single-process thread pool**.
- Keep proof semantics strict: no proof math changes, no fast-mode behavior changes.
- Keep API/status contract unchanged (`queued -> pending -> ready|failed` and existing payload shapes).

### Implementation Changes
- Add a new config knob in [config.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/config.py):
  - `proof_worker_threads: int = 2`
  - env: `MVP_PROOF_WORKER_THREADS`
  - validation: must be `>=1`
- Refactor [prover_worker.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/prover_worker.py) into a dispatcher + worker-thread model:
  - `claim_dispatcher` thread:
    - serially calls `manifest.claim_next()` (single claimer to avoid duplicate-claim races)
    - immediately sets status to `pending`
    - pushes jobs to an in-memory FIFO queue
  - `N` proof worker threads (`N = proof_worker_threads`):
    - each thread owns its **own `ZkLoraAdapter` instance** (avoid shared adapter internals across threads)
    - runs `adapter.prove(job)`
    - writes terminal status via shared `ProofStore` (`ready` with refs or `failed` with `prove_failed`)
  - Main loop starts/joins threads and preserves existing `--once` / `--max-jobs` semantics:
    - `--once`: claim+process exactly one job using current synchronous path
    - normal mode: threaded pipeline
- Keep process model unchanged:
  - still one authoritative worker process by default
  - no multi-process worker support in this phase (no cross-process file-locking redesign yet).

### Test Plan
- Extend [test_prover_worker.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/tests/test_prover_worker.py):
  - `test_threaded_worker_processes_all_jobs_no_duplicates`
    - enqueue 20+ jobs
    - run with `threads=2`
    - assert each request reaches exactly one terminal state and no duplicate claims
  - `test_threaded_worker_failure_mapping_preserved`
    - mixed success/failure adapter behavior
    - assert `failed` + `error_code="prove_failed"` + non-empty `error_message`
  - `test_status_lifecycle_preserved_under_threads`
    - assert transitions remain valid and terminal timestamps are set
- Re-run current proof adapter/worker tests unchanged to ensure no API/status regressions.
- Manual perf gate (non-CI):
  - run same 5-request workload with `threads=1` and `threads=2`
  - compare wall-clock completion time and throughput; record results in run notes.

### Assumptions and Defaults
- Chosen defaults:
  - optimization target = throughput-first
  - concurrency model = in-process thread pool
  - semantics = strict (no debug-check removal/tuning in this phase)
  - default thread count = fixed `2` with env override
- Expected behavior:
  - throughput improves, single-request prove time remains roughly similar
  - first request still pays setup/keygen cold-start cost
  - proof artifact contract and public API remain backward compatible.
